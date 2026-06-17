import urllib.request
import json
import urllib.error
import time
import sqlite3


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

# 服务重启预案（需要审批，有回滚步骤，验证失败）
playbook_id = "e94b0e52-d1b9-4ee0-a24a-f48bfefea175"
work_order_id = "627f8d0f-1a68-4f49-b8d7-1d5821fac212"
anomaly_id = "25e7772b-7503-42f2-91c6-09a3b1812b0e"

print("=" * 60)
print("测试：验证失败 + 回滚（检查步骤保存）")
print("=" * 60)
print()

# 执行预案
print("1. 启动预案执行...")
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
    print(f"   执行ID: {execution_id}")

# 审批通过
print("2. 审批通过...")
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/playbook-executions/{execution_id}/approve",
    data=json.dumps({"approved": True, "note": "同意执行"}).encode(),
    method="PUT",
    headers={
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    print(f"   审批结果: {result['message']}")

# 等待执行完成
print("3. 等待执行 + 验证 + 回滚完成...")
for i in range(25):
    time.sleep(2)
    req = urllib.request.Request(
        f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        data = result.get("data", result)
        status = data.get("status", "unknown")
        if status in ("success", "failed", "rolled_back", "rejected"):
            print(f"   完成，状态: {status}")
            break
    print(f"   第{i+1}次检查: {status}")

print()
print("=" * 60)
print("执行结果详情")
print("=" * 60)

# 从 API 获取详细信息
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    data = result.get("data", result)
    
    print(f"状态: {data.get('status')}")
    print(f"结果摘要: {data.get('result_summary')}")
    print(f"验证结果: {data.get('verification_result')}")
    print(f"验证备注: {data.get('verification_note')}")
    print(f"是否需要回滚: {data.get('is_rollback_needed')}")
    print(f"回滚结果: {data.get('rollback_result')}")
    
    step_results = data.get("step_results") or []
    print(f"\n总步骤数: {len(step_results)}")
    print("\n执行步骤:")
    for step in step_results:
        if step.get("step_type") != "rollback":
            status_icon = "✅" if step.get("success") else "❌"
            print(f"  {status_icon} {step.get('step_name')} ({step.get('step_type')})")
    
    rollback_steps = [s for s in step_results if s.get("step_type") == "rollback"]
    if rollback_steps:
        print(f"\n回滚步骤:")
        for step in rollback_steps:
            status_icon = "✅" if step.get("success") else "❌"
            print(f"  {status_icon} {step.get('step_name')} ({step.get('step_type')})")
            if not step.get("success") and step.get("error_message"):
                print(f"     错误: {step.get('error_message')}")

print()
print("=" * 60)
print("数据库验证")
print("=" * 60)

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT step_results, status, result_summary, verification_result, rollback_result FROM playbook_executions WHERE id = ?", (execution_id,))
row = cursor.fetchone()
if row:
    db_steps = json.loads(row[0])
    print(f"数据库中步骤数: {len(db_steps)}")
    print(f"数据库状态: {row[1]}")
    print(f"结果摘要: {row[2]}")
    print(f"验证结果: {row[3]}")
    print(f"回滚结果: {row[4]}")
    
    exec_steps = [s for s in db_steps if s.get("step_type") != "rollback"]
    rollback_steps = [s for s in db_steps if s.get("step_type") == "rollback"]
    print(f"执行步骤数: {len(exec_steps)}")
    print(f"回滚步骤数: {len(rollback_steps)}")

conn.close()
