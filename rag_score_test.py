#!/usr/bin/env python3
"""Independent re-score test of multiai RAG endpoints against localhost:8081."""
import json, time, sys, uuid
import requests

BASE = "http://localhost:8081"
results = []
def log(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# unique user
rand = uuid.uuid4().hex[:8]
email = f"ragtest_{rand}@example.com"
password = "TestPass#12345"
name = "RAG Tester"

s = requests.Session()

# 1) SIGNUP
r = s.post(f"{BASE}/auth/signup", json={"email": email, "password": password, "name": name})
log("signup", r.status_code == 200 and "token" in r.json(), f"HTTP {r.status_code} {r.text[:120]}")
token = r.json().get("token")
headers = {"Authorization": f"Bearer {token}"}

# 2) AUTH REQUIRED on RAG endpoints (no token)
r = requests.post(f"{BASE}/v1/rag/upload", files={"file": ("a.txt","hi")})
log("auth_upload_401", r.status_code == 401, f"HTTP {r.status_code} {r.text[:80]}")
r = requests.post(f"{BASE}/v1/rag/query", json={"question":"x"})
log("auth_query_401", r.status_code == 401, f"HTTP {r.status_code} {r.text[:80]}")
r = requests.get(f"{BASE}/v1/rag/documents")
log("auth_list_401", r.status_code == 401, f"HTTP {r.status_code} {r.text[:80]}")

# 3) UPLOAD EN
en_content = b"This is a technical document about machine learning. Neural networks learn patterns from data. Gradient descent optimizes the model weights. Overfitting happens when the model memorizes training data instead of generalizing."
r = s.post(f"{BASE}/v1/rag/upload", files={"file": ("ml_intro.txt", en_content)}, headers=headers)
j = r.json()
log("upload_en", r.status_code == 200 and "document_id" in j, f"HTTP {r.status_code} {j}")
en_id = j.get("document_id")

# 4) UPLOAD FA
fa_content = "این یک سند فارسی درباره یادگیری ماشین است. شبکه‌های عصبی الگوهای داده را یاد می‌گیرند. کاهش گرادیان وزن‌های مدل را بهینه می‌کند. بیش‌برازش زمانی رخ می‌دهد که مدل داده‌های آموزشی را حفظ کند.".encode("utf-8")
r = s.post(f"{BASE}/v1/rag/upload", files={"file": ("ml_fa.txt", fa_content)}, headers=headers)
j = r.json()
log("upload_fa", r.status_code == 200 and "document_id" in j, f"HTTP {r.status_code} {j}")
fa_id = j.get("document_id")

# 5) STATUS poll
time.sleep(0.5)
for did in (en_id, fa_id):
    r = s.get(f"{BASE}/v1/rag/documents/{did}/status", headers=headers)
    j = r.json()
    log(f"status_{did}", r.status_code == 200 and "status" in j, f"HTTP {r.status_code} {j}")

# 6) LIST
r = s.get(f"{BASE}/v1/rag/documents", headers=headers)
j = r.json()
docs = j.get("documents", [])
log("list", r.status_code == 200 and len(docs) >= 2, f"HTTP {r.status_code} count={len(docs)}")

# 7) QUERY EN
r = s.post(f"{BASE}/v1/rag/query", json={"question": "What is overfitting in machine learning?", "model": "mimo-v2.5"}, headers=headers)
j = r.json()
en_answer = j.get("answer", "")
log("query_en", r.status_code == 200 and ("answer" in j or "result" in j), f"HTTP {r.status_code} keys={list(j.keys())} ans_len={len(str(en_answer))}")

# 8) QUERY FA
r = s.post(f"{BASE}/v1/rag/query", json={"question": "بیش‌برازش چیست؟", "model": "mimo-v2.5"}, headers=headers)
j = r.json()
fa_answer = j.get("answer", "")
log("query_fa", r.status_code == 200 and ("answer" in j or "result" in j), f"HTTP {r.status_code} keys={list(j.keys())} ans_len={len(str(fa_answer))}")

# 9) DELETE
r = s.delete(f"{BASE}/v1/rag/documents/{en_id}", headers=headers)
log("delete_en", r.status_code == 200 and j.get("deleted") is not None or r.json().get("deleted")==True, f"HTTP {r.status_code} {r.text[:80]}")
# verify gone from list
r = s.get(f"{BASE}/v1/rag/documents", headers=headers)
docs_after = r.json().get("documents", [])
deleted_present = any(d["id"]==en_id for d in docs_after)
log("delete_verify", not deleted_present, f"deleted id still listed? {deleted_present}; remaining={len(docs_after)}")

# 10) DELETE non-existent
r = s.delete(f"{BASE}/v1/rag/documents/99999999", headers=headers)
log("delete_404", r.status_code == 404, f"HTTP {r.status_code} {r.text[:80]}")

# 11) filename traversal sanitization
r = s.post(f"{BASE}/v1/rag/upload", files={"file": ("../../evil.txt", b"content")}, headers=headers)
jj = r.json()
safe = jj.get("filename","") == "evil.txt"
log("filename_sanitize", r.status_code == 200 and safe, f"HTTP {r.status_code} returned_filename={jj.get('filename')!r}")

# 12) unsupported type rejection
r = s.post(f"{BASE}/v1/rag/upload", files={"file": ("x.exe", b"x")}, headers=headers)
log("reject_unsupported", r.status_code == 400, f"HTTP {r.status_code} {r.text[:80]}")

# 13) empty question rejection
r = s.post(f"{BASE}/v1/rag/query", json={"question": "   ", "model":"mimo-v2.5"}, headers=headers)
log("reject_empty_q", r.status_code == 400, f"HTTP {r.status_code} {r.text[:80]}")

print("\n=== SUMMARY ===")
print(f"EN answer sample: {str(en_answer)[:300]}")
print(f"FA answer sample: {str(fa_answer)[:300]}")
passed = sum(1 for _,ok,_ in results if ok)
print(f"PASSED {passed}/{len(results)}")
for n,ok,d in results:
    if not ok:
        print("  FAIL:", n, "->", d)
