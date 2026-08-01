import json, urllib.request, urllib.error, time, os

# Bypass any HTTP(S) proxy: litellm is on the docker-internal network and must
# be reached directly (the upstream tinyproxy cannot resolve docker hostnames).
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
_proxy_handler = urllib.request.ProxyHandler({})
_opener = urllib.request.build_opener(_proxy_handler)

LITELLM = "http://sanjhubai_litellm:4000"

MODELS = """tencent-hy3
mistral-large
mistral-medium-3-5
deepseek-v4-pro
deepseek-v4-flash
agnes-2.0-flash
kimi-k2.7-code-free
mimo-v2.5
mimo-v2.5-pro
mimo-v2.5-pro-ultraspeed
text-embedding-3-small
deepseek-v4-pro-free
deepseek-v4-flash-free
gemini-2.5-flash-free
gemini-2.5-pro-free
kr/claude-sonnet-4.5
kr/claude-haiku-4.5
kr/deepseek-3.2
kr/qwen3-coder-next
kr/glm-5
kr/MiniMax-M2.5
gc/gemini-2.5-pro
gc/gemini-2.5-flash
qd/qmodel_latest
kr/claude-sonnet-4.5-thinking
kr/claude-haiku-4.5-thinking
kr/claude-sonnet-4.5-agentic
kr/claude-haiku-4.5-agentic
kr/claude-sonnet-4.5-thinking-agentic
kr/claude-haiku-4.5-thinking-agentic
gc/gemini-3.1-pro-preview
gc/gemini-3.1-flash-lite-preview
""".strip().splitlines()

def call(model, timeout=40):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "say hi"}],
        "max_tokens": 16,
    }).encode()
    req = urllib.request.Request(
        f"{LITELLM}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _opener.open(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
            content = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, content[:80]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:200]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"

results = {"ok": [], "fail": []}
for m in MODELS:
    ok, msg = call(m)
    status = "OK " if ok else "FAIL"
    print(f"{status} {m}  -> {msg}")
    (results["ok"] if ok else results["fail"]).append(m)
    time.sleep(0.5)

print("\n=== SUMMARY ===")
print(f"WORKING ({len(results['ok'])}): {', '.join(results['ok'])}")
print(f"FAILED ({len(results['fail'])}): {', '.join(results['fail'])}")

with open("/app/_test/model_test_results.json", "w") as f:
    json.dump(results, f, indent=2)
