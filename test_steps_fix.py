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

# 缓存清理预案（不需要审批，验证总是通过 - 我们之前改成通过了）
playbook_id = "6c641365-7ea5-4a01-8802-611873b89ec6"

# 找一个工单ID
work_order_id = "bed30c7b-a6c5-430d-8435-189988b450ef"
anomaly_id = "ebdb213e-1e9a-4084-92af-f221d9de1417"

print("=== 执行预案，测试 step_results 保存 ===")

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

# 等待执行完成
print("等待执行完成...")
for i in range(15):
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
            break

print(f"执行完成，状态: {status}")
print()

# 从 API 检查
print("=== API 返回 ===")
req = urllib.request.Request(
    f"http://localhost:8000/api/v1/playbook-executions/{execution_id}",
    headers={"Authorization": f"Bearer {admin_token}"}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())
    data = result.get("data", result)
    step_results = data.get("step_results") or []
    print(f"步骤数: {len(step_results)}")
    for step in step_results:
        print(f"  - {step.get('step_name')}: {'成功' if step.get('success') else '失败'}")

print()

# 从数据库检查
print("=== 数据库检查 ===")
db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT step_results, result_summary FROM playbook_executions WHERE id = ?", (execution_id,))
row = cursor.fetchone()
if row:
    db_steps = json.loads(row[0])
    print(f"步骤数: {len(db_steps)}")
    for step in db_steps:
        print(f"  - {step.get('step_name')}: {'成功' if step.get('success') else '失败'}")
    print(f"结果摘要: {row[1]}")
conn.close()
