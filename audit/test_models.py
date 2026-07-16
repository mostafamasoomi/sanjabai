#!/usr/bin/env python3
"""Model audit test script."""
import json, subprocess, sys

BASE = "http://127.0.0.1:8081"
TOKEN = open('/root/multiai/audit/.token').read().strip()

BYNARA = [
    "agnes-2.0-flash", "agnes-2.5-flash", "gemini-3.5-flash",
    "mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5-pro-ultraspeed",
    "mistral-large", "mistral-medium-3-5", "tencent-hy3",
    "grok-4.5", "glm-5.2-free", "kimi-k2.7-code-free"
]

OPENROUTER = [
    "openai/gpt-5.6-luna", "openai/gpt-5.5", "openai/gpt-5", "openai/gpt-4o",
    "openai/gpt-4o-mini", "openai/gpt-3.5-turbo", "openai/o3-mini", "openai/o4-mini",
    "anthropic/claude-sonnet-5", "anthropic/claude-opus-4.8", "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4", "anthropic/claude-opus-4",
    "google/gemini-3.5-flash", "google/gemini-2.5-flash", "google/gemini-2.5-pro",
    "deepseek/deepseek-v4-pro", "deepseek/deepseek-chat", "deepseek/deepseek-r1",
    "x-ai/grok-4.5", "qwen/qwen3.7-max", "qwen/qwen3.6-plus", "qwen/qwen3-coder",
    "mistralai/mistral-large-2512", "mistralai/mistral-medium-3-5",
    "mistralai/mistral-small-3.2-24b-instruct",
    "meta-llama/llama-4-maverick", "meta-llama/llama-3.3-70b-instruct",
    "nousresearch/hermes-4-405b", "nousresearch/hermes-3-llama-3.1-70b",
    "perplexity/sonar-pro", "cohere/command-a", "openrouter/auto",
    "aion-labs/aion-3.0", "x-ai/grok-4.3", "tencent/hy3",
    "minimax/minimax-m3", "qwen/qwen3.7-plus", "stepfun/step-3.7-flash",
    "openai/gpt-5.4", "moonshotai/kimi-k2.7-code",
]

def test_model(model):
    payload = {"model": model, "messages": [{"role": "user", "content": "say hi"}], "max_tokens": 10}
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}", "-X", "POST", f"{BASE}/v1/chat/completions",
        "-H", "Authorization: Bearer " + TOKEN,
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        lines = output.rsplit('\n', 1)
        if len(lines) == 2:
            body, http_code = lines
        else:
            body, http_code = "", "000"
        http_code = http_code.strip()
        
        if http_code == "200":
            return "WORKING", http_code, ""
        else:
            try:
                d = json.loads(body)
                err = d.get('error', {})
                code = err.get('code', 'none')
                msg = (err.get('message', '') or '')[:120]
                return f"BROKEN_{http_code}", http_code, f"{code}: {msg}"
            except:
                return f"BROKEN_{http_code}", http_code, body[:100]
    except Exception as e:
        return "ERROR", "000", str(e)[:100]

if __name__ == "__main__":
    print("=" * 70)
    print("BYNARA MODELS (12 total)")
    print("=" * 70)
    bynara_results = {}
    for model in BYNARA:
        status, code, detail = test_model(model)
        bynara_results[model] = (status, code, detail)
        print(f"  [{status}] {model} (HTTP {code}) {detail[:80] if detail else ''}")
        sys.stdout.flush()

    print()
    print("=" * 70)
    print("OPENROUTER MODELS (40 tested)")
    print("=" * 70)
    openrouter_results = {}
    for model in OPENROUTER:
        status, code, detail = test_model(model)
        openrouter_results[model] = (status, code, detail)
        print(f"  [{status}] {model} (HTTP {code}) {detail[:80] if detail else ''}")
        sys.stdout.flush()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_results = {**bynara_results, **openrouter_results}
    working = [m for m, (s, _, _) in all_results.items() if s == "WORKING"]
    broken = {m: (s, c, d) for m, (s, c, d) in all_results.items() if s != "WORKING"}

    print(f"\nWorking: {len(working)} models")
    for m in working:
        print(f"  + {m}")

    print(f"\nBroken: {len(broken)} models")
    for m, (s, c, d) in sorted(broken.items(), key=lambda x: x[1][0]):
        print(f"  - {m} -> {s} (HTTP {c}): {d[:80] if d else 'no detail'}")

    with open('/root/multiai/audit/test_results.json', 'w') as f:
        json.dump({
            "working": working,
            "broken": {m: {"status": s, "http_code": c, "detail": d} for m, (s, c, d) in broken.items()},
            "bynara": {m: {"status": s, "http_code": c, "detail": d} for m, (s, c, d) in bynara_results.items()},
            "openrouter": {m: {"status": s, "http_code": c, "detail": d} for m, (s, c, d) in openrouter_results.items()},
        }, f, indent=2)

    print(f"\nResults saved to /root/multiai/audit/test_results.json")