# YARA Facts-Blob Harness (R001/R003/R006) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a deterministic Python fact extractor feeding a compiled YARA rule pack reproduces `engine_core.baseline()`'s existing R001/R003/R006 output exactly, establishing the pattern the remaining twelve rules will follow in later slices.

**Architecture:** `src/facts_extractor.py` computes, per rule, a small "details" dict (fact-tag lines for YARA, evidence paths, affected line ids, and the human-readable message) directly from the claim — a single source of truth per rule so the tags YARA sees and the result fields assembled afterward can never drift apart. `src/yara_engine.py` joins those tags into one facts blob, scans it with the compiled `rules/core.yar` pack, resolves the fixed precedence (`FAIL > UNABLE_TO_ASSESS > NOT_APPLICABLE > PASS`) in Python, and assembles `schemas/result.schema.json`-shaped results using the matching rule's evidence/message/line-ids from the details dict.

**Tech Stack:** Python 3.10, `yara-x` 1.20.0 (Python bindings, `yara_x.compile(source) -> Rules`, `Rules.scan(bytes) -> ScanResults`), standard-library `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-22-yara-facts-blob-harness-design.md`

## Global Constraints

- Never show `NOT_IMPLEMENTED` as `PASS`. A rule that matches no outcome in the scan must raise, never silently default.
- Never invent data — evidence values are always a direct `pointer()` lookup on the actual claim at a path the extractor genuinely identified; never a fabricated or guessed value.
- Deterministic results always report `confidence: null, confidence_kind: "not_probabilistic"`.
- `rule_version` on every emitted result and every `.yar` rule's `meta.rule_version` must equal the corresponding entry's `"version"` in `rules/rules.json` (currently `"1.0.0"` for R001/R003/R006).
- `yara-x==1.20.0` is the one pinned third-party dependency this slice adds to `requirements.txt`. No other new dependency.
- Nothing in `src/engine_core.py`, `src/run_baseline.py`, `rules/rules.json`, or `tests/test_baseline.py` is modified. The new pipeline is additive and is proven against the old one, never replaces it in this slice.
- All new/modified files use LF line endings consistent with the rest of the repo; Windows Git will warn about CRLF conversion on commit — that is expected and not an error to fix.

---

### Task 1: Pin the yara-x dependency

**Files:**
- Modify: `requirements.txt`
- Test: manual smoke check (no unittest needed for a dependency pin)

**Interfaces:**
- Produces: the `yara_x` module importable from any script run with this repo's Python environment, used by every later task.

- [ ] **Step 1: Update requirements.txt**

Replace the file's contents with:

```
# yara-x is the only third-party dependency this build adds so far (facts-blob
# rule pack harness). Everything else remains standard library.
yara-x==1.20.0
```

- [ ] **Step 2: Install it**

Run: `pip install -r requirements.txt`
Expected: `Successfully installed yara-x-1.20.0` (or "already satisfied" if already installed).

- [ ] **Step 3: Smoke-test the import**

Run: `python -c "import yara_x; print(yara_x.compile('rule t { condition: true }').scan(b'x').matching_rules[0].identifier)"`
Expected output: `t`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: pin yara-x 1.20.0 for the facts-blob rule pack harness"
```

---

### Task 2: `facts_extractor.py` — R001 details

**Files:**
- Create: `src/facts_extractor.py`
- Test: `tests/test_facts_extractor_r001.py`

**Interfaces:**
- Consumes: `engine_core.empty(v) -> bool`, `engine_core.valid_date(v) -> date | None` (both already defined in `src/engine_core.py`, imported read-only, not modified).
- Produces: `r001_details(claim: dict) -> dict` with keys `facts: list[str]`, `evidence_paths: list[str]`, `line_ids: list[str]`, `message: str`. Later tasks (3, 4) add sibling functions to this same file; task 6 consumes all three.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_facts_extractor_r001.py`:

```python
import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r001_details


class R001DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r001_details(self.c)
        self.assertEqual(d['facts'], ['R001:OK'])
        self.assertEqual(d['evidence_paths'], ['/invoice_number', '/member_id', '/diagnosis_code', '/lines'])
        self.assertEqual(d['line_ids'], [])
        self.assertEqual(d['message'], 'Required information is present.')

    def test_missing_top_level_field(self):
        self.c['invoice_number'] = None
        d = r001_details(self.c)
        self.assertEqual(d['facts'], ['R001:MISSING:/invoice_number'])
        self.assertEqual(d['evidence_paths'], ['/invoice_number'])
        self.assertEqual(d['message'], 'Required information is missing.')

    def test_missing_line_field_reports_line_id(self):
        self.c['lines'][0]['quantity'] = None
        d = r001_details(self.c)
        self.assertIn('R001:MISSING:/lines/0/quantity', d['facts'])
        self.assertEqual(d['line_ids'], ['L1'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_facts_extractor_r001 -v`
