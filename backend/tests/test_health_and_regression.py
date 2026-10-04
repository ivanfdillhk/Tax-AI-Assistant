"""Regression tests for /health endpoint fix + core /api endpoints."""
import os
import json
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
LOCAL_BACKEND = "http://localhost:8001"


# --- /health endpoint (nginx deployment probe) ---
def test_health_endpoint_localhost():
    """nginx probe hits upstream 127.0.0.1:8001/health directly."""
    r = requests.get(f"{LOCAL_BACKEND}/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


def test_health_endpoint_http10():
    """nginx probe uses HTTP/1.0. Simulate with urllib3 (raw socket not needed; FastAPI accepts)."""
    import socket
    s = socket.create_connection(("127.0.0.1", 8001), timeout=10)
    s.sendall(b"GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
    resp = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        resp += chunk
    s.close()
    assert b"200 OK" in resp.split(b"\r\n", 1)[0]
    assert b'"status":"ok"' in resp or b'"status": "ok"' in resp


# --- Existing /api routes untouched ---
def test_api_putusan_by_id():
    r = requests.get(f"{BASE_URL}/api/putusan/put-004106-2020", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == "put-004106-2020"


def test_api_peraturan_list_nonempty():
    r = requests.get(f"{BASE_URL}/api/peraturan", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0


def test_api_branding_singleton():
    r = requests.get(f"{BASE_URL}/api/branding", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    # must have at least firm_name key (singleton shape)
    assert "firm_name" in data


def test_api_chat_sse_streams_tokens_and_done():
    r = requests.post(
        f"{BASE_URL}/api/chat",
        json={"question": "Apa isu PPN yang diputus?", "document_id": "put-004106-2020"},
        stream=True,
        timeout=120,
    )
    assert r.status_code == 200
    body = "".join(r.iter_lines(decode_unicode=True))
    assert '"type": "token"' in body or '"type":"token"' in body
    assert '"type": "done"' in body or '"type":"done"' in body
    assert "citations" in body
