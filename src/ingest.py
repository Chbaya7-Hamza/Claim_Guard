"""Single entry point for claim ingestion and normalization.

Accepts, and auto-detects:
  - normalized JSONL / JSON  (the authoritative benchmark input)
  - FHIR R4-style Bundle JSONL / JSON  (mapped by fhir_adapter; partial by design)
  - a relational CSV folder (claims.csv, lines.csv, coverage.csv, authorizations.csv,
    attachments.csv), rebuilt by csv_to_jsonl.convert

Every record ends as either an accepted claim in the ONE internal representation
(the normalized envelope, checked by engine_core.validate_transport) or a
quarantined record with the reason. A bad record never aborts the batch, is never
silently dropped and never becomes a "passed" claim.

    python src/ingest.py --input data/development/fhir_bundles.jsonl \\
        --output outputs/ingested.jsonl --quarantine outputs/quarantined.jsonl \\
        --report outputs/ingest_report.json
"""
import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from csv_to_jsonl import convert as csv_folder_to_claims
from engine_core import validate_transport
from fhir_adapter import FhirMappingError, bundle_to_claim
from jsonl_reader import parse_json, read_lines

NORMALIZED = 'normalized_json'
FHIR = 'fhir_bundle'
CSV_FOLDER = 'csv_folder'


@dataclass
class Ingested:
    source_format: str
    source_ref: str                      # e.g. "claims.jsonl:17" or a folder path
    claim: dict = None                   # normalized envelope when accepted
    error: str = None                    # reason when quarantined
    report: dict = field(default_factory=dict)
    raw: object = None                   # original record kept for the quarantine file

    @property
    def accepted(self):
        return self.claim is not None


def detect_format(path):
    p = Path(path)
    if p.is_dir():
        if (p / 'claims.csv').exists():
            return CSV_FOLDER
        raise ValueError(f'{p} is a directory without claims.csv')
    head = p.read_text(encoding='utf-8-sig', errors='replace').lstrip()[:2000]
    return FHIR if '"resourceType"' in head and '"Bundle"' in head else NORMALIZED


def _records(path):
    """Yield (source_ref, parsed_json_or_None, parse_error_or_None). Handles JSONL,
    and a JSON array; one malformed line is reported, not fatal."""
    p = Path(path)
    with open(p, 'rb') as f:
        head = f.read(4096).removeprefix(b'\xef\xbb\xbf').lstrip()
    if head.startswith(b'['):  # one JSON array: it can only be read (and lost) as a whole
        try:
            text = p.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError as e:
            yield p.name, None, f'Invalid UTF-8: {e}'
            return
        value, error = parse_json(text)
        if error or not isinstance(value, list):
            yield p.name, None, error or 'Invalid JSON: expected an array'
            return
        for i, rec in enumerate(value, start=1):
            yield f'{p.name}[{i}]', rec, None
        return
    for i, line, read_error in read_lines(p):
        if read_error:
            yield f'{p.name}:{i}', None, read_error
            continue
        rec, error = parse_json(line)
        yield f'{p.name}:{i}', rec, error


def _finish(item):
    """Common gate: whatever the source, the result must pass the transport contract."""
    if item.claim is not None:
        try:
            validate_transport(item.claim)
        except (ValueError, KeyError, TypeError) as e:
            item.error = f'Failed transport validation: {e}'
            item.raw = item.raw if item.raw is not None else item.claim
            item.claim = None
    return item


def ingest(path, fmt=None):
    fmt = fmt or detect_format(path)
    if fmt == CSV_FOLDER:
        try:
            claims = csv_folder_to_claims(path)
        except (OSError, KeyError, ValueError) as e:
            yield Ingested(fmt, str(path), error=f'CSV folder could not be read: {e}')
            return
        for c in claims:
            yield _finish(Ingested(fmt, f"{Path(path).name}/claims.csv:{c.get('claim_id')}", claim=c,
                                   report={'source_format': fmt}))
        return
    for ref, rec, err in _records(path):
        if err:
            yield Ingested(fmt, ref, error=err)
            continue
        if not isinstance(rec, dict):  # null, a number, an array: nothing to map, but it must be counted
            yield Ingested(fmt, ref, error=f'Expected a JSON object, got {type(rec).__name__}', raw=rec)
            continue
        if fmt == FHIR:
            try:
                claim, report = bundle_to_claim(rec)
                yield _finish(Ingested(fmt, ref, claim=claim, report=report, raw=rec))
            except FhirMappingError as e:
                yield Ingested(fmt, ref, error=f'FHIR mapping failed: {e}', raw=rec)
            except Exception as e:  # any other shape a malformed bundle takes: quarantine this record, keep going
                yield Ingested(fmt, ref, error=f'FHIR mapping failed: {type(e).__name__}: {e}', raw=rec)
        else:
            yield _finish(Ingested(fmt, ref, claim=rec, report={'source_format': fmt}, raw=rec))


def summarize(items):
    items = list(items)
    warnings = Counter(w.split(':')[0] for i in items for w in i.report.get('warnings', []))
    quarantined = [i for i in items if not i.accepted]
    return {
        'source_format': items[0].source_format if items else None,
        'records': len(items),
        'accepted': len(items) - len(quarantined),
        'quarantined': len(quarantined),
        'quarantine_reasons': dict(Counter(i.error.split(':')[0] for i in quarantined)),
        'warnings': dict(warnings),
        'not_carried_by_source': sorted({f for i in items for f in i.report.get('not_carried_by_fhir', [])}),
        'inferred_fields': sorted({f for i in items for f in i.report.get('inferred', {})}),
        'encounters_carried': sum(len(i.report.get('encounters', [])) for i in items),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input', required=True)
    p.add_argument('--format', choices=[NORMALIZED, FHIR, CSV_FOLDER])
    p.add_argument('--output', required=True, help='accepted claims, normalized JSONL')
    p.add_argument('--quarantine', help='quarantined records with reasons, JSONL')
    p.add_argument('--report')
    a = p.parse_args()
    items = list(ingest(a.input, a.format))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(''.join(json.dumps(i.claim, ensure_ascii=False) + '\n' for i in items if i.accepted), encoding='utf-8')
    if a.quarantine:
        Path(a.quarantine).write_text(''.join(
            json.dumps({'source_ref': i.source_ref, 'error': i.error, 'raw': i.raw}, ensure_ascii=False, default=str) + '\n'
            for i in items if not i.accepted), encoding='utf-8')
    summary = summarize(items)
    if a.report:
        Path(a.report).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
