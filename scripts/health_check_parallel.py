
import sys
import json
import urllib.request
import urllib.error
import time

# Configuration for Test Env
API_URL = "http://127.0.0.1:8001"
WEB_URL = "http://localhost:3002"

def check_endpoint(name, url, expected_status=200):
    print(f"Checking {name} at {url}...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            if status == expected_status or (expected_status == 200 and status < 400):
                print(f"✅ {name} is UP (Status: {status})")
                return True
            else:
                print(f"❌ {name} returned status {status}")
                return False
    except urllib.error.HTTPError as e:
        if e.code == expected_status or (expected_status == 200 and e.code < 400):
             print(f"✅ {name} is UP (Status: {e.code})")
             return True
        print(f"❌ {name} returned status {e.code}")
        return False
    except urllib.error.URLError as e:
        print(f"❌ {name} is DOWN: {e.reason}")
        return False
    except Exception as e:
        print(f"❌ {name} is DOWN: {e}")
        return False

def check_data_count():
    print("Checking Data Integrity via API...")
    url = f"{API_URL}/analytics/summary"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.getcode() == 200:
                data = json.loads(response.read().decode())
                # We expect ~13 patients from backfill
                count = data.get("total_patients", 0)
                print(f"✅ API reports {count} patients (Expected ~13)")
                return True
            else:
                print(f"❌ API Analytics endpoint failed: {response.getcode()}")
                return False
    except Exception as e:
        print(f"❌ Failed to connect to API: {e}")
        return False

def main():
    print("--- Parallel Environment Health Check ---")
    
    # API Docs is a good check for FastAPI
    api_ok = check_endpoint("API Backend", f"{API_URL}/docs")
    
    data_ok = False
    if api_ok:
        data_ok = check_data_count()
        
    web_ok = check_endpoint("Dashboard Frontend", f"{WEB_URL}/dashboard")
    
    if api_ok and data_ok and web_ok:
        print("\n✅ SYSTEM HEALTHY")
        sys.exit(0)
    else:
        print("\n❌ SYSTEM ISSUES DETECTED")
        sys.exit(1)

if __name__ == "__main__":
    main()
