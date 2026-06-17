import urllib.request
import json


def login(username, password):
    url = "http://localhost:8000/api/v1/auth/login"
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        return result["data"]["access_token"]


def test_get(url, token):
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"✅ {url}")
            print(f"   Keys: {list(data.keys())[:5]}")
            if "total" in data:
                print(f"   Total: {data['total']}")
            if "data" in data and isinstance(data["data"], list):
                print(f"   Data count: {len(data['data'])}")
            return data, None
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode())
        print(f"❌ {url}")
        print(f"   Status: {e.code}")
        print(f"   Error: {err.get('detail', err.get('message', str(err)))}")
        return None, err


admin_token = login("admin", "Admin@123456")
operator_token = login("operator1", "Oper@123")
print("Tokens obtained")

print("\n" + "=" * 60)
print("测试接口列表")
print("=" * 60)

print("\n--- 主管账号 (admin) ---")
test_get("http://localhost:8000/api/v1/auth/me", admin_token)
test_get("http://localhost:8000/api/v1/anomalies?page=1&page_size=5", admin_token)
test_get("http://localhost:8000/api/v1/work-orders?page=1&page_size=5", admin_token)
test_get("http://localhost:8000/api/v1/playbooks?page=1&page_size=5", admin_token)
test_get("http://localhost:8000/api/v1/reports/daily?page=1&page_size=5", admin_token)

print("\n--- 运维账号 (operator1) ---")
test_get("http://localhost:8000/api/v1/auth/me", operator_token)
test_get("http://localhost:8000/api/v1/anomalies?page=1&page_size=5", operator_token)
test_get("http://localhost:8000/api/v1/work-orders?page=1&page_size=5", operator_token)

print("\n" + "=" * 60)
