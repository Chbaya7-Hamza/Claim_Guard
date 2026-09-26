"""Ingestion must quarantine a bad record, never lose its neighbours and never abort the file.

The rubric's first item is ingestion and normalisation of FHIR R4 JSON and CSV. A held-out file may carry a
malformed bundle, a stray text cell in a numeric column, an Excel byte-order mark or an orphan row.
"""
import copy
import csv
import json
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl
from ingest import ingest, summarize
from yara_engine import evaluate

CSV_DIR = ROOT / 'data' / 'development' / 'csv'
JUNK = [None, '', 0, -1, 1.5, True, [], {}, 'x', '2026-02-30', {'reference': 'Patient/nope'}, [None], ['a'],
        {'a': {'b': {}}}, '9' * 50, 10 ** 30, 'line break']


def sites(o, path=()):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            yield o, k
            yield from sites(v)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield o, i
            yield from sites(v)


class FhirBundlesThatAreWrong(unittest.TestCase):
    def test_no_mutation_of_a_bundle_aborts_ingestion_or_reaches_the_engine_broken(self):
        cfg = config(ROOT)
        bundles = load_jsonl(ROOT / 'data/development/fhir_bundles.jsonl')[:60]
        rng = random.Random(20260926)
        seen = {'accepted': 0, 'quarantined': 0}
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(700):
                b = copy.deepcopy(rng.choice(bundles))
                for _ in range(rng.choice((1, 1, 2, 3))):
                    found = list(sites(b))
                    if not found:
                        break
                    parent, key = rng.choice(found)
                    roll = rng.random()
                    if roll < 0.3:
                        del parent[key]
                    elif roll < 0.4 and isinstance(parent, list):
                        parent.append(copy.deepcopy(parent[key]))
                    else:
                        parent[key] = copy.deepcopy(rng.choice(JUNK))
                p = Path(tmp) / 'bundle.jsonl'
                p.write_text(json.dumps(b) + '\n', encoding='utf-8')
                items = list(ingest(p))  # must not raise
                self.assertEqual(len(items), 1)
                item = items[0]
                if item.claim is not None:
                    seen['accepted'] += 1
                    errors = []
                    self.assertEqual(len(evaluate(item.claim, cfg, errors)), 15)
                    self.assertEqual(errors, [])
                else:
                    seen['quarantined'] += 1
                    self.assertTrue(item.error)
        self.assertGreater(seen['accepted'], 100)
        self.assertGreater(seen['quarantined'], 100)

    def test_a_non_object_entry_is_quarantined_beside_good_bundles(self):
        bundles = load_jsonl(ROOT / 'data/development/fhir_bundles.jsonl')[:3]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'mixed.jsonl'
            lines = [json.dumps(bundles[0]), '"just a string"', '[1, 2]', '{"resourceType": "Bundle", "entry": "x"}',
                     '{"resourceType": "Bundle", "entry": [null, 5, "y"]}', json.dumps(bundles[1])]
            p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            items = list(ingest(p, 'fhir_bundle'))
        self.assertEqual(len(items), 6)
        self.assertTrue(items[0].accepted and items[5].accepted)
        self.assertFalse(any(i.accepted for i in items[1:5]))


class CsvFoldersThatAreWrong(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / 'csv'
        shutil.copytree(CSV_DIR, self.dir)
        with open(self.dir / 'claims.csv', newline='', encoding='utf-8') as f:
            self.ids = [r['claim_id'] for r in csv.DictReader(f)][:12]
        for name in ('claims', 'lines', 'coverage', 'authorizations', 'attachments'):
            self.keep(name)

    def tearDown(self):
        self.tmp.cleanup()

    def keep(self, name):
        with open(self.dir / f'{name}.csv', newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
            fields = rows[0].keys() if rows else csv.DictReader(open(self.dir / f'{name}.csv', encoding='utf-8')).fieldnames
        rows = [r for r in rows if r['claim_id'] in self.ids]
        self.write(name, rows, list(fields))

    def write(self, name, rows, fields=None):
        fields = fields or list(rows[0].keys())
        with open(self.dir / f'{name}.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    def rows(self, name):
        with open(self.dir / f'{name}.csv', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def go(self):
        return list(ingest(self.dir))

    def test_the_untouched_subset_is_fully_accepted(self):
        items = self.go()
        self.assertEqual((len(items), sum(i.accepted for i in items)), (12, 12))

    def test_one_text_cell_in_a_numeric_column_quarantines_only_that_claim(self):
        for bad in ('abc', 'nan', 'inf', '1e999', '2,5', '١٢'):
            lines = self.rows('lines')
            victim = lines[0]['claim_id']
            lines[0]['quantity'] = bad
            self.write('lines', lines)
            items = self.go()
            self.assertEqual(len(items), 12, bad)
            self.assertEqual(sum(i.accepted for i in items), 11, bad)
            self.assertIn(victim, next(i.source_ref for i in items if not i.accepted), bad)
            self.keep('lines')  # restore is not needed; rewrite from a clean copy each round
            shutil.copy(CSV_DIR / 'lines.csv', self.dir / 'lines.csv')
            self.keep('lines')

    def test_an_excel_byte_order_mark_loses_nothing(self):
        for name in ('claims', 'lines', 'coverage', 'authorizations', 'attachments'):
            p = self.dir / f'{name}.csv'
            p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes())
        items = self.go()
        self.assertEqual(sum(i.accepted for i in items), 12)

    def test_an_orphan_row_for_an_unlisted_claim_is_ignored_not_fatal(self):
        lines = self.rows('lines')
        lines.append(dict(lines[0], claim_id='CG-DOES-NOT-EXIST'))
        self.write('lines', lines)
        items = self.go()
        self.assertEqual((len(items), sum(i.accepted for i in items)), (12, 12))

    def test_a_claim_with_no_coverage_row_is_quarantined_alone(self):
        cov = [r for r in self.rows('coverage') if r['claim_id'] != self.ids[3]]
        self.write('coverage', cov)
        items = self.go()
        self.assertEqual(sum(i.accepted for i in items), 11)

    def test_a_claim_with_no_line_rows_is_quarantined_alone(self):
        lines = [r for r in self.rows('lines') if r['claim_id'] != self.ids[5]]
        self.write('lines', lines)
        self.assertEqual(sum(i.accepted for i in self.go()), 11)

    def test_summary_counts_add_up(self):
        lines = self.rows('lines')
        lines[0]['unit_price'] = 'abc'
        self.write('lines', lines)
        s = summarize(self.go())
        self.assertEqual(s['records'], s['accepted'] + s['quarantined'])
        self.assertEqual(s['quarantined'], 1)


class NormalizedFilesThatAreWrong(unittest.TestCase):
    def test_bom_bad_lines_and_non_objects_are_quarantined_and_the_rest_accepted(self):
        good = load_jsonl(ROOT / 'data/development/claims.jsonl')[:3]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'mixed.jsonl'
            raw = b'\xef\xbb\xbf' + b'\r\n'.join([
                json.dumps(good[0]).encode(), b'{oops', b'\xff\xfe', b'[1]', b'null', b'9' * 5000,
                json.dumps(good[1]).encode(), json.dumps(dict(good[2], surprise=1)).encode()]) + b'\r\n'
            p.write_bytes(raw)
            items = list(ingest(p))
        self.assertEqual(len(items), 8)
        self.assertEqual([i.accepted for i in items], [True, False, False, False, False, False, True, False])
        self.assertTrue(all(i.error for i in items if not i.accepted))


if __name__ == '__main__':
    unittest.main()