Expected: `ModuleNotFoundError: No module named 'facts_extractor'`

- [ ] **Step 3: Write the implementation**

Create `src/facts_extractor.py`:

```python
"""Deterministic fact extraction for the YARA facts-blob harness (R001/R003/R006).

Each rXXX_details(claim) is the single source of truth for that rule: it
computes the fact-tag lines YARA will pattern-match on, the evidence paths
and line ids the assembled result reports, and the human-readable message —
all from one pass over the claim, so the three can never drift apart.
"""
from engine_core import empty, valid_date


def r001_details(c):
    paths = []
    ids = []
    for k in ('invoice_number', 'member_id', 'diagnosis_code'):
        if empty(c[k]):
            paths.append(f'/{k}')
    for i, l in enumerate(c['lines']):
        for k in ('service_date', 'service_code', 'quantity', 'unit_price', 'net_amount'):
            if empty(l[k]):
                paths.append(f'/lines/{i}/{k}')
                ids.append(l['line_id'])
    if paths:
        return {
            'facts': [f'R001:MISSING:{p}' for p in paths],
            'evidence_paths': list(dict.fromkeys(paths)),
            'line_ids': sorted(set(ids)),
            'message': 'Required information is missing.',
        }
    return {
        'facts': ['R001:OK'],
        'evidence_paths': ['/invoice_number', '/member_id', '/diagnosis_code', '/lines'],
        'line_ids': [],
        'message': 'Required information is present.',
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_facts_extractor_r001 -v`
Expected: `OK` (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/facts_extractor.py tests/test_facts_extractor_r001.py
git commit -m "feat: add R001 fact/evidence/message extraction"
```

---

### Task 3: `facts_extractor.py` — R003 details

**Files:**
- Modify: `src/facts_extractor.py`
- Test: `tests/test_facts_extractor_r003.py`

**Interfaces:**
- Consumes: `engine_core.empty`, `engine_core.valid_date` (same as Task 2).
- Produces: `r003_details(claim: dict) -> dict`, same shape as `r001_details`'s return.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_facts_extractor_r003.py`:

```python
import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r003_details


class R003DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:OK'])

    def test_boundary_date_passes(self):
        day = self.c['lines'][0]['service_date']
        self.c['coverage']['start_date'] = day
        self.c['coverage']['end_date'] = day
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:OK'])

    def test_inactive_status_fails(self):
        self.c['coverage']['status'] = 'cancelled'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:INACTIVE:status=cancelled') for f in d['facts']))

    def test_out_of_period_fails(self):
        self.c['coverage']['start_date'] = '2026-01-01'
        self.c['coverage']['end_date'] = '2026-01-31'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:OUT_OF_PERIOD:/lines/0/service_date:') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_missing_end_date_is_unknown(self):
        self.c['coverage']['end_date'] = None
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['coverage']['end_date'] = None
        self.c['coverage']['status'] = 'cancelled'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:INACTIVE:') for f in d['facts']))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_facts_extractor_r003 -v`
Expected: `ImportError: cannot import name 'r003_details' from 'facts_extractor'`

- [ ] **Step 3: Add the implementation**

Append to `src/facts_extractor.py`:

```python


def r003_details(c):
    cv = c['coverage']
    start = valid_date(cv['start_date'])
    end = valid_date(cv['end_date'])
    paths = ['/coverage/status', '/coverage/start_date', '/coverage/end_date']
    failed = []
    unknown = []
    facts = []
    ids = []
    if empty(cv['status']):
        unknown.append('coverage status')
    elif cv['status'] != 'active':
        failed.append('coverage status is not active')
        facts.append(f'R003:INACTIVE:status={cv["status"]}')
    if not start or not end:
        unknown.append('coverage period')
    for i, l in enumerate(c['lines']):
        paths.append(f'/lines/{i}/service_date')
        d = valid_date(l['service_date'])
        if not d:
            unknown.append('service date')
            continue
        if (start and d < start) or (end and d > end):
            failed.append('service outside coverage period')
            ids.append(l['line_id'])
            facts.append(
                f'R003:OUT_OF_PERIOD:/lines/{i}/service_date:service={d.isoformat()}:'
                f'start={start.isoformat() if start else ""}:end={end.isoformat() if end else ""}'
            )
    if failed:
        message = '; '.join(sorted(set(failed))) + (
            '; Additional unknown inputs: ' + ', '.join(sorted(set(unknown))) if unknown else ''
        )
    elif unknown:
        facts = ['R003:UNKNOWN']
        message = '; '.join(sorted(set(unknown)))
    else:
        facts = ['R003:OK']
        message = 'All service dates are within active coverage, including boundaries.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': sorted(set(ids)), 'message': message}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_facts_extractor_r003 -v`
Expected: `OK` (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/facts_extractor.py tests/test_facts_extractor_r003.py
git commit -m "feat: add R003 fact/evidence/message extraction"
```

---

### Task 4: `facts_extractor.py` — R006 details + `build_blob`

**Files:**
- Modify: `src/facts_extractor.py`
- Test: `tests/test_facts_extractor_r006.py`

**Interfaces:**
- Consumes: `engine_core.empty`, `engine_core.valid_date`.
- Produces: `r006_details(claim: dict) -> dict` (same shape); `build_blob(claim: dict) -> str`, the newline-joined, newline-terminated facts blob for all three rules — consumed by `yara_engine.py` in Task 6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_facts_extractor_r006.py`:

```python
import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r006_details, build_blob


class R006DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:OK'])
        self.assertEqual(d['evidence_paths'], ['/lines'])

    def test_duplicate_line_fails(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        self.c['lines'].append(other)
        d = r006_details(self.c)
        self.assertTrue(any(f.startswith('R006:DUPLICATE:0,2:') for f in d['facts']))
        self.assertEqual(sorted(d['line_ids']), ['L1', 'L99'])

    def test_separate_modifier_is_not_duplicate(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        other['modifier'] = 'EDU-SEPARATE'
        self.c['lines'].append(other)
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:OK'])

    def test_missing_service_code_is_unknown(self):
        self.c['lines'][0]['service_code'] = None
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:UNKNOWN'])


class BuildBlobTests(unittest.TestCase):
    def test_blob_contains_all_three_rules_and_ends_with_newline(self):
        c = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        blob = build_blob(c)
        self.assertIn('R001:OK', blob)
        self.assertIn('R003:OK', blob)
        self.assertIn('R006:OK', blob)
        self.assertTrue(blob.endswith('\n'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_facts_extractor_r006 -v`
Expected: `ImportError: cannot import name 'r006_details' from 'facts_extractor'`

- [ ] **Step 3: Add the implementation**

Append to `src/facts_extractor.py`:

```python


def r006_details(c):
    seen = {}
    dups = []
    missing = False
    facts = []
    for i, l in enumerate(c['lines']):
        if empty(l['service_code']) or not valid_date(l['service_date']):
            missing = True
            continue
        key = (l['service_code'], l['service_date'], l['modifier'] or '')
        if key in seen:
            a = seen[key]
            dups.extend([a, i])
            facts.append(f'R006:DUPLICATE:{a},{i}:key={"|".join(key)}')
        else:
            seen[key] = i
    ids = []
    paths = []
    for i in sorted(set(dups)):
        ids.append(c['lines'][i]['line_id'])
        paths.extend(f'/lines/{i}/{k}' for k in ('service_code', 'service_date', 'modifier'))
    if dups:
        message = 'Possible duplicate lines require review.' + (
            ' Additional lines have missing inputs.' if missing else ''
        )
    elif missing:
        facts = ['R006:UNKNOWN']
        message = 'Missing inputs prevent a complete duplicate check.'
    else:
        facts = ['R006:OK']
        message = 'No duplicate service/date/modifier combinations.'
    return {'facts': facts, 'evidence_paths': paths or ['/lines'], 'line_ids': ids, 'message': message}


def build_blob(c):
    facts = r001_details(c)['facts'] + r003_details(c)['facts'] + r006_details(c)['facts']
    return '\n'.join(facts) + '\n'
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_facts_extractor_r006 -v`
Expected: `OK` (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/facts_extractor.py tests/test_facts_extractor_r006.py
git commit -m "feat: add R006 fact/evidence/message extraction and build_blob"
```

---

### Task 5: `rules/core.yar` — the R001/R003/R006 rule pack

**Files:**
- Create: `rules/core.yar`
- Test: `tests/test_facts_blob.py`

**Interfaces:**
- Consumes: nothing (pure YARA source, hand-built fact-tag strings in the test).
- Produces: a compilable YARA source string at `rules/core.yar`, whose rules carry `meta.rule_id` / `meta.outcome` / `meta.severity` / `meta.rule_version`. Task 6's `yara_engine.py` compiles this exact file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_facts_blob.py` (this exercises the YARA layer directly against hand-built fact lines, independent of `facts_extractor.py`, per the engine spec's Section 11 requirement to catch a broken rule close to its cause):

```python
import unittest, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import yara_x


class YaraPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = yara_x.compile((ROOT / 'rules' / 'core.yar').read_text(encoding='utf-8'))

    def outcomes(self, blob):
        scan = self.rules.scan(blob.encode('utf-8'))
        by_rule = {}
        for rule in scan.matching_rules:
            meta = dict(rule.metadata)
            by_rule.setdefault(meta['rule_id'], set()).add(meta['outcome'])
        return by_rule

    def test_r001_fail(self):
        self.assertEqual(self.outcomes('R001:MISSING:/invoice_number\n')['R001'], {'FAIL'})

    def test_r001_pass(self):
        self.assertEqual(self.outcomes('R001:OK\n')['R001'], {'PASS'})

    def test_r003_fail_inactive(self):
        self.assertEqual(self.outcomes('R003:INACTIVE:status=cancelled\n')['R003'], {'FAIL'})

    def test_r003_fail_out_of_period(self):
        blob = 'R003:OUT_OF_PERIOD:/lines/0/service_date:service=2026-01-01:start=2026-02-01:end=2026-03-01\n'
        self.assertEqual(self.outcomes(blob)['R003'], {'FAIL'})

    def test_r003_unable(self):
        self.assertEqual(self.outcomes('R003:UNKNOWN\n')['R003'], {'UNABLE_TO_ASSESS'})

    def test_r003_pass(self):
        self.assertEqual(self.outcomes('R003:OK\n')['R003'], {'PASS'})

    def test_r006_fail(self):
        self.assertEqual(self.outcomes('R006:DUPLICATE:0,2:key=SVC-LAB|2026-05-25|\n')['R006'], {'FAIL'})

    def test_r006_unable(self):
        self.assertEqual(self.outcomes('R006:UNKNOWN\n')['R006'], {'UNABLE_TO_ASSESS'})

    def test_r006_pass(self):
        self.assertEqual(self.outcomes('R006:OK\n')['R006'], {'PASS'})

    def test_rule_versions_match_rules_json(self):
        import json
        rules_json = {r['rule_id']: r for r in json.loads((ROOT / 'rules/rules.json').read_text())}
        scan = self.rules.scan(
            b'R001:OK\nR003:OK\nR006:OK\n'
        )
        for rule in scan.matching_rules:
            meta = dict(rule.metadata)
            self.assertEqual(meta['rule_version'], rules_json[meta['rule_id']]['version'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_facts_blob -v`
Expected: `FileNotFoundError` (or a compile error) — `rules/core.yar` does not exist yet.

- [ ] **Step 3: Write the rule pack**

Create `rules/core.yar`:

```yara
rule R001_fail {
  meta:
    rule_id = "R001"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R001:MISSING:/
  condition:
    $m
}

rule R001_pass {
  meta:
    rule_id = "R001"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R001:OK"
  condition:
    $m
}

rule R003_fail {
  meta:
    rule_id = "R003"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $inactive = /R003:INACTIVE:/
    $out_of_period = /R003:OUT_OF_PERIOD:/
  condition:
    any of them
}

rule R003_unable {
  meta:
    rule_id = "R003"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R003:UNKNOWN"
  condition:
    $m
}

rule R003_pass {
  meta:
    rule_id = "R003"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R003:OK"
  condition:
    $m
}

rule R006_fail {
  meta:
    rule_id = "R006"
    outcome = "FAIL"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = /R006:DUPLICATE:/
  condition:
    $m
}

rule R006_unable {
  meta:
    rule_id = "R006"
    outcome = "UNABLE_TO_ASSESS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R006:UNKNOWN"
  condition:
    $m
}

rule R006_pass {
  meta:
    rule_id = "R006"
    outcome = "PASS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R006:OK"
  condition:
    $m
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_facts_blob -v`
Expected: `OK` (10 tests)

- [ ] **Step 5: Commit**

```bash
git add rules/core.yar tests/test_facts_blob.py
git commit -m "feat: add YARA rule pack for R001/R003/R006"
```

---

### Task 6: `yara_engine.py` — compile, scan, resolve precedence, assemble results

**Files:**
- Create: `src/yara_engine.py`
- Test: `tests/test_yara_engine.py`

**Interfaces:**
- Consumes: `facts_extractor.r001_details`, `r003_details`, `r006_details` (Tasks 2–4); `engine_core.pointer(obj, path) -> Any` (existing helper, imported read-only); `engine_core.config(root) -> dict` (existing, used only in tests to load `rules.json`).
- Produces: `EngineError(Exception)`; `evaluate(claim: dict, cfg: dict) -> list[dict]`, one result per rule in `{'R001', 'R003', 'R006'}`, each dict shaped exactly like `schemas/result.schema.json` — consumed by Task 7's diff script and Task 8's validate_pack extension conceptually (Task 8 re-scans the pack directly, not through `evaluate`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_yara_engine.py` (mirrors the R001/R003/R006 cases already in `tests/test_baseline.py`, run through the new pipeline instead of `engine_core.base_check`):

```python
import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from yara_engine import evaluate, EngineError


class YaraEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def result(self, rid):
        return next(r for r in evaluate(self.c, self.cfg) if r['rule_id'] == rid)

    def test_clean_claim_all_pass(self):
        for rid in ('R001', 'R003', 'R006'):
            self.assertEqual(self.result(rid)['status'], 'PASS')

    def test_r001_missing_fails(self):
        self.c['invoice_number'] = None
        r = self.result('R001')
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(r['confidence'], None)
        self.assertEqual(r['confidence_kind'], 'not_probabilistic')
        self.assertEqual(r['method'], 'deterministic')

    def test_r003_boundary_passes(self):
        day = self.c['lines'][0]['service_date']
        self.c['coverage']['start_date'] = day
        self.c['coverage']['end_date'] = day
        self.assertEqual(self.result('R003')['status'], 'PASS')

    def test_r003_unknown_coverage_is_not_pass(self):
        self.c['coverage']['end_date'] = None
        self.assertEqual(self.result('R003')['status'], 'UNABLE_TO_ASSESS')

    def test_r003_known_failure_dominates_unknown(self):
        self.c['coverage']['end_date'] = None
        self.c['coverage']['status'] = 'cancelled'
        self.assertEqual(self.result('R003')['status'], 'FAIL')

    def test_r006_duplicate_and_modifier(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        self.c['lines'].append(other)
        self.assertEqual(self.result('R006')['status'], 'FAIL')
        other['modifier'] = 'EDU-SEPARATE'
        self.assertEqual(self.result('R006')['status'], 'PASS')

    def test_missing_rule_in_pack_raises(self):
        cfg = {'rules': [r for r in self.cfg['rules'] if r['rule_id'] != 'R001'] + [
            {**next(r for r in self.cfg['rules'] if r['rule_id'] == 'R001'), 'rule_id': 'R999', 'version': '1.0.0'}
        ]}
        # R999 has no facts and no YARA rule at all -> must raise, never silently pass.
        import yara_engine
        yara_engine.DETAIL_FUNCS['R999'] = yara_engine.DETAIL_FUNCS.pop('R001')
        try:
            with self.assertRaises(EngineError):
                evaluate(self.c, cfg)
        finally:
            yara_engine.DETAIL_FUNCS['R001'] = yara_engine.DETAIL_FUNCS.pop('R999')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_yara_engine -v`
Expected: `ModuleNotFoundError: No module named 'yara_engine'`

- [ ] **Step 3: Write the implementation**

Create `src/yara_engine.py`:

```python
"""Compile rules/core.yar, scan a claim's facts blob, resolve precedence, assemble results."""
import hashlib
from pathlib import Path

import yara_x

from engine_core import pointer
from facts_extractor import r001_details, r003_details, r006_details

PACK_PATH = Path(__file__).resolve().parents[1] / 'rules' / 'core.yar'
PRECEDENCE = ['FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE', 'PASS']
DETAIL_FUNCS = {'R001': r001_details, 'R003': r003_details, 'R006': r006_details}

_compiled = None


class EngineError(Exception):
    pass


def compiled_rules():
    global _compiled
    if _compiled is None:
        _compiled = yara_x.compile(PACK_PATH.read_text(encoding='utf-8'))
    return _compiled


def pack_hash():
    return hashlib.sha256(PACK_PATH.read_bytes()).hexdigest()


def evaluate(c, cfg):
    detail_funcs = DETAIL_FUNCS
    details = {rid: fn(c) for rid, fn in detail_funcs.items()}
    blob = '\n'.join(fact for d in details.values() for fact in d['facts']) + '\n'
    scan = compiled_rules().scan(blob.encode('utf-8'))
    by_rule = {}
    for rule in scan.matching_rules:
        meta = dict(rule.metadata)
        by_rule.setdefault(meta['rule_id'], set()).add(meta['outcome'])
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    results = []
    for rule_id in detail_funcs:
        outcomes = by_rule.get(rule_id, set())
        if not outcomes:
            raise EngineError(f'{rule_id} produced no outcome - extractor and rule pack are out of sync')
        status = next(o for o in PRECEDENCE if o in outcomes)
        r = rule_defs[rule_id]
        d = details[rule_id]
        results.append({
            'claim_id': c['claim_id'],
            'rule_id': rule_id,
            'rule_version': r['version'],
            'status': status,
            'severity': r['severity'],
            'affected_line_ids': d['line_ids'],
            'evidence': [{'path': p, 'value': pointer(c, p)} for p in dict.fromkeys(d['evidence_paths'])],
            'rule_source': r['source'],
            'explanation': d['message'],
            'corrective_action': r['corrective_action'] if status in ('FAIL', 'UNABLE_TO_ASSESS') else '',
            'confidence': None,
            'confidence_kind': 'not_probabilistic',
            'requires_human_review': status in ('FAIL', 'UNABLE_TO_ASSESS'),
            'method': 'deterministic',
            'review_status': 'unreviewed',
        })
    return results
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_yara_engine -v`
Expected: `OK` (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/yara_engine.py tests/test_yara_engine.py
git commit -m "feat: add yara_engine - compile, scan, resolve precedence, assemble results"
```

---

### Task 7: Equivalence proof against the development split

**Files:**
- Create: `scripts/diff_baseline_vs_yara.py` (throwaway proof script, not a project deliverable)

**Interfaces:**
- Consumes: `engine_core.config`, `engine_core.load_jsonl`, `engine_core.base_check`, `engine_core.validate_transport` (all existing); `yara_engine.evaluate` (Task 6).
- Produces: a pass/fail console report; no importable interface for later tasks.

- [ ] **Step 1: Write the script**

Create `scripts/diff_baseline_vs_yara.py`:

```python
"""Throwaway equivalence proof: yara_engine must reproduce engine_core.baseline
for R001/R003/R006 over the full development split, field-for-field."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl, base_check, validate_transport
from yara_engine import evaluate

SCOPE = ('R001', 'R003', 'R006')


def main():
    cfg = config(ROOT)
    claims = load_jsonl(ROOT / 'data/development/claims.jsonl')
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    mismatches = []
    for c in claims:
        validate_transport(c)
        old = {rid: base_check(c, rule_defs[rid]) for rid in SCOPE}
        new = {r['rule_id']: r for r in evaluate(c, cfg)}
        for rid in SCOPE:
            if old[rid] != new[rid]:
                mismatches.append((c['claim_id'], rid, old[rid], new[rid]))
    if mismatches:
        for claim_id, rid, old_r, new_r in mismatches[:5]:
            print(f'MISMATCH {claim_id} {rid}')
            print('  baseline:', json.dumps(old_r, sort_keys=True))
            print('  yara    :', json.dumps(new_r, sort_keys=True))
        print(f'{len(mismatches)} mismatches out of {len(claims) * len(SCOPE)} rule results')
        sys.exit(1)
    print(f'MATCH: {len(claims)} claims x {len(SCOPE)} rules, '
          f'{len(claims) * len(SCOPE)} results identical to the existing baseline.')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run it against the 400-claim development split**

Run: `python scripts/diff_baseline_vs_yara.py`
Expected: `MATCH: 400 claims x 3 rules, 1200 results identical to the existing baseline.`

If it reports mismatches instead: read the first printed diff, find which field differs (usually `evidence` ordering, a `message` wording divergence, or a missed edge case in `facts_extractor.py`'s R001/R003/R006 logic vs. `engine_core.base_check`), fix the extractor function in `src/facts_extractor.py`, re-run the relevant unit tests from Tasks 2–4, then re-run this script until it reports `MATCH`. Do not proceed to Task 8 until it does — this script's pass is the literal acceptance criterion for this whole slice.

- [ ] **Step 3: Commit**

```bash
git add scripts/diff_baseline_vs_yara.py
git commit -m "test: add development-split equivalence proof against the existing baseline"
```

---

### Task 8: `validate_pack.py` — preflight consistency check for `core.yar`

**Files:**
- Modify: `src/validate_pack.py`

**Interfaces:**
- Consumes: `rules/core.yar` (Task 5), `rules/rules.json` (existing).
- Produces: `check_core_yar(root: Path, cfg: dict) -> list[str]` (returns the sorted rule ids it validated), called from `main()`; printed as part of `validate_pack.py`'s existing report.

- [ ] **Step 1: Add the check function**

In `src/validate_pack.py`, add near the top (after the existing imports):

```python
import yara_x
```

Then add this function before `def main():`:

```python
def check_core_yar(root, cfg):
    """Compile rules/core.yar and confirm every (rule_id, outcome) it defines
    both fires on a matching probe and carries the rule_version rules.json expects.
    Scoped to the rule ids actually present in the pack, so it stays green as
    later slices add R002-R015 incrementally rather than all at once."""
    pack_path = root / 'rules' / 'core.yar'
    rules = yara_x.compile(pack_path.read_text(encoding='utf-8'))
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    probes = {
        ('R001', 'FAIL'): 'R001:MISSING:/invoice_number',
        ('R001', 'PASS'): 'R001:OK',
        ('R003', 'FAIL'): 'R003:INACTIVE:status=cancelled',
        ('R003', 'UNABLE_TO_ASSESS'): 'R003:UNKNOWN',
        ('R003', 'PASS'): 'R003:OK',
        ('R006', 'FAIL'): 'R006:DUPLICATE:0,1:key=SVC-LAB|2026-05-25|',
        ('R006', 'UNABLE_TO_ASSESS'): 'R006:UNKNOWN',
        ('R006', 'PASS'): 'R006:OK',
    }
    blob = '\n'.join(probes.values()) + '\n'
    scan = rules.scan(blob.encode('utf-8'))
    seen = {}
    for rule in scan.matching_rules:
        meta = dict(rule.metadata)
        seen[(meta['rule_id'], meta['outcome'])] = meta.get('rule_version')
    for key in probes:
        assert key in seen, f'core.yar: expected outcome not matched: {key}'
        assert seen[key] == rule_defs[key[0]]['version'], f'core.yar: rule_version mismatch for {key}'
    return sorted({rule_id for rule_id, _ in probes})
```

- [ ] **Step 2: Call it from main()**

In `src/validate_pack.py`, find this block near the end of `main()`:

```python
    manifest=root/'SHA256SUMS.json'
    if manifest.exists():
```

Insert immediately before it:

```python
    yara_ids=check_core_yar(root,cfg)
```

Find the final `print` line:

```python
    print(json.dumps(totals,indent=2));print('PASS: transport, public labels/evidence, CSV round trips, split IDs, mapping basics and release checksums. This is not full HL7 FHIR validation.')
```

Replace it with:

```python
    print(json.dumps(totals,indent=2));print('PASS: transport, public labels/evidence, CSV round trips, split IDs, mapping basics and release checksums. This is not full HL7 FHIR validation.')
    print(f'PASS: rules/core.yar compiles and matches rules.json for {yara_ids}.')
```

- [ ] **Step 3: Run it**

Run: `python src/validate_pack.py`
Expected: the existing per-split JSON summary, the existing `PASS:` line, and a new final line:
`PASS: rules/core.yar compiles and matches rules.json for ['R001', 'R003', 'R006'].`

- [ ] **Step 4: Run the full test suite once more to confirm nothing regressed**

Run: `python -m unittest discover -s tests -v`
Expected: all tests pass, including the pre-existing `tests/test_baseline.py` (untouched) and every test added in Tasks 2–6.

- [ ] **Step 5: Commit**

```bash
git add src/validate_pack.py
git commit -m "feat: extend validate_pack to check rules/core.yar against rules.json"
```
