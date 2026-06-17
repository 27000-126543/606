import sqlite3
import json

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

execution_id = "549223d1-82de-4bc7-881d-c03e531baa26"
cursor.execute("SELECT step_results, result_summary, status FROM playbook_executions WHERE id = ?", (execution_id,))
row = cursor.fetchone()
if row:
    print(f"状态: {row[2]}")
    print(f"结果摘要: {row[1]}")
    print()
    step_results = json.loads(row[0])
    print(f"步骤数: {len(step_results)}")
    for i, step in enumerate(step_results):
        step_name = step.get("step_name", "未知")
        success = step.get("success", False)
        print(f"  {i+1}. {step_name} - {'成功' if success else '失败'}")

conn.close()
