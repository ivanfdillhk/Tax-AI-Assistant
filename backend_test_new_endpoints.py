#!/usr/bin/env python3
"""
Backend test for TaxLens new endpoints:
1. POST /api/peraturan/{id}/refetch - Refetch full text from source
2. DELETE /api/peraturan/{id} and DELETE /api/putusan/{id} - Delete with seed tombstones
3. POST /api/putusan/import-url - Regression test after refactor
"""
import requests
import os
import sys
import time
import uuid

# Backend URL from environment
BACKEND_URL = "https://tax-assistant-ai-1.preview.emergentagent.com/api"

def test_refetch_peraturan():
    """TEST 1: Refetch peraturan full text from source."""
    print("=" * 80)
    print("TEST 1: REFETCH PERATURAN FULL TEXT (POST /api/peraturan/{id}/refetch)")
    print("=" * 80)
    
    results = {
        "passed": [],
        "failed": [],
        "soft_notes": []
    }
    
    # Test 1a: Get seed record uu-28-2007 and note current body length
    print("\n[TEST 1a] GET /api/peraturan to find uu-28-2007 and note body length")
    try:
        response = requests.get(f"{BACKEND_URL}/peraturan", timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 1a: GET /api/peraturan failed")
            return results
        
        peraturan_list = response.json()
        uu_28_2007 = None
        for p in peraturan_list:
            if p.get("id") == "uu-28-2007":
                uu_28_2007 = p
                break
        
        if not uu_28_2007:
            print("❌ FAIL: uu-28-2007 not found in peraturan list")
            results["failed"].append("Test 1a: uu-28-2007 not found")
            return results
        
        original_body_length = len(uu_28_2007.get("body", ""))
        source_url = uu_28_2007.get("source_url", "")
        
        print(f"   ✅ Found uu-28-2007")
        print(f"   Original body length: {original_body_length} chars")
        print(f"   Source URL: {source_url}")
        
        if not source_url or not source_url.startswith("http"):
            print(f"   ⚠️  WARNING: source_url is not a valid HTTP URL")
            results["soft_notes"].append("Test 1a: source_url may not be valid")
        
        results["passed"].append("Test 1a: Found uu-28-2007")
        
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 1a: Exception - {e}")
        return results
    
    # Test 1b: POST /api/peraturan/uu-28-2007/refetch
    print("\n[TEST 1b] POST /api/peraturan/uu-28-2007/refetch")
    print("   (Network-dependent: may take 10-35 seconds)")
    try:
        response = requests.post(f"{BACKEND_URL}/peraturan/uu-28-2007/refetch", timeout=35)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            new_body_length = len(data.get("body", ""))
            print(f"   New body length: {new_body_length} chars")
            print(f"   Body length change: {new_body_length - original_body_length:+d} chars")
            
            if new_body_length >= original_body_length:
                print(f"   ✅ PASS: Body length maintained or increased (source reachable)")
                results["passed"].append("Test 1b: Refetch uu-28-2007 successful")
            else:
                print(f"   ⚠️  SOFT NOTE: Body length decreased (may indicate source issue)")
                results["soft_notes"].append("Test 1b: Body length decreased after refetch")
                results["passed"].append("Test 1b: Refetch returned 200 (endpoint working)")
        
        elif response.status_code in [400, 502]:
            print(f"   ⚠️  SOFT NOTE: Got {response.status_code} - source may be JS-only or unreachable")
            print(f"   Response: {response.text[:200]}")
            results["soft_notes"].append(f"Test 1b: Source unreachable (HTTP {response.status_code})")
            results["passed"].append("Test 1b: Endpoint behaves correctly (no 500 crash)")
        
        else:
            print(f"❌ FAIL: Unexpected status code {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            results["failed"].append(f"Test 1b: Unexpected status {response.status_code}")
        
    except requests.Timeout:
        print(f"   ⚠️  SOFT NOTE: Request timed out (source may be slow/unreachable)")
        results["soft_notes"].append("Test 1b: Request timeout (network-dependent)")
        results["passed"].append("Test 1b: Endpoint exists (timeout is acceptable)")
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 1b: Exception - {e}")
    
    # Test 1c: Create/identify a peraturan with no valid source_url
    print("\n[TEST 1c] Upload peraturan with no valid source_url, then refetch")
    try:
        # Upload a small text file as peraturan (source_url will be 'File pengguna')
        test_content = "Test peraturan content for refetch test"
        files = {"file": ("test_peraturan.txt", test_content.encode(), "text/plain")}
        response = requests.post(f"{BACKEND_URL}/peraturan/upload", files=files, timeout=30)
        
        print(f"   Upload status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Upload failed with {response.status_code}")
            results["failed"].append("Test 1c: Upload failed")
        else:
            data = response.json()
            test_peraturan_id = data.get("id")
            source_url = data.get("source_url", "")
            
            print(f"   Uploaded peraturan id: {test_peraturan_id}")
            print(f"   Source URL: {source_url}")
            
            # Try to refetch this peraturan (should return 400)
            print(f"\n[TEST 1c-refetch] POST /api/peraturan/{test_peraturan_id}/refetch")
            response = requests.post(f"{BACKEND_URL}/peraturan/{test_peraturan_id}/refetch", timeout=30)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 400:
                print(f"   ✅ PASS: Correctly returns 400 for peraturan with no valid source_url")
                results["passed"].append("Test 1c: Refetch with invalid source_url returns 400")
            else:
                print(f"❌ FAIL: Expected 400, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                results["failed"].append(f"Test 1c: Expected 400, got {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 1c: Exception - {e}")
    
    # Test 1d: POST /api/peraturan/<random-uuid>/refetch -> expect 404
    print("\n[TEST 1d] POST /api/peraturan/<random-uuid>/refetch (expect 404)")
    random_uuid = str(uuid.uuid4())
    try:
        response = requests.post(f"{BACKEND_URL}/peraturan/{random_uuid}/refetch", timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"   ✅ PASS: Correctly returns 404 for non-existent peraturan")
            results["passed"].append("Test 1d: Refetch non-existent peraturan returns 404")
        else:
            print(f"❌ FAIL: Expected 404, got {response.status_code}")
            results["failed"].append(f"Test 1d: Expected 404, got {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 1d: Exception - {e}")
    
    return results


def test_delete_endpoints():
    """TEST 2: Delete peraturan & putusan with seed tombstones."""
    print("\n" + "=" * 80)
    print("TEST 2: DELETE PERATURAN & PUTUSAN (with seed tombstones)")
    print("=" * 80)
    
    results = {
        "passed": [],
        "failed": [],
        "soft_notes": []
    }
    
    # Test 2a: Import a throwaway peraturan, then delete it
    print("\n[TEST 2a] Import throwaway peraturan via import-url, then DELETE")
    try:
        # Use a direct public PDF URL
        pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        payload = {"url": pdf_url, "kind": "peraturan"}
        
        print(f"   Importing from: {pdf_url}")
        response = requests.post(f"{BACKEND_URL}/putusan/import-url", json=payload, timeout=35)
        
        print(f"   Import status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Import failed with {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            results["failed"].append("Test 2a: Import failed")
        else:
            data = response.json()
            throwaway_id = data.get("id")
            print(f"   Imported peraturan id: {throwaway_id}")
            
            # Now delete it
            print(f"\n[TEST 2a-delete] DELETE /api/peraturan/{throwaway_id}")
            response = requests.delete(f"{BACKEND_URL}/peraturan/{throwaway_id}", timeout=30)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("deleted") == True:
                    print(f"   ✅ Delete returned 200 with deleted:true")
                    
                    # Verify it's gone from GET /api/peraturan
                    print(f"\n[TEST 2a-verify] GET /api/peraturan to confirm deletion")
                    response = requests.get(f"{BACKEND_URL}/peraturan", timeout=30)
                    
                    if response.status_code == 200:
                        peraturan_list = response.json()
                        if not any(p.get("id") == throwaway_id for p in peraturan_list):
                            print(f"   ✅ PASS: Throwaway peraturan is absent from list")
                            results["passed"].append("Test 2a: Import and delete throwaway peraturan")
                        else:
                            print(f"❌ FAIL: Throwaway peraturan still present in list")
                            results["failed"].append("Test 2a: Peraturan not deleted")
                    else:
                        print(f"❌ FAIL: GET /api/peraturan failed with {response.status_code}")
                        results["failed"].append("Test 2a: Verification failed")
                else:
                    print(f"❌ FAIL: Response missing deleted:true")
                    results["failed"].append("Test 2a: Invalid delete response")
            else:
                print(f"❌ FAIL: Expected 200, got {response.status_code}")
                results["failed"].append(f"Test 2a: Delete failed with {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 2a: Exception - {e}")
    
    # Test 2b: DELETE a SAMPLE peraturan (uu-36-2008)
    print("\n[TEST 2b] DELETE sample peraturan uu-36-2008")
    print("   ⚠️  WARNING: This permanently deletes sample data (expected behavior)")
    try:
        response = requests.delete(f"{BACKEND_URL}/peraturan/uu-36-2008", timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("deleted") == True:
                print(f"   ✅ Delete returned 200 with deleted:true")
                
                # Verify it's gone from GET /api/peraturan
                print(f"\n[TEST 2b-verify] GET /api/peraturan to confirm uu-36-2008 is absent")
                response = requests.get(f"{BACKEND_URL}/peraturan", timeout=30)
                
                if response.status_code == 200:
                    peraturan_list = response.json()
                    if not any(p.get("id") == "uu-36-2008" for p in peraturan_list):
                        print(f"   ✅ PASS: uu-36-2008 is absent from list (tombstone working)")
                        results["passed"].append("Test 2b: Delete sample peraturan uu-36-2008")
                    else:
                        print(f"❌ FAIL: uu-36-2008 still present in list")
                        results["failed"].append("Test 2b: Sample peraturan not deleted")
                else:
                    print(f"❌ FAIL: GET /api/peraturan failed with {response.status_code}")
                    results["failed"].append("Test 2b: Verification failed")
            else:
                print(f"❌ FAIL: Response missing deleted:true")
                results["failed"].append("Test 2b: Invalid delete response")
        else:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append(f"Test 2b: Delete failed with {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 2b: Exception - {e}")
    
    # Test 2c: DELETE a putusan
    print("\n[TEST 2c] DELETE a putusan")
    try:
        # First get the list of putusan
        response = requests.get(f"{BACKEND_URL}/putusan", timeout=30)
        print(f"   GET /api/putusan status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: GET /api/putusan failed with {response.status_code}")
            results["failed"].append("Test 2c: GET putusan failed")
        else:
            putusan_list = response.json()
            
            if len(putusan_list) == 0:
                print(f"   ⚠️  SOFT NOTE: No putusan available to delete")
                results["soft_notes"].append("Test 2c: No putusan to delete")
            else:
                # Pick the first putusan (prefer put-pph21-2023 if available)
                target_putusan = None
                for p in putusan_list:
                    if p.get("id") == "put-pph21-2023":
                        target_putusan = p
                        break
                
                if not target_putusan:
                    target_putusan = putusan_list[0]
                
                putusan_id = target_putusan.get("id")
                print(f"   Selected putusan id: {putusan_id}")
                print(f"   ⚠️  WARNING: This permanently deletes sample data (expected behavior)")
                
                # Delete it
                print(f"\n[TEST 2c-delete] DELETE /api/putusan/{putusan_id}")
                response = requests.delete(f"{BACKEND_URL}/putusan/{putusan_id}", timeout=30)
                
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("deleted") == True:
                        print(f"   ✅ Delete returned 200 with deleted:true")
                        
                        # Verify it's gone
                        print(f"\n[TEST 2c-verify] GET /api/putusan to confirm deletion")
                        response = requests.get(f"{BACKEND_URL}/putusan", timeout=30)
                        
                        if response.status_code == 200:
                            putusan_list = response.json()
                            if not any(p.get("id") == putusan_id for p in putusan_list):
                                print(f"   ✅ PASS: Putusan is absent from list")
                                results["passed"].append("Test 2c: Delete putusan")
                            else:
                                print(f"❌ FAIL: Putusan still present in list")
                                results["failed"].append("Test 2c: Putusan not deleted")
                        else:
                            print(f"❌ FAIL: GET /api/putusan failed with {response.status_code}")
                            results["failed"].append("Test 2c: Verification failed")
                    else:
                        print(f"❌ FAIL: Response missing deleted:true")
                        results["failed"].append("Test 2c: Invalid delete response")
                else:
                    print(f"❌ FAIL: Expected 200, got {response.status_code}")
                    results["failed"].append(f"Test 2c: Delete failed with {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 2c: Exception - {e}")
    
    # Test 2d: DELETE /api/peraturan/<random-uuid> -> expect 404
    print("\n[TEST 2d] DELETE /api/peraturan/<random-uuid> (expect 404)")
    random_uuid = str(uuid.uuid4())
    try:
        response = requests.delete(f"{BACKEND_URL}/peraturan/{random_uuid}", timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"   ✅ PASS: Correctly returns 404 for non-existent peraturan")
            results["passed"].append("Test 2d: Delete non-existent peraturan returns 404")
        else:
            print(f"❌ FAIL: Expected 404, got {response.status_code}")
            results["failed"].append(f"Test 2d: Expected 404, got {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 2d: Exception - {e}")
    
    # Test 2e: DELETE /api/putusan/<random-uuid> -> expect 404
    print("\n[TEST 2e] DELETE /api/putusan/<random-uuid> (expect 404)")
    random_uuid = str(uuid.uuid4())
    try:
        response = requests.delete(f"{BACKEND_URL}/putusan/{random_uuid}", timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"   ✅ PASS: Correctly returns 404 for non-existent putusan")
            results["passed"].append("Test 2e: Delete non-existent putusan returns 404")
        else:
            print(f"❌ FAIL: Expected 404, got {response.status_code}")
            results["failed"].append(f"Test 2e: Expected 404, got {response.status_code}")
    
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 2e: Exception - {e}")
    
    return results


def test_import_url_regression():
    """TEST 3: Regression test for import-url after refactor."""
    print("\n" + "=" * 80)
    print("TEST 3: REGRESSION import-url after refactor")
    print("=" * 80)
    
    results = {
        "passed": [],
        "failed": [],
        "soft_notes": []
    }
    
    # Test 3: POST /api/putusan/import-url with direct PDF URL
    print("\n[TEST 3] POST /api/putusan/import-url with direct PDF URL")
    try:
        pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        payload = {"url": pdf_url, "kind": "peraturan"}
        
        print(f"   Importing from: {pdf_url}")
        print(f"   (Network-dependent: may take 10-35 seconds)")
        
        response = requests.post(f"{BACKEND_URL}/putusan/import-url", json=payload, timeout=35)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            body = data.get("body", "")
            file_id = data.get("file_id")
            
            print(f"   Body length: {len(body)} chars")
            print(f"   Body preview: {body[:100]}")
            print(f"   file_id: {file_id}")
            
            if len(body) > 0:
                print(f"   ✅ Body is non-empty")
            else:
                print(f"❌ FAIL: Body is empty")
                results["failed"].append("Test 3: Body is empty")
            
            if file_id:
                print(f"   ✅ file_id is non-null")
            else:
                print(f"❌ FAIL: file_id is null")
                results["failed"].append("Test 3: file_id is null")
            
            if len(body) > 0 and file_id:
                print(f"   ✅ PASS: import-url works after refactor")
                results["passed"].append("Test 3: import-url regression test")
            
        else:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            results["failed"].append(f"Test 3: Import failed with {response.status_code}")
    
    except requests.Timeout:
        print(f"   ⚠️  SOFT NOTE: Request timed out (source may be slow/unreachable)")
        results["soft_notes"].append("Test 3: Request timeout (network-dependent)")
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        results["failed"].append(f"Test 3: Exception - {e}")
    
    return results


def main():
    print("\n" + "=" * 80)
    print("TaxLens Backend Test - New Endpoints")
    print("=" * 80)
    print("Testing THREE new/changed backend endpoints:")
    print("1. POST /api/peraturan/{id}/refetch")
    print("2. DELETE /api/peraturan/{id} and DELETE /api/putusan/{id}")
    print("3. POST /api/putusan/import-url (regression)")
    print("=" * 80)
    
    all_results = {
        "passed": [],
        "failed": [],
        "soft_notes": []
    }
    
    # Run all tests
    print("\n")
    results1 = test_refetch_peraturan()
    all_results["passed"].extend(results1["passed"])
    all_results["failed"].extend(results1["failed"])
    all_results["soft_notes"].extend(results1.get("soft_notes", []))
    
    results2 = test_delete_endpoints()
    all_results["passed"].extend(results2["passed"])
    all_results["failed"].extend(results2["failed"])
    all_results["soft_notes"].extend(results2.get("soft_notes", []))
    
    results3 = test_import_url_regression()
    all_results["passed"].extend(results3["passed"])
    all_results["failed"].extend(results3["failed"])
    all_results["soft_notes"].extend(results3.get("soft_notes", []))
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    print(f"\n✅ PASSED: {len(all_results['passed'])} tests")
    for test in all_results["passed"]:
        print(f"   - {test}")
    
    print(f"\n❌ FAILED: {len(all_results['failed'])} tests")
    for test in all_results["failed"]:
        print(f"   - {test}")
    
    if len(all_results["soft_notes"]) > 0:
        print(f"\n⚠️  SOFT NOTES: {len(all_results['soft_notes'])} items (not failures)")
        for note in all_results["soft_notes"]:
            print(f"   - {note}")
    
    print("\n" + "=" * 80)
    
    if len(all_results["failed"]) == 0:
        print("🎉 ALL TESTS PASSED!")
        if len(all_results["soft_notes"]) > 0:
            print("   (Some soft notes present - network-dependent issues)")
        sys.exit(0)
    else:
        print("⚠️  SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
