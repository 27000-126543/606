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

# 测试日报生成
print("=== 生成日报 ===")
req = urllib.request.Request(
    "http://localhost:8000/api/v1/query/reports/daily/generate",
    data=b"{}",
    method="POST",
    headers={
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    print(f"状态码: {resp.status}")
    print("完整响应:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
