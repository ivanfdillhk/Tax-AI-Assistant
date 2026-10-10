import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# Fallback - read from frontend .env if not in environ
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass


def test_putusan_no_filter_returns_all():
    r = requests.get(f"{BASE_URL}/api/putusan", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    print(f"[no filter] total={len(data)} case_types={sorted({d.get('case_type') for d in data})}")


def test_putusan_filter_banding():
    r = requests.get(f"{BASE_URL}/api/putusan", params={"case_type": "Putusan Banding"}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1, "Expected at least one Banding putusan"
    for d in data:
        ct = (d.get("case_type") or "").lower()
        assert "banding" in ct, f"Non-banding item leaked: {d.get('case_type')}"
    print(f"[banding] count={len(data)}")


def test_putusan_filter_peninjauan_kembali():
    r = requests.get(f"{BASE_URL}/api/putusan", params={"case_type": "Peninjauan Kembali"}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Expectation: no PK data seeded -> empty list, no leaked Banding
    for d in data:
        ct = (d.get("case_type") or "").lower()
        assert "peninjauan" in ct, f"Non-PK item leaked: {d.get('case_type')}"
    print(f"[PK] count={len(data)}")


def test_putusan_year_filter_still_works_with_case_type():
    # Combined filter regression
    r_all_banding = requests.get(f"{BASE_URL}/api/putusan", params={"case_type": "Putusan Banding"}, timeout=20)
    assert r_all_banding.status_code == 200
    banding = r_all_banding.json()
    if not banding:
        return
    year = banding[0].get("year")
    r = requests.get(f"{BASE_URL}/api/putusan", params={"case_type": "Putusan Banding", "year": str(year)}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert all(d.get("year") == year for d in data), "Year filter not respected"
    assert all("banding" in (d.get("case_type") or "").lower() for d in data)
    print(f"[banding+year={year}] count={len(data)}")
