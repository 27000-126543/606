import sqlite3
import json

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

execution_id = "190872e3-a11e-4717-9a7f-721cbbafa916"
cursor.execute("SELECT * FROM playbook_executions WHERE id = ?", (execution_id,))
row = cursor.fetchone()
if row:
    columns = [desc[0] for desc in cursor.description]
    print("=== 执行记录详情 ===")
    for col, val in zip(columns, row):
        if val and col in ("step_results", "verification_metrics", "execution_parameters", "rollback_result"):
            try:
                parsed = json.loads(val)
                print(f"{col}: {json.dumps(parsed, indent=2, ensure_ascii=False)[:500]}")
            except:
                print(f"{col}: {val[:300]}")
        else:
            print(f"{col}: {val}")

conn.close()
