#!/usr/bin/env python3
"""
Backend test for TaxLens inline PDF download feature.
Tests GET /api/files/{file_id}/download with optional ?inline=1 parameter.
"""
import requests
import os
import sys
from pathlib import Path

# Backend URL from environment
BACKEND_URL = "https://tax-assistant-ai-1.preview.emergentagent.com/api"

def test_inline_pdf_download():
    """Test the new inline PDF download feature."""
    print("=" * 80)
    print("TESTING: Inline PDF Download Feature")
    print("=" * 80)
    
    results = {
        "passed": [],
        "failed": []
    }
    
    # Test 1: Upload a PDF putusan
    print("\n[TEST 1] Upload PDF putusan via POST /api/putusan/upload")
    test_pdf_path = "/app/test_putusan_header.pdf"
    
    if not os.path.exists(test_pdf_path):
        print(f"❌ FAIL: Test PDF file not found at {test_pdf_path}")
        results["failed"].append("Test 1: PDF file not found")
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
            results["failed"].append("Test 1: Upload failed")
            return results
        
        data = response.json()
        print(f"   Response keys: {list(data.keys())}")
        
        # Check required fields
        if "id" not in data:
            print("❌ FAIL: Response missing 'id' field")
            results["failed"].append("Test 1: Missing id field")
            return results
        
        if "file_id" not in data:
            print("❌ FAIL: Response missing 'file_id' field")
            results["failed"].append("Test 1: Missing file_id field")
            return results
        
        if "original_filename" not in data:
            print("❌ FAIL: Response missing 'original_filename' field")
            results["failed"].append("Test 1: Missing original_filename field")
            return results
        
        if not data["original_filename"].endswith(".pdf"):
            print(f"❌ FAIL: original_filename should end with .pdf, got: {data['original_filename']}")
            results["failed"].append("Test 1: Invalid filename")
            return results
        
        file_id = data["file_id"]
        original_filename = data["original_filename"]
        
        print(f"   ✅ PASS: Upload successful")
        print(f"   file_id: {file_id}")
        print(f"   original_filename: {original_filename}")
        results["passed"].append("Test 1: Upload PDF putusan")
        
    except Exception as e:
        print(f"❌ FAIL: Exception during upload: {e}")
        results["failed"].append(f"Test 1: Exception - {e}")
        return results
    
    # Test 2: Download with inline=1 parameter
    print("\n[TEST 2] GET /api/files/{file_id}/download?inline=1")
    try:
        response = requests.get(f"{BACKEND_URL}/files/{file_id}/download?inline=1", timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 2: Download with inline=1 failed")
        else:
            # Check Content-Type
            content_type = response.headers.get("Content-Type", "")
            print(f"   Content-Type: {content_type}")
            
            if "application/pdf" not in content_type:
                print(f"❌ FAIL: Expected Content-Type to contain 'application/pdf', got: {content_type}")
                results["failed"].append("Test 2: Wrong Content-Type")
            else:
                print(f"   ✅ Content-Type is correct")
            
            # Check Content-Disposition
            content_disposition = response.headers.get("Content-Disposition", "")
            print(f"   Content-Disposition: {content_disposition}")
            
            if not content_disposition.startswith("inline"):
                print(f"❌ FAIL: Expected Content-Disposition to start with 'inline', got: {content_disposition}")
                results["failed"].append("Test 2: Content-Disposition not inline")
            else:
                print(f"   ✅ Content-Disposition starts with 'inline'")
            
            # Check response body size
            response_size = len(response.content)
            print(f"   Response body size: {response_size} bytes (uploaded: {pdf_size} bytes)")
            
            if response_size != pdf_size:
                print(f"❌ FAIL: Response size {response_size} doesn't match uploaded size {pdf_size}")
                results["failed"].append("Test 2: Size mismatch")
            else:
                print(f"   ✅ Response size matches uploaded file")
            
            # If all checks passed
            if "application/pdf" in content_type and content_disposition.startswith("inline") and response_size == pdf_size:
                print(f"   ✅ PASS: Download with inline=1 works correctly")
                results["passed"].append("Test 2: Download with inline=1")
            
    except Exception as e:
        print(f"❌ FAIL: Exception during download with inline=1: {e}")
        results["failed"].append(f"Test 2: Exception - {e}")
    
    # Test 3: Download without inline parameter (default attachment)
    print("\n[TEST 3] GET /api/files/{file_id}/download (no inline param)")
    try:
        response = requests.get(f"{BACKEND_URL}/files/{file_id}/download", timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 3: Download without inline failed")
        else:
            # Check Content-Disposition
            content_disposition = response.headers.get("Content-Disposition", "")
            print(f"   Content-Disposition: {content_disposition}")
            
            if not content_disposition.startswith("attachment"):
                print(f"❌ FAIL: Expected Content-Disposition to start with 'attachment', got: {content_disposition}")
                results["failed"].append("Test 3: Content-Disposition not attachment")
            else:
                print(f"   ✅ PASS: Content-Disposition starts with 'attachment' (default behavior)")
                results["passed"].append("Test 3: Download without inline param")
            
    except Exception as e:
        print(f"❌ FAIL: Exception during download without inline: {e}")
        results["failed"].append(f"Test 3: Exception - {e}")
    
    # Test 4: Upload PDF peraturan and test inline download
    print("\n[TEST 4] Upload PDF peraturan via POST /api/peraturan/upload")
    test_pdf_path2 = "/app/test_table.pdf"
    
    try:
        with open(test_pdf_path2, "rb") as f:
            pdf_bytes2 = f.read()
            pdf_size2 = len(pdf_bytes2)
        
        with open(test_pdf_path2, "rb") as f:
            files = {"file": ("test_table.pdf", f, "application/pdf")}
            response = requests.post(f"{BACKEND_URL}/peraturan/upload", files=files, timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            results["failed"].append("Test 4: Peraturan upload failed")
        else:
            data = response.json()
            
            if "file_id" not in data:
                print("❌ FAIL: Response missing 'file_id' field")
                results["failed"].append("Test 4: Missing file_id")
            else:
                peraturan_file_id = data["file_id"]
                print(f"   ✅ Upload successful, file_id: {peraturan_file_id}")
                
                # Test inline download for peraturan
                print(f"\n[TEST 4b] GET /api/files/{peraturan_file_id}/download?inline=1")
                response = requests.get(f"{BACKEND_URL}/files/{peraturan_file_id}/download?inline=1", timeout=30)
                
                print(f"   Status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"❌ FAIL: Expected 200, got {response.status_code}")
                    results["failed"].append("Test 4: Peraturan inline download failed")
                else:
                    content_disposition = response.headers.get("Content-Disposition", "")
                    content_type = response.headers.get("Content-Type", "")
                    
                    print(f"   Content-Disposition: {content_disposition}")
                    print(f"   Content-Type: {content_type}")
                    
                    if content_disposition.startswith("inline") and "application/pdf" in content_type:
                        print(f"   ✅ PASS: Peraturan inline download works correctly")
                        results["passed"].append("Test 4: Peraturan inline download")
                    else:
                        print(f"❌ FAIL: Content-Disposition or Content-Type incorrect")
                        results["failed"].append("Test 4: Peraturan inline headers incorrect")
        
    except Exception as e:
        print(f"❌ FAIL: Exception during peraturan test: {e}")
        results["failed"].append(f"Test 4: Exception - {e}")
    
    # Test 5: Edge case - non-existent file_id
    print("\n[TEST 5] GET /api/files/{random-uuid}/download?inline=1 (edge case)")
    random_uuid = "00000000-0000-0000-0000-000000000000"
    
    try:
        response = requests.get(f"{BACKEND_URL}/files/{random_uuid}/download?inline=1", timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"   ✅ PASS: Correctly returns 404 for non-existent file")
            results["passed"].append("Test 5: Edge case 404")
        else:
            print(f"❌ FAIL: Expected 404, got {response.status_code}")
            results["failed"].append("Test 5: Should return 404")
            
    except Exception as e:
        print(f"❌ FAIL: Exception during edge case test: {e}")
        results["failed"].append(f"Test 5: Exception - {e}")
    
    return results


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TaxLens Backend Test - Inline PDF Download Feature")
    print("=" * 80)
    
    results = test_inline_pdf_download()
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    print(f"\n✅ PASSED: {len(results['passed'])} tests")
    for test in results["passed"]:
        print(f"   - {test}")
    
    print(f"\n❌ FAILED: {len(results['failed'])} tests")
    for test in results["failed"]:
        print(f"   - {test}")
    
    print("\n" + "=" * 80)
    
    if len(results["failed"]) == 0:
        print("🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("⚠️  SOME TESTS FAILED")
        sys.exit(1)
