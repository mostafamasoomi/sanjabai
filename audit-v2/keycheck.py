import os, json, urllib.request, urllib.error
# Read .env
env={}
for line in open("/root/multiai/.env"):
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); env[k]=v.strip().strip('"').strip("'")
bynara=env.get("BYNARA_API_KEY"); orkey=env.get("OPENROUTER_API_KEY")
print("BYNARA_API_KEY len:", len(bynara) if bynara else 0)
print("OPENROUTER_API_KEY len:", len(orkey) if orkey else 0)

def post(url, body, headers, timeout=20):
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method="POST"),timeout=timeout)
        return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)[:120]

# Direct Bynara test (bypass litellm) for a working and a broken model
burl="https://router.bynara.id/v1/chat/completions"
bh={"Content-Type":"application/json","Authorization":f"Bearer {bynara}"}
for mdl in ["tencent-hy3","mimo-v2.5","kimi-k2.7-code-free","mistral-large"]:
    s,b=post(burl,{"model":mdl,"messages":[{"role":"user","content":"hi"}],"max_tokens":3},bh)
    print(f"BYNARA direct {mdl}: {s} {b}")

# Direct OpenRouter key check
ourl="https://openrouter.ai/api/v1/chat/completions"
oh={"Content-Type":"application/json","Authorization":f"Bearer {orkey}"}
s,b=post(ourl,{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"max_tokens":3},oh)
print(f"OPENROUTER direct openai/gpt-4o-mini: {s} {b}")
# key info endpoint
try:
    r=urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/key",headers={"Authorization":f"Bearer {orkey}"},method="GET"),timeout=15)
    print("OPENROUTER /key:", r.status, r.read().decode()[:200])
except urllib.error.HTTPError as e:
    print("OPENROUTER /key:", e.code, e.read().decode()[:200])
except Exception as e:
    print("OPENROUTER /key err:", str(e)[:120])
