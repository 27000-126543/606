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

# 缓存清理预案（不需要审批）
playbook_id = "6c641365-7ea5-4a01-8802-611873b89ec6"
# 工单ID
work_order_id = "bed30c7b-a6c5-430d-8435-189988b450ef"
anomaly_id = "ebdb213e-1e9a-4084-92af-f221d9de1417"

print("=" * 60)
print("预案执行 - 验证通过测试")
print("=" * 60)
print()

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
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    anom_data = result.get("data", result)
    print(f"异常状态: {anom_data.get('status')}")

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
                print("=" * 60)
                print("执行完成 - 详细结果")
                print("=" * 60)
                print(f"状态: {status}")
                print(f"结果摘要: {data.get('result_summary', 'N/A')}")
                print(f"验证结果: {data.get('verification_result', 'N/A')}")
                print(f"验证备注: {data.get('verification_note', 'N/A')}")
                print(f"错误码: {data.get('error_code', 'N/A')}")
                print(f"错误信息: {data.get('error_message', 'N/A')}")
                print(f"是否需要回滚: {data.get('is_rollback_needed', 'N/A')}")
                print(f"回滚结果: {data.get('rollback_result', 'N/A')}")
                
                step_results = data.get("step_results") or []
                print(f"步骤数: {len(step_results)}")
                for step in step_results:
                    step_name = step.get("step_name", "未知")
                    success = step.get("success", False)
                    status_str = "✅ 成功" if success else "❌ 失败"
                    print(f"  {status_str} {step_name}")
                    if not success and step.get("error_message"):
                        print(f"     错误: {step.get('error_message')}")
                
                # 检查工单状态
                print()
                print("=" * 60)
                print("执行后 - 工单状态")
                print("=" * 60)
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
                    print(f"实际解决时长: {wo_data.get('actual_resolution_minutes', 'N/A')} 分钟")
                
                # 检查异常状态
                print()
                print("=" * 60)
                print("执行后 - 异常状态")
                print("=" * 60)
                req = urllib.request.Request(
                    f"http://localhost:8000/api/v1/anomalies/{anomaly_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode())
                    anom_data = result.get("data", result)
                    print(f"异常状态: {anom_data.get('status')}")
                    print(f"解决方式: {anom_data.get('resolution_method', 'N/A')}")
                    print(f"解决备注: {anom_data.get('resolution_note', 'N/A')}")
                
                break
    except Exception as e:
        print(f"  查询执行状态失败: {e}")
else:
    print("  等待超时")
