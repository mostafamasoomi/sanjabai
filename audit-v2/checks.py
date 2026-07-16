import urllib.request, json
def get(path, token=None):
    h={"Content-Type":"application/json"}
    if token: h["Authorization"]=f"Bearer {token}"
    return json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:8081"+path,headers=h,method="GET"),timeout=15).read())

tok=json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:8081/auth/login",
    data=json.dumps({"email":"demo@multiai.com","password":"Demo@2026"}).encode(),
    headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["token"]

# catalog models
try:
    cat=get("/catalog/models",tok)
    print("CATALOG available count:", len(cat.get("data",[])))
    for m in cat.get("data",[]):
        print("  ", m["id"], m.get("provider"), m.get("availability"))
except Exception as e:
    print("catalog err", e)

# v1/models
try:
    vm=get("/v1/models",tok)
    print("V1 models count:", len(vm.get("data",[])))
except Exception as e:
    print("v1 err", e)
