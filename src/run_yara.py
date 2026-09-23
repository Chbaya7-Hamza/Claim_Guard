"""Run the full YARA-X facts-blob rule pack (all 15 rules) over claims."""
import argparse, json
from pathlib import Path
from engine_core import config, load_jsonl, validate_transport
from yara_engine import evaluate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',default='data/development/claims.jsonl');p.add_argument('--output',default='outputs/yara_predictions.jsonl');p.add_argument('--limit',type=int)
    a=p.parse_args();cfg=config(Path(__file__).resolve().parents[1]);claims=load_jsonl(a.input)
    if a.limit is not None:claims=claims[:a.limit]
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8') as f:
        for c in claims:
            validate_transport(c)
            for result in evaluate(c,cfg):f.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(f'Processed {len(claims)} claims across {len(cfg["rules"])} rules (R001-R015). Output: {out}')
if __name__=='__main__':main()
