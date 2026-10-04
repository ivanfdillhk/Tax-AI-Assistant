#!/usr/bin/env python3
"""
POST-IMPORT SMOKE TEST for TaxLens Backend
Tests THREE core flows after fresh environment re-import:
1. Web Search (GET /api/search)
2. AI Search (POST /api/ai-search)
3. PDF Upload/Download (POST /api/putusan/upload + GET /api/files/{id}/download)

These endpoints call live LLM (Gemini via EMERGENT_LLM_KEY) and Emergent Object Storage,
so we use generous timeouts (10-35 seconds per request).
"""
import requests
import os
import sys
import time
from pathlib import Path

# Backend URL from environment
BACKEND_URL = "https://ai-tax-helper-5.preview.emergentagent.com/api"

def test_web_search():
    """TEST 1: Web Search Engine (GET /api/search)"""
    print("\n" + "=" * 80)
    print("TEST 1: WEB SEARCH ENGINE")
    print("=" * 80)
    
    results = {"passed": [], "failed": []}
    
    # Test 1.1: Basic tax query
    print("\n[TEST 1.1] GET /api/search?q=pembatalan%20STP%20pajak&page=1")
    try:
        start_time = time.time()
        response = requests.get(
            f"{BACKEND_URL}/search",
            params={"q": "pembatalan STP pajak", "page": 1},
            timeout=35
        )
        elapsed = time.time() - start_time
        
        print(f"   Status: {response.status_code}")
        print(f"   Response time: {elapsed:.1f}s")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            results["failed"].append("Test 1.1: Basic query failed")
        else:
            data = response.json()
            print(f"   Response keys: {list(data.keys())}")
            
            # Check required top-level keys
            required_keys = ["query", "total", "totalPages", "page", "searchTime", "results"]
            missing_keys = [k for k in required_keys if k not in data]
            
            if missing_keys:
                print(f"❌ FAIL: Missing required keys: {missing_keys}")
                results["failed"].append(f"Test 1.1: Missing keys {missing_keys}")
            else:
                print(f"   ✅ All required top-level keys present")
                
                # Check results array
                results_list = data.get("results", [])
                print(f"   Results count: {len(results_list)}")
                
                if len(results_list) == 0:
                    print(f"❌ FAIL: No results returned")
                    results["failed"].append("Test 1.1: No results")
                else:
                    # Check first result has all required fields
                    first_result = results_list[0]
                    required_result_fields = ["title", "url", "displayUrl", "snippet", "source", "rank", "favicon"]
                    missing_result_fields = [f for f in required_result_fields if f not in first_result]
                    
                    if missing_result_fields:
                        print(f"❌ FAIL: Result missing fields: {missing_result_fields}")
                        results["failed"].append(f"Test 1.1: Result missing {missing_result_fields}")
                    else:
                        print(f"   ✅ All required result fields present")
                        
                        # Check URLs are real (not vertexaisearch redirects)
                        real_urls = [r for r in results_list if "vertexaisearch" not in r.get("url", "")]
                        print(f"   Real URLs (non-redirect): {len(real_urls)}/{len(results_list)}")
                        
                        if len(real_urls) == 0:
                            print(f"❌ FAIL: All URLs are vertexaisearch redirects")
                            results["failed"].append("Test 1.1: No real URLs")
                        else:
                            print(f"   ✅ Found real source URLs")
                            
                            # Show sample URLs
                            print(f"   Sample URLs:")
                            for r in results_list[:3]:
                                print(f"      - {r.get('source', 'N/A')}: {r.get('url', 'N/A')[:80]}")
                            
                            print(f"   ✅ PASS: Basic tax query works correctly")
                            results["passed"].append("Test 1.1: Basic tax query")
    
    except requests.Timeout:
        print(f"❌ FAIL: Request timeout (>35s)")
        results["failed"].append("Test 1.1: Timeout")
    except Exception as e:
        print(f"❌ FAIL: Exception - {e}")
        results["failed"].append(f"Test 1.1: Exception - {e}")
    
    # Test 1.2: General non-tax query (should return diverse sources)
    print("\n[TEST 1.2] GET /api/search?q=harga%20saham%20Astra%20Agro%20Lestari")
    try:
        start_time = time.time()
        response = requests.get(
            f"{BACKEND_URL}/search",
            params={"q": "harga saham Astra Agro Lestari", "page": 1},
            timeout=35
        )
        elapsed = time.time() - start_time
        
        print(f"   Status: {response.status_code}")
        print(f"   Response time: {elapsed:.1f}s")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 1.2: General query failed")
        else:
            data = response.json()
            results_list = data.get("results", [])
            print(f"   Results count: {len(results_list)}")
            
            if len(results_list) == 0:
                print(f"❌ FAIL: No results for general query")
                results["failed"].append("Test 1.2: No results")
            else:
                # Check for diverse sources (not forced to tax domains)
                sources = [r.get("source", "") for r in results_list]
                tax_domains = ["pajak.go.id", "kemenkeu.go.id", "peraturan.go.id"]
                non_tax_sources = [s for s in sources if not any(td in s for td in tax_domains)]
                
                print(f"   Non-tax sources: {len(non_tax_sources)}/{len(sources)}")
                print(f"   Sample sources: {sources[:5]}")
                
                if len(non_tax_sources) == 0:
                    print(f"❌ FAIL: All results forced to tax domains")
                    results["failed"].append("Test 1.2: Forced to tax domains")
                else:
                    print(f"   ✅ PASS: General query returns diverse sources (not forced to tax)")
                    results["passed"].append("Test 1.2: General non-tax query")
    
    except requests.Timeout:
        print(f"❌ FAIL: Request timeout (>35s)")
        results["failed"].append("Test 1.2: Timeout")
    except Exception as e:
        print(f"❌ FAIL: Exception - {e}")
        results["failed"].append(f"Test 1.2: Exception - {e}")
    
    # Test 1.3: Missing q parameter (should return 422)
    print("\n[TEST 1.3] GET /api/search (missing q parameter)")
    try:
        response = requests.get(f"{BACKEND_URL}/search", timeout=10)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 422:
            print(f"   ✅ PASS: Correctly returns 422 for missing q parameter")
            results["passed"].append("Test 1.3: Missing q returns 422")
        else:
            print(f"❌ FAIL: Expected 422, got {response.status_code}")
            results["failed"].append("Test 1.3: Should return 422")
    
    except Exception as e:
        print(f"❌ FAIL: Exception - {e}")
        results["failed"].append(f"Test 1.3: Exception - {e}")
    
    return results


