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


admin_token = login("admin", "Admin@123456")

work_order_id = "bed30c7b-a6c5-430d-8435-189988b450ef"

print("=== 工单详情 ===")
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/work-orders/{work_order_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"状态码: {resp.status}")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:800])
except urllib.error.HTTPError as e:
    print(f"❌ {e.code}")
    print(e.read().decode())

print()
print("=== 测试预案执行 ===")

playbook_id = "a293b9ec-51a4-40fd-abb5-7c9c04b52b5b"
anomaly_id = "ebdb213e-1e9a-4084-92af-f221d9de1417"

req = urllib.request.Request(
    "http://localhost:8000/api/v1/playbooks/execute",
    data=json.dumps({
        "playbook_id": playbook_id,
        "work_order_id": work_order_id,
        "anomaly_id": anomaly_id,
        "parameters": {}
    }).encode(),
    method="POST",
    headers={
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"✅ 状态码: {resp.status}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(f"❌ {e.code}")
    print(e.read().decode())
