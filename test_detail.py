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


def get(url, token):
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, json.loads(e.read().decode()))


def post(url, token, data=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else b"{}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, json.loads(e.read().decode()))


admin_token = login("admin", "Admin@123456")
operator_token = login("operator1", "Oper@123")

print("=" * 60)
print("测试权限过滤和接口格式")
print("=" * 60)

# 获取一个异常ID
anomalies, _ = get("http://localhost:8000/api/v1/anomalies?page_size=1", admin_token)
anomaly_id = anomalies["data"][0]["id"]
print(f"\n测试用异常ID: {anomaly_id}")

# 获取一个工单ID
orders, _ = get("http://localhost:8000/api/v1/work-orders?page_size=1", admin_token)
order_id = orders["data"][0]["id"]
print(f"测试用工单ID: {order_id}")

print("\n--- 1. 异常详情权限测试 ---")
print("主管账号:")
result, err = get(f"http://localhost:8000/api/v1/anomalies/{anomaly_id}", admin_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功")
    print(f"  Keys: {list(result.keys())[:8]}")

print("运维账号:")
result, err = get(f"http://localhost:8000/api/v1/anomalies/{anomaly_id}", operator_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功 (说明运维能看到这个异常)")

print("\n--- 2. 根因分析接口测试 ---")
print("主管账号:")
result, err = post(f"http://localhost:8000/api/v1/anomalies/{anomaly_id}/analyze", admin_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功")
    print(f"  Keys: {list(result.keys())}")
    if "data" in result:
        print(f"  data keys: {list(result['data'].keys()) if isinstance(result['data'], dict) else 'N/A'}")

print("\n--- 3. 工单详情权限测试 ---")
print("主管账号:")
result, err = get(f"http://localhost:8000/api/v1/work-orders/{order_id}", admin_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功")
    print(f"  Keys: {list(result.keys())[:8]}")

print("\n--- 4. 日报生成测试 ---")
print("生成日报:")
result, err = post("http://localhost:8000/api/v1/query/reports/daily/generate", admin_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功")
    print(f"  结果: {str(result)[:200]}")

print("\n--- 5. 日报列表测试 ---")
result, err = get("http://localhost:8000/api/v1/query/reports/daily", admin_token)
if err:
    print(f"  ❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"  ✅ 成功")
    print(f"  total: {result.get('total', 'N/A')}")

print("\n" + "=" * 60)
