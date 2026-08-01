"""Integration tests for the Document Generator feature.

Covers the 4 endpoints (/v1/documents/generate, /v1/documents (list),
/v1/documents/{id}/download, /v1/documents/{id}/delete) including
happy paths and security/validation negatives.

Run against the live API:
    pytest tests/test_document_generator.py --live

Or import the helper matrix for CI.
"""
import json
import subprocess
import pytest

BASE = "http://localhost:8081"
DEMO_EMAIL = "demo@sanjhubai.com"
DEMO_PASS = "Demo@2026"

try:
    import httpx
    HAVE_HTTPX = True
except ImportError:
    HAVE_HTTPX = False


def _login() -> dict:
    r = httpx.post(
        f"{BASE}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code}"
    cookie = r.cookies.get("session")
    assert cookie, "no session cookie"
    return {"Cookie": f"session={cookie}"}


def _file_type(path: str) -> str:
    out = subprocess.run(["file", path], capture_output=True, text=True)
    return out.stdout


@pytest.mark.skipif(not HAVE_HTTPX, reason="httpx required for live tests")
@pytest.mark.live
class TestDocumentGeneratorLive:
    def setup_method(self):
        self.headers = _login()

    def test_generate_pptx_real_file(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "renewable energy benefits", "type": "pptx"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "pptx"
        assert data["slides_count"] >= 1
        # download and verify it is a real PowerPoint
        d = httpx.get(f"{BASE}{data['download_url']}", headers=self.headers, timeout=30)
        assert d.status_code == 200
        open("/tmp/_t.pptx", "wb").write(d.content)
        assert "OXML" in _file_type("/tmp/_t.pptx")

    def test_generate_docx_real_file(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "quarterly sales report", "type": "docx"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "docx"
        d = httpx.get(f"{BASE}{data['download_url']}", headers=self.headers, timeout=30)
        assert d.status_code == 200
        open("/tmp/_t.docx", "wb").write(d.content)
        assert "OXML" in _file_type("/tmp/_t.docx")

    def test_invalid_type_rejected(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "x", "type": "pdf"},
            timeout=30,
        )
        assert r.status_code == 400

    def test_empty_prompt_rejected(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "", "type": "pptx"},
            timeout=30,
        )
        assert r.status_code == 400

    def test_oversized_prompt_rejected(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "a" * 5000, "type": "pptx"},
            timeout=30,
        )
        assert r.status_code == 413

    def test_disallowed_model_rejected(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "x", "type": "pptx", "model": "evil-model"},
            timeout=30,
        )
        assert r.status_code == 400

    def test_unauthorized_generate_401(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            json={"prompt": "x", "type": "pptx"},
            timeout=30,
        )
        assert r.status_code == 401

    def test_malformed_doc_id_400(self):
        r = httpx.get(
            f"{BASE}/v1/documents/../etc/passwd/download",
            headers=self.headers,
            timeout=30,
        )
        assert r.status_code in (400, 404)  # never 500

    def test_list_and_delete(self):
        r = httpx.post(
            f"{BASE}/v1/documents/generate",
            headers=self.headers,
            json={"prompt": "delete me test", "type": "pptx"},
            timeout=120,
        )
        doc_id = r.json()["id"]
        lst = httpx.get(f"{BASE}/v1/documents", headers=self.headers, timeout=30)
        assert lst.status_code == 200
        assert any(d["id"] == doc_id for d in lst.json()["documents"])
        dele = httpx.delete(f"{BASE}/v1/documents/{doc_id}", headers=self.headers, timeout=30)
        assert dele.status_code == 200
        # second delete should 404
        dele2 = httpx.delete(f"{BASE}/v1/documents/{doc_id}", headers=self.headers, timeout=30)
        assert dele2.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--live"])
