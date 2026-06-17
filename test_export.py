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

# 获取报表列表
print("--- 报表列表 (/reports/daily) ---")
req = urllib.request.Request(
    "http://localhost:8000/api/v1/query/reports/daily?page_size=1",
    headers={"Authorization": f"Bearer {admin_token}"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"✅ 成功，total: {result.get('total', 'N/A')}")
        if result.get("data"):
            report_id = result["data"][0]["id"]
            print(f"  报表ID: {report_id}")
            
            print()
            print("--- 测试 PDF 导出 ---")
            req = urllib.request.Request(
                f"http://localhost:8000/api/v1/query/reports/{report_id}/export/pdf",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    content = resp.read()
                    print(f"✅ PDF导出成功，文件大小: {len(content)} bytes")
                    print(f"  Content-Type: {resp.headers.get('Content-Type')}")
            except urllib.error.HTTPError as e:
                print(f"❌ {e.code}")
                print(e.read().decode())
            
            print()
            print("--- 测试 Excel 导出 ---")
            req = urllib.request.Request(
                f"http://localhost:8000/api/v1/query/reports/{report_id}/export/excel",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    content = resp.read()
                    print(f"✅ Excel导出成功，文件大小: {len(content)} bytes")
                    print(f"  Content-Type: {resp.headers.get('Content-Type')}")
            except urllib.error.HTTPError as e:
                print(f"❌ {e.code}")
                print(e.read().decode())
except urllib.error.HTTPError as e:
    print(f"❌ {e.code}")
    print(e.read().decode())
