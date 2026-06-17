import sqlite3

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查预案执行记录
execution_id = "f907a254-8e35-457c-a2da-9d872a4643d3"
cursor.execute("SELECT * FROM playbook_executions WHERE id = ?", (execution_id,))
row = cursor.fetchone()
if row:
    columns = [desc[0] for desc in cursor.description]
    print("=== 执行记录 ===")
    for col, val in zip(columns, row):
        if col in ("step_results", "verification_metrics", "execution_parameters"):
            print(f"{col}: {val[:200] if val else 'None'}")
        else:
            print(f"{col}: {val}")

print()

# 检查配置回滚预案的 steps
playbook_id = "a293b9ec-51a4-40fd-abb5-7c9c04b52b5b"
cursor.execute("SELECT id, name, execution_steps, rollback_steps, verification_method, require_approval FROM playbooks WHERE id = ?", (playbook_id,))
row = cursor.fetchone()
if row:
    print("=== 预案配置 ===")
    print(f"ID: {row[0]}")
    print(f"名称: {row[1]}")
    print(f"执行步骤: {row[2][:300] if row[2] else 'None'}")
    print(f"回滚步骤: {row[3][:200] if row[3] else 'None'}")
    print(f"验证方式: {row[4]}")
    print(f"需要审批: {row[5]}")

conn.close()
