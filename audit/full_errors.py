#!/usr/bin/env python3
"""Get full error details for broken models."""
import json, subprocess, sys, os

BASE = "http://127.0.0.1:8081"
TOKEN = os.environ.get("AUDIT_TOKEN", "")
if not TOKEN:
    TOKEN = open(os.path.expanduser("/root/multiai/audit/.token")).read().strip()

MODELS = {
    'openai/gpt-4o': 'openrouter',
    'mimo-v2.5': 'bynara',
    'mimo-v2.5-pro': 'bynara',
    'grok-4.5': 'bynara',
    'glm-5.2-free': 'bynara',
}

def get_full_error(model):
    p = {'model': model, 'messages': [{'role':'user','content':'hi'}], 'max_tokens': 5}
    r = subprocess.run(['curl', '-s', '-X', 'POST', f'{BASE}/v1/chat/completions',
        '-H', 'Authorization: Bearer ' + TOKEN,
        '-H', 'Content-Type: application/json', '-d', json.dumps(p)],
        capture_output=True, text=True, timeout=15)
    print(f'=== {model} ===')
    stdout = r.stdout.strip()
    lines = stdout.rsplit('\n', 1)
    body = lines[0] if len(lines) == 2 else stdout
    http_code = lines[1] if len(lines) == 2 else '???'
    print(f'HTTP: {http_code}')
    try:
        d = json.loads(body)
        print(json.dumps(d, indent=2, ensure_ascii=False))
    except:
        print(body[:500])
    print()

for model in MODELS:
    get_full_error(model)