def test_ai_search():
    """TEST 2: AI Search (POST /api/ai-search)"""
    print("\n" + "=" * 80)
    print("TEST 2: AI SEARCH")
    print("=" * 80)
    
    results = {"passed": [], "failed": []}
    
    # Test 2.1: Valid question
    print("\n[TEST 2.1] POST /api/ai-search with valid question")
    try:
        start_time = time.time()
        response = requests.post(
            f"{BACKEND_URL}/ai-search",
            json={"q": "Apakah STP bisa dibatalkan?"},
            timeout=35
        )
        elapsed = time.time() - start_time
        
        print(f"   Status: {response.status_code}")
        print(f"   Response time: {elapsed:.1f}s")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            results["failed"].append("Test 2.1: Valid question failed")
        else:
            data = response.json()
            print(f"   Response keys: {list(data.keys())}")
            
            # Check required keys
            required_keys = ["query", "answer", "sources", "searchTime"]
            missing_keys = [k for k in required_keys if k not in data]
            
            if missing_keys:
                print(f"❌ FAIL: Missing required keys: {missing_keys}")
                results["failed"].append(f"Test 2.1: Missing keys {missing_keys}")
            else:
                print(f"   ✅ All required keys present")
                
                # Check answer has citation markers
                answer = data.get("answer", "")
                print(f"   Answer length: {len(answer)} chars")
                
                # Find all [n] citation markers
                import re
                citation_markers = re.findall(r'\[(\d+)\]', answer)
                print(f"   Citation markers found: {len(citation_markers)} - {citation_markers[:10]}")
                
                # Check sources
                sources = data.get("sources", [])
                print(f"   Sources count: {len(sources)}")
                
                if len(sources) == 0:
                    print(f"❌ FAIL: No sources returned")
                    results["failed"].append("Test 2.1: No sources")
                else:
                    # Check first source has required fields
                    first_source = sources[0]
                    required_source_fields = ["number", "title", "url", "displayUrl", "source", "favicon"]
                    missing_source_fields = [f for f in required_source_fields if f not in first_source]
                    
                    if missing_source_fields:
                        print(f"❌ FAIL: Source missing fields: {missing_source_fields}")
                        results["failed"].append(f"Test 2.1: Source missing {missing_source_fields}")
                    else:
                        print(f"   ✅ All required source fields present")
                        
                        # Check all citation markers reference valid source numbers
                        source_numbers = [s.get("number") for s in sources]
                        print(f"   Source numbers: {source_numbers}")
                        
                        invalid_citations = [int(m) for m in citation_markers if int(m) not in source_numbers]
                        
                        if invalid_citations:
                            print(f"❌ FAIL: Invalid citation markers (no matching source): {invalid_citations}")
                            results["failed"].append("Test 2.1: Dangling citations")
                        else:
                            print(f"   ✅ All citation markers reference valid sources")
                            
                            # Show sample sources
                            print(f"   Sample sources:")
                            for s in sources[:3]:
                                print(f"      [{s.get('number')}] {s.get('source', 'N/A')}: {s.get('url', 'N/A')[:80]}")
                            
                            print(f"   ✅ PASS: AI search works correctly")
                            results["passed"].append("Test 2.1: Valid question")
    
    except requests.Timeout:
        print(f"❌ FAIL: Request timeout (>35s)")
        results["failed"].append("Test 2.1: Timeout")
    except Exception as e:
        print(f"❌ FAIL: Exception - {e}")
        results["failed"].append(f"Test 2.1: Exception - {e}")
    
    # Test 2.2: Empty question (should return 400)
    print("\n[TEST 2.2] POST /api/ai-search with empty question")
    try:
        response = requests.post(
            f"{BACKEND_URL}/ai-search",
            json={"q": ""},
            timeout=10
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 400:
            print(f"   ✅ PASS: Correctly returns 400 for empty question")
            results["passed"].append("Test 2.2: Empty question returns 400")
        else:
            print(f"❌ FAIL: Expected 400, got {response.status_code}")
            results["failed"].append("Test 2.2: Should return 400")
    
    except Exception as e:
        print(f"❌ FAIL: Exception - {e}")
        results["failed"].append(f"Test 2.2: Exception - {e}")
    
    return results


def test_pdf_upload_download():
    """TEST 3: PDF Upload/Download"""
    print("\n" + "=" * 80)
    print("TEST 3: PDF UPLOAD/DOWNLOAD")
    print("=" * 80)
    
    results = {"passed": [], "failed": []}
    
    # Test 3.1: Upload PDF
    print("\n[TEST 3.1] POST /api/putusan/upload with PDF")
    test_pdf_path = "/app/test_putusan_header.pdf"
    
    if not os.path.exists(test_pdf_path):
        print(f"❌ FAIL: Test PDF file not found at {test_pdf_path}")
        results["failed"].append("Test 3.1: PDF file not found")
        return results
    
    with open(test_pdf_path, "rb") as f:
        pdf_bytes = f.read()
        pdf_size = len(pdf_bytes)
    
    try:
        with open(test_pdf_path, "rb") as f:
            files = {"file": ("test_putusan_header.pdf", f, "application/pdf")}
            response = requests.post(f"{BACKEND_URL}/putusan/upload", files=files, timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            results["failed"].append("Test 3.1: Upload failed")
            return results
        
        data = response.json()
        
        # Check required fields
        if "file_id" not in data:
            print(f"❌ FAIL: Response missing 'file_id' field")
            results["failed"].append("Test 3.1: Missing file_id")
            return results
        
        if "original_filename" not in data:
            print(f"❌ FAIL: Response missing 'original_filename' field")
            results["failed"].append("Test 3.1: Missing original_filename")
            return results
        
        if not data["original_filename"].endswith(".pdf"):
            print(f"❌ FAIL: original_filename should end with .pdf, got: {data['original_filename']}")
            results["failed"].append("Test 3.1: Invalid filename")
            return results
        
        file_id = data["file_id"]
        original_filename = data["original_filename"]
        
        print(f"   ✅ PASS: Upload successful")
        print(f"   file_id: {file_id}")
        print(f"   original_filename: {original_filename}")
        results["passed"].append("Test 3.1: Upload PDF")
        
    except Exception as e:
        print(f"❌ FAIL: Exception during upload: {e}")
        results["failed"].append(f"Test 3.1: Exception - {e}")
        return results
    
    # Test 3.2: Download with default (attachment)
    print("\n[TEST 3.2] GET /api/files/{file_id}/download (default attachment)")
    try:
        response = requests.get(f"{BACKEND_URL}/files/{file_id}/download", timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 3.2: Download failed")
        else:
            # Check Content-Type
            content_type = response.headers.get("Content-Type", "")
            print(f"   Content-Type: {content_type}")
            
            if "application/pdf" not in content_type:
                print(f"❌ FAIL: Expected Content-Type to contain 'application/pdf'")
                results["failed"].append("Test 3.2: Wrong Content-Type")
            else:
                print(f"   ✅ Content-Type is correct")
            
            # Check Content-Disposition
            content_disposition = response.headers.get("Content-Disposition", "")
            print(f"   Content-Disposition: {content_disposition}")
            
            if not content_disposition.startswith("attachment"):
                print(f"❌ FAIL: Expected Content-Disposition to start with 'attachment'")
                results["failed"].append("Test 3.2: Content-Disposition not attachment")
            else:
                print(f"   ✅ Content-Disposition starts with 'attachment'")
            
            # Check response body size
            response_size = len(response.content)
            print(f"   Response body size: {response_size} bytes (uploaded: {pdf_size} bytes)")
            
            if response_size != pdf_size:
                print(f"❌ FAIL: Response size doesn't match uploaded size")
                results["failed"].append("Test 3.2: Size mismatch")
            else:
                print(f"   ✅ Response size matches uploaded file")
            
            # If all checks passed
            if "application/pdf" in content_type and content_disposition.startswith("attachment") and response_size == pdf_size:
                print(f"   ✅ PASS: Download with attachment works correctly")
                results["passed"].append("Test 3.2: Download (attachment)")
    
    except Exception as e:
        print(f"❌ FAIL: Exception during download: {e}")
        results["failed"].append(f"Test 3.2: Exception - {e}")
    
    # Test 3.3: Download with inline=1
    print("\n[TEST 3.3] GET /api/files/{file_id}/download?inline=1")
    try:
        response = requests.get(f"{BACKEND_URL}/files/{file_id}/download?inline=1", timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 3.3: Download with inline=1 failed")
        else:
            # Check Content-Disposition
            content_disposition = response.headers.get("Content-Disposition", "")
            print(f"   Content-Disposition: {content_disposition}")
            
            if not content_disposition.startswith("inline"):
                print(f"❌ FAIL: Expected Content-Disposition to start with 'inline'")
                results["failed"].append("Test 3.3: Content-Disposition not inline")
            else:
                print(f"   ✅ PASS: Download with inline=1 works correctly")
                results["passed"].append("Test 3.3: Download (inline)")
    
    except Exception as e:
        print(f"❌ FAIL: Exception during download with inline=1: {e}")
        results["failed"].append(f"Test 3.3: Exception - {e}")
    
    # Test 3.4: Non-existent file (should return 404)
    print("\n[TEST 3.4] GET /api/files/{random-uuid}/download (should return 404)")
    random_uuid = "00000000-0000-0000-0000-000000000000"
    
    try:
        response = requests.get(f"{BACKEND_URL}/files/{random_uuid}/download", timeout=10)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"   ✅ PASS: Correctly returns 404 for non-existent file")
            results["passed"].append("Test 3.4: Non-existent file returns 404")
        else:
            print(f"❌ FAIL: Expected 404, got {response.status_code}")
            results["failed"].append("Test 3.4: Should return 404")
    
    except Exception as e:
        print(f"❌ FAIL: Exception during 404 test: {e}")
        results["failed"].append(f"Test 3.4: Exception - {e}")
    
    return results


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TAXLENS POST-IMPORT SMOKE TEST")
    print("Testing THREE core flows after fresh environment re-import")
    print("=" * 80)
    
    all_results = {"passed": [], "failed": []}
    
    # Run all three tests
    test1_results = test_web_search()
    all_results["passed"].extend(test1_results["passed"])
    all_results["failed"].extend(test1_results["failed"])
    
    test2_results = test_ai_search()
    all_results["passed"].extend(test2_results["passed"])
    all_results["failed"].extend(test2_results["failed"])
    
    test3_results = test_pdf_upload_download()
    all_results["passed"].extend(test3_results["passed"])
    all_results["failed"].extend(test3_results["failed"])
    
    # Print final summary
    print("\n" + "=" * 80)
    print("FINAL TEST SUMMARY")
    print("=" * 80)
    
    print(f"\n✅ PASSED: {len(all_results['passed'])} tests")
    for test in all_results["passed"]:
        print(f"   - {test}")
    
    print(f"\n❌ FAILED: {len(all_results['failed'])} tests")
    for test in all_results["failed"]:
        print(f"   - {test}")
    
    print("\n" + "=" * 80)
    
    if len(all_results["failed"]) == 0:
        print("🎉 ALL SMOKE TESTS PASSED!")
        print("Backend is working correctly after re-import.")
        sys.exit(0)
    else:
        print("⚠️  SOME SMOKE TESTS FAILED")
        print("Please review the failures above.")
        sys.exit(1)
