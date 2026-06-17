import urllib.request
import json
import urllib.error


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


def test_url(url, token, method="GET", data=None):
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(data).encode()
    else:
        data_bytes = None
    
    req = urllib.request.Request(url, data=data_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"✅ {method} {url}")
            if isinstance(result, dict) and "total" in result:
                print(f"   total: {result['total']}")
            if isinstance(result, dict) and "data" in result and isinstance(result["data"], list):
                print(f"   data count: {len(result['data'])}")
            return True
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode())
        print(f"❌ {method} {url} -> {e.code}")
        print(f"   {err.get('detail', err.get('message', str(err)))}")
        return False


admin_token = login("admin", "Admin@123456")
operator_token = login("operator1", "Oper@123")

print("=" * 60)
print("测试路由路径")
print("=" * 60)

print("\n--- 报表相关 ---")
test_url("http://localhost:8000/api/v1/query/reports/daily", admin_token)
test_url("http://localhost:8000/api/v1/reports/daily", admin_token)

print("\n--- 预案相关 ---")
test_url("http://localhost:8000/api/v1/playbooks", admin_token)
test_url("http://localhost:8000/api/v1/work-orders/playbooks", admin_token)
test_url("http://localhost:8000/api/v1/query/playbooks", admin_token)

print("\n--- 异常列表 (验证权限过滤) ---")
test_url("http://localhost:8000/api/v1/anomalies?page_size=5", admin_token)
test_url("http://localhost:8000/api/v1/anomalies?page_size=5", operator_token)

print("\n--- 工单列表 (验证权限过滤) ---")
test_url("http://localhost:8000/api/v1/work-orders?page_size=5", admin_token)
test_url("http://localhost:8000/api/v1/work-orders?page_size=5", operator_token)

print("\n" + "=" * 60)
