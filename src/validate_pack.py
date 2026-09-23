"""Check public pack transport, results, CSV round trips, split separation and mapping basics."""
from pathlib import Path
import json,hashlib
from engine_core import load_jsonl,validate_transport,config
from csv_to_jsonl import convert
from evaluate import index
from schema_subset import validate
import yara_x

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
        ('R002', 'FAIL'): 'R002:LATE:/lines/0/service_date:service=2026-01-01:submission=2025-01-01',
        ('R002', 'UNABLE_TO_ASSESS'): 'R002:UNKNOWN',
        ('R002', 'PASS'): 'R002:OK',
        ('R003', 'FAIL'): 'R003:INACTIVE:status=cancelled',
        ('R003', 'UNABLE_TO_ASSESS'): 'R003:UNKNOWN',
        ('R003', 'PASS'): 'R003:OK',
        ('R004', 'FAIL'): 'R004:PATIENT_MISMATCH:patient_id=X:beneficiary_patient_id=Y',
        ('R004', 'UNABLE_TO_ASSESS'): 'R004:UNKNOWN',
        ('R004', 'PASS'): 'R004:OK',
        ('R005', 'FAIL'): 'R005:UNLISTED:provider_id=X',
        ('R005', 'UNABLE_TO_ASSESS'): 'R005:UNKNOWN',
        ('R005', 'PASS'): 'R005:OK',
        ('R006', 'FAIL'): 'R006:DUPLICATE:0,1:key=SVC-LAB|2026-05-25|',
        ('R006', 'UNABLE_TO_ASSESS'): 'R006:UNKNOWN',
        ('R006', 'PASS'): 'R006:OK',
        ('R007', 'FAIL'): 'R007:MISMATCH:/lines/0/net_amount:expected=1:actual=2',
        ('R007', 'UNABLE_TO_ASSESS'): 'R007:UNKNOWN',
        ('R007', 'PASS'): 'R007:OK',
        ('R008', 'FAIL'): 'R008:MISSING_AUTH:/lines/0/authorization_id',
        ('R008', 'UNABLE_TO_ASSESS'): 'R008:UNKNOWN',
        ('R008', 'NOT_APPLICABLE'): 'R008:NOT_APPLICABLE',
        ('R008', 'PASS'): 'R008:OK',
        ('R009', 'FAIL'): 'R009:MISMATCH:/lines/0/authorization_id',
        ('R009', 'UNABLE_TO_ASSESS'): 'R009:UNKNOWN',
        ('R009', 'NOT_APPLICABLE'): 'R009:NOT_APPLICABLE',
        ('R009', 'PASS'): 'R009:OK',
        ('R010', 'FAIL'): 'R010:MISSING_DOC:/lines/0/service_code',
        ('R010', 'UNABLE_TO_ASSESS'): 'R010:UNKNOWN',
        ('R010', 'NOT_APPLICABLE'): 'R010:NOT_APPLICABLE',
        ('R010', 'PASS'): 'R010:OK',
        ('R011', 'FAIL'): 'R011:NOT_CATALOGUED:/lines/0/service_code',
        ('R011', 'UNABLE_TO_ASSESS'): 'R011:UNKNOWN',
        ('R011', 'PASS'): 'R011:OK',
        ('R012', 'FAIL'): 'R012:MISMATCH:total_amount=1:expected=2',
        ('R012', 'UNABLE_TO_ASSESS'): 'R012:UNKNOWN',
        ('R012', 'PASS'): 'R012:OK',
        ('R013', 'FAIL'): 'R013:LIMIT:/lines/0/quantity',
        ('R013', 'UNABLE_TO_ASSESS'): 'R013:UNKNOWN',
        ('R013', 'PASS'): 'R013:OK',
        ('R014', 'FAIL'): 'R014:LATE:lag=100:window=60',
        ('R014', 'UNABLE_TO_ASSESS'): 'R014:UNKNOWN',
        ('R014', 'NOT_APPLICABLE'): 'R014:NOT_APPLICABLE',
        ('R014', 'PASS'): 'R014:OK',
        ('R015', 'FAIL'): 'R015:MISMATCH:currency=USD',
        ('R015', 'UNABLE_TO_ASSESS'): 'R015:UNKNOWN',
        ('R015', 'PASS'): 'R015:OK',
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

def main():
    root=Path(__file__).resolve().parents[1];seen=set();patients=set();totals={};cfg=config(root)
    claim_schema=json.loads((root/'schemas/claim.schema.json').read_text());result_schema=json.loads((root/'schemas/result.schema.json').read_text())
    for split,count in [('development',400),('validation',150),('stress',50)]:
        folder=root/'data'/split;claims=load_jsonl(folder/'claims.jsonl')
        assert len(claims)==count,(split,'count')
        for c in claims:
            validate_transport(c);validate(c,claim_schema)
            assert c['claim_id'] not in seen,'Claim leak/duplicate'
            assert c['patient_id'] not in patients,'Patient leak/duplicate'
            seen.add(c['claim_id']);patients.add(c['patient_id'])
        assert convert(folder/'csv')==claims,'CSV round trip mismatch'
        gold=index(load_jsonl(folder/'expected_results.jsonl'),{c['claim_id']:c for c in claims})
        for result in gold.values():validate(result,result_schema)
        assert set(gold)=={(c['claim_id'],r['rule_id']) for c in claims for r in cfg['rules']},'Gold coverage'
        bundles=load_jsonl(folder/'fhir_bundles.jsonl');assert len(bundles)==count
        for c,b in zip(claims,bundles):
            assert b['resourceType']=='Bundle' and b['type']=='collection'
            entries=b['entry'];assert len({x['fullUrl'] for x in entries})==len(entries)
            cl=next(x['resource'] for x in entries if x['resource']['resourceType']=='Claim')
            assert cl['id']==c['claim_id'] and cl['total']['value']==c['total_amount']
            assert len(cl['item'])==len(c['lines'])
            for a,l in zip(cl['item'],c['lines']):
                assert a['productOrService']['coding'][0]['code']==l['service_code']
                assert a.get('servicedDate')==l['service_date']
        totals[split]={'claims':len(claims),'results':len(gold)}
    yara_ids=check_core_yar(root,cfg);print(f'PASS: rules/core.yar compiles and matches rules.json for {yara_ids}.')
    manifest=root/'SHA256SUMS.json'
    if manifest.exists():
        for rel,digest in json.loads(manifest.read_text()).items():
            p=root/rel
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise AssertionError('Release checksum differs: '+rel+' (expected after intentional edits; retain original pack for comparison)')
    print(json.dumps(totals,indent=2));print('PASS: transport, public labels/evidence, CSV round trips, split IDs, mapping basics and release checksums. This is not full HL7 FHIR validation.')
if __name__=='__main__':main()
