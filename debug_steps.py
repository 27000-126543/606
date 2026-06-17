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

execution_id = "549223d1-82de-4bc7-881d-c03e531baa26"

print(f"执行ID: {execution_id}")
print()

req = urllib.request.Request(
    f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    data = result.get("data", result)
    
    print("=== API 返回的完整数据 ===")
    print(f"status: {data.get('status')}")
    print(f"result_summary: {data.get('result_summary')}")
    
    step_results = data.get("step_results")
    print(f"step_results 类型: {type(step_results)}")
    print(f"step_results 数量: {len(step_results) if step_results else 0}")
    
    if step_results:
        print(f"step_results 第一个: {json.dumps(step_results[0], indent=2, ensure_ascii=False)[:200]}")
        print(f"step_results 类型: {type(step_results[0])}")
    
    print()
    print("=== 完整响应 ===")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
