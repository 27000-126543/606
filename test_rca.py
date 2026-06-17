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

# 获取异常ID
req = urllib.request.Request(
    "http://localhost:8000/api/v1/anomalies?page_size=1",
    headers={"Authorization": f"Bearer {admin_token}"}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    anomaly_id = result["data"][0]["id"]

print(f"异常ID: {anomaly_id}")
print()

# 根因分析
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/anomalies/{anomaly_id}/analyze",
    data=b"{}",
    method="POST",
    headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print("✅ 根因分析成功")
        print()
        print("完整响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(f"❌ {e.code}")
    print(e.read().decode())
