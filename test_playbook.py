import urllib.request
import json
import urllib.error
import time


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

# 配置回滚预案ID
playbook_id = "a293b9ec-51a4-40fd-abb5-7c9c04b52b5b"
# 工单ID
work_order_id = "bed30c7b-a6c5-430d-8435-189988b450ef"
anomaly_id = "ebdb213e-1e9a-4084-92af-f221d9de1417"

print("=== 执行预案 ===")
print(f"预案ID: {playbook_id}")
print(f"工单ID: {work_order_id}")
print(f"异常ID: {anomaly_id}")
print()

# 先查看工单和异常的初始状态
print("=== 初始状态 ===")
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/work-orders/{work_order_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"工单状态: {result['data']['status']}")
except urllib.error.HTTPError as e:
    print(f"工单查询失败: {e.code}")
    print(e.read().decode())

req = urllib.request.Request(
    f"http://localhost:8000/api/v1/anomalies/{anomaly_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"异常状态: {result['data']['status']}")
except urllib.error.HTTPError as e:
    print(f"异常查询失败: {e.code}")
    print(e.read().decode())

print()

# 执行预案
print("=== 启动预案执行 ===")
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
        print(f"✅ 预案执行已启动")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        execution_id = result["data"]["execution_id"]
        print()
        print("=== 等待执行完成 ===")
        
        # 等待执行完成
        for i in range(15):
            time.sleep(2)
            req = urllib.request.Request(
                f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode())
                    data = result["data"]
                    status = data.get("status", "unknown")
                    print(f"  第{i+1}次检查: status={status}")
                    
                    if status in ("success", "failed", "rolled_back", "rejected"):
                        print()
                        print("=== 执行完成 ===")
                        print(f"状态: {status}")
                        print(f"结果摘要: {data.get('result_summary', 'N/A')}")
                        print(f"验证结果: {data.get('verification_result', 'N/A')}")
                        print(f"验证备注: {data.get('verification_note', 'N/A')}")
                        
                        step_results = data.get("step_results", [])
                        print(f"步骤数: {len(step_results)}")
                        for step in step_results:
                            print(f"  - {step.get('step_name', 'N/A')}: {'成功' if step.get('success') else '失败'}")
                        
                        # 检查工单状态
                        print()
                        print("=== 执行后工单状态 ===")
                        req = urllib.request.Request(
                            f"http://localhost:8000/api/v1/work-orders/{work_order_id}",
                            headers={"Authorization": f"Bearer {admin_token}"}
                        )
                        with urllib.request.urlopen(req) as resp:
                            result = json.loads(resp.read().decode())
                            print(f"工单状态: {result['data']['status']}")
                        
                        # 检查异常状态
                        print()
                        print("=== 执行后异常状态 ===")
                        req = urllib.request.Request(
                            f"http://localhost:8000/api/v1/anomalies/{anomaly_id}",
                            headers={"Authorization": f"Bearer {admin_token}"}
                        )
                        with urllib.request.urlopen(req) as resp:
                            result = json.loads(resp.read().decode())
                            print(f"异常状态: {result['data']['status']}")
                        
                        break
            except Exception as e:
                print(f"  查询执行状态失败: {e}")
        else:
            print("  等待超时")
            
except urllib.error.HTTPError as e:
    print(f"❌ {e.code}")
    print(e.read().decode())
