#!/usr/bin/env python3
import json, re, time, urllib.request, urllib.error
from collections import Counter

BACKEND = "http://localhost:8081/v1/chat/completions"
CONFIG = "/root/multiai/backend/litellm_config.yaml"
OUT = "/root/multiai/audit-v2/test_all_results.json"

def get_token():
    for _ in range(3):
        try:
            req = urllib.request.Request("http://localhost:8081/auth/login",
                data=json.dumps({"email":"demo@multiai.com","password":"Demo@2026"}).encode(),
                headers={"Content-Type":"application/json"}, method="POST")
            return json.load(urllib.request.urlopen(req, timeout=20))["token"]
        except Exception:
            time.sleep(2)
    raise SystemExit("cannot get token")

models = []
with open(CONFIG) as f:
    for line in f:
        m = re.match(r"\s*-\s*model_name:\s*(\S+)\s*$", line)
        if m:
            models.append(m.group(1))
print(f"Parsed {len(models)} models from config", flush=True)

token = get_token()
results = {}

def save():
    with open(OUT,"w") as f:
        json.dump({"results": results}, f, indent=2)

def test_model(name, timeout=25, depth=0):
    payload = {"model": name, "messages":[{"role":"user","content":"say hi in one word"}],
               "max_tokens": 5, "temperature": 0}
    req = urllib.request.Request(BACKEND, data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"}, method="POST")
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        body = r.read().decode()
        try:
            j = json.loads(body)
            preview = j.get("choices",[{}])[0].get("message",{}).get("content","")[:40]
        except Exception:
            preview = body[:40]
        return r.status, preview, None, round((time.time()-t0)*1000)
    except urllib.error.HTTPError as e:
        if e.code == 429 and depth == 0:
            time.sleep(4)
            return test_model(name, timeout, depth=1)
        body = e.read().decode()[:300]
        try:
            j = json.loads(body)
            err = j.get("error",{}).get("message") or j.get("detail") or body[:200]
        except Exception:
            err = body[:200]
        return e.code, "", str(err)[:200], round((time.time()-t0)*1000)
    except Exception as e:
        return 0, "", f"{type(e).__name__}: {str(e)[:150]}", round((time.time()-t0)*1000)

for i, name in enumerate(models):
    status, preview, err, ms = test_model(name)
    results[name] = {"http": status, "preview": preview, "error": err, "ms": ms}
    mark = "OK " if status == 200 else "XX "
    print(f"{mark}{i+1:3d}/{len(models)} {name:45s} {status} {ms}ms {preview or err}", flush=True)
    save()

working = [n for n,v in results.items() if v["http"]==200]
broken = [n for n,v in results.items() if v["http"]!=200]
codes = Counter(v["http"] for v in results.values())
summary = {"total": len(models), "working": len(working), "broken": len(broken),
           "working_models": working, "code_distribution": dict(codes)}
with open(OUT,"w") as f:
    json.dump({"summary": summary, "results": results}, f, indent=2)
print("\n=== SUMMARY ===", flush=True)
print(json.dumps(summary, indent=2), flush=True)
