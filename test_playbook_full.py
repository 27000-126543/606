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
work_order_id = "627f8d0f-1a68-4f49-b8d7-1d5821fac212"
anomaly_id = "25e7772b-7503-42f2-91c6-09a3b1812b0e"

print("=== 初始状态 ===")
# 获取工单初始状态
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/work-orders/{work_order_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    wo_data = result.get("data", result)
    print(f"工单状态: {wo_data.get('status')}")
    print(f"playbook_executed: {wo_data.get('playbook_executed')}")

# 获取异常初始状态
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/anomalies/{anomaly_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        anom_data = result.get("data", result)
        print(f"异常状态: {anom_data.get('status')}")
except urllib.error.HTTPError as e:
    print(f"异常查询失败: {e.code}")

print()
print("=== 启动预案执行 ===")

# 执行预案
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
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    execution_id = result["data"]["execution_id"]
    print(f"执行ID: {execution_id}")
    print(f"初始状态: {result['data']['status']}")

print()
print("=== 等待执行完成 ===")

# 等待执行完成
for i in range(20):
    time.sleep(2)
    req = urllib.request.Request(
        f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            data = result.get("data", result)
            status = data.get("status", "unknown")
            print(f"  第{i+1}次检查: status={status}")
            
            if status in ("success", "failed", "rolled_back", "rejected"):
                print()
                print("=== 执行完成 ===")
                print(f"状态: {status}")
                print(f"结果摘要: {data.get('result_summary', 'N/A')}")
                print(f"验证结果: {data.get('verification_result', 'N/A')}")
                print(f"验证备注: {data.get('verification_note', 'N/A')}")
                print(f"错误信息: {data.get('error_message', 'N/A')}")
                
                step_results = data.get("step_results", [])
                print(f"步骤数: {len(step_results)}")
                for step in step_results:
                    print(f"  - {step.get('step_name', 'N/A')}: {'成功' if step.get('success') else '失败'}")
                    if not step.get("success") and step.get("error_message"):
                        print(f"    错误: {step.get('error_message')}")
                
                # 检查工单状态
                print()
                print("=== 执行后工单状态 ===")
                req = urllib.request.Request(
                    f"http://localhost:8000/api/v1/work-orders/{work_order_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode())
                    wo_data = result.get("data", result)
                    print(f"工单状态: {wo_data.get('status')}")
                    print(f"playbook_executed: {wo_data.get('playbook_executed')}")
                    print(f"解决时间: {wo_data.get('resolved_at', 'N/A')}")
                
                # 检查异常状态
                print()
                print("=== 执行后异常状态 ===")
                req = urllib.request.Request(
                    f"http://localhost:8000/api/v1/anomalies/{anomaly_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                try:
                    with urllib.request.urlopen(req) as resp:
                        result = json.loads(resp.read().decode())
                        anom_data = result.get("data", result)
                        print(f"异常状态: {anom_data.get('status')}")
                        print(f"解决方式: {anom_data.get('resolution_method', 'N/A')}")
                except urllib.error.HTTPError as e:
                    print(f"异常查询失败: {e.code}")
                    print(e.read().decode())
                
                break
    except Exception as e:
        print(f"  查询执行状态失败: {e}")
else:
    print("  等待超时")
