"""Losslessly rebuild this pack's normalized JSONL from its relational CSV export."""
from pathlib import Path
import csv,json,argparse,math
def read(path):
    with open(path,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))  # utf-8-sig: Excel writes a BOM
def number(v):
    if v=='':return None
    if not v.isascii():return v  # float() would read Arabic-Indic or full-width digits; that is a silent repair
    try:n=float(v)
    except ValueError:return v  # not a number: keep the text so this one claim fails transport validation and is quarantined alone
    if not math.isfinite(n):return v
    return int(n) if n.is_integer() else n
def convert(folder):
    d=Path(folder);claims=read(d/'claims.csv');by={c['claim_id']:c for c in claims}
    for c in claims:
        for k,v in c.items():
            if v=='':c[k]=None
        c['total_amount']=number(c['total_amount']) if c['total_amount'] is not None else None
        c.update(coverage=None,lines=[],authorizations=[],attachments=[])
    nums={'lines':{'quantity','unit_price','net_amount'},'authorizations':{'max_quantity'},'coverage':set(),'attachments':set()}
    for name in nums:
        for row in read(d/(name+'.csv')):
            cid=row.pop('claim_id')
            if cid not in by:continue  # a row for a claim that claims.csv does not list has nothing to attach to
            for k,v in row.items():row[k]=number(v) if k in nums[name] else None if v=='' else v
            if name=='coverage':by[cid][name]=row
            else:by[cid][name].append(row)
    return claims
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);rows=convert(a.folder);out.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in rows),encoding='utf-8');print('Rebuilt',len(rows),'claims')
