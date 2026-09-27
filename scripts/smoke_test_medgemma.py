"""One-off smoke test for the official google/medgemma-4b-it checkpoint via transformers, in 4-bit
(bitsandbytes), against the same FINDING/RULE fixture used for gemma3:4b and qwen3:4b. Not wired into
llm_adapter.py yet -- this only answers "does the official checkpoint avoid the community GGUF's
chat-template mismatch" before any pipeline integration work.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig

from llm_adapter import build_prompt, validate_explanation, check_grounding, repair_citations

FINDING = {
    'claim_id': 'CG-TEST4', 'rule_id': 'R009', 'rule_version': '1.0.0', 'status': 'UNABLE_TO_ASSESS',
    'severity': 'high', 'affected_line_ids': ['L2'],
    'evidence': [{'path': '/authorizations/AUTH-2/valid_to', 'value': None}],
    'rule_source': 'fictional-rulebook/R009@1.0.0',
    'explanation': 'A comparison input is missing.',
    'corrective_action': 'Request the authorization validity dates from the provider.',
    'confidence': None, 'confidence_kind': 'not_probabilistic',
    'requires_human_review': True, 'method': 'deterministic', 'review_status': 'unreviewed',
}
RULE = {
    'rule_id': 'R009', 'title': 'Authorization record matches service', 'severity': 'high',
    'logic': 'Authorization patient, service, dates and quantity must match the line.',
    'corrective_action': FINDING['corrective_action'], 'version': '1.0.0',
    'source': 'fictional-rulebook/R009@1.0.0',
}

MODEL_ID = 'google/medgemma-4b-it'

print(f'Loading {MODEL_ID} in 4-bit...')
t0 = time.monotonic()
quant_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                   bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True)
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, quantization_config=quant_config,
                                                     device_map='cuda', torch_dtype=torch.bfloat16)
print(f'Loaded in {time.monotonic() - t0:.1f}s. GPU memory: {torch.cuda.memory_allocated() / 1e9:.2f} GB')

prompt = build_prompt(FINDING, RULE)
messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
inputs = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(model.device)

t0 = time.monotonic()
with torch.inference_mode():
    out = model.generate(**inputs, max_new_tokens=800, do_sample=False)
gen_time = time.monotonic() - t0
text = processor.decode(out[0][inputs['input_ids'].shape[-1]:], skip_special_tokens=True)
print(f'\nGenerated in {gen_time:.1f}s, {len(out[0]) - inputs["input_ids"].shape[-1]} tokens')
print('\n--- raw output ---')
print(text)

print('\n--- pipeline parse attempt ---')
clean = text.strip()
if clean.startswith('```'):
    clean = clean.strip('`')
    if clean.startswith('json'):
        clean = clean[4:]
try:
    parsed = json.loads(clean)
    checked = check_grounding(validate_explanation(repair_citations(parsed, FINDING), FINDING), FINDING, RULE)
    print('PASSED the real pipeline checks:')
    print(json.dumps(checked, indent=2))
except Exception as e:
    print(f'FAILED: {type(e).__name__}: {e}')
