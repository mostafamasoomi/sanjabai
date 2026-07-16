import json, urllib.request
BASE="http://localhost:8081"
tok=json.loads(urllib.request.urlopen(urllib.request.Request(BASE+"/auth/login",
    data=json.dumps({"email":"demo@multiai.com","password":"Demo@2026"}).encode(),
    headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["token"]
h={"Content-Type":"application/json","Authorization":f"Bearer {tok}"}
prompts={
 "greeting":"hi",
 "code":"write a python function to reverse a string",
 "reasoning":"analyze why the sky is blue and explain the trade-offs",
 "creative":"write a short story about a robot",
 "complex":"compare and contrast quantum computing and classical computing in detail with examples",
 "medium":"summarize the benefits of exercise",
}
for cat,p in prompts.items():
    payload={"model":"auto","messages":[{"role":"user","content":p}],"max_tokens":20,"temperature":0,"stream":False}
    r=urllib.request.urlopen(urllib.request.Request(BASE+"/v1/smart-chat",data=json.dumps(payload).encode(),headers=h,method="POST"),timeout=40)
    j=json.loads(r.read().decode())
    sel=r.headers.get("X-Smart-Model"); prov=r.headers.get("X-Smart-Provider"); scat=r.headers.get("X-Smart-Category")
    content=j.get("choices",[{}])[0].get("message",{}).get("content","")[:30] if "choices" in j else str(j)[:60]
    print(f"{cat:10s} => model={sel:18s} prov={prov:8s} cat={scat:10s} http={r.status} content='{content}'")
