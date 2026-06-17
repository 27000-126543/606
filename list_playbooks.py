import sqlite3

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, name, playbook_type, verification_method, verification_rules, require_approval, rollback_steps FROM playbooks")
print("=== 所有预案 ===")
for row in cursor.fetchall():
    print(f"ID: {row[0]}")
    print(f"名称: {row[1]}")
    print(f"类型: {row[2]}")
    print(f"验证方式: {row[3]}")
    print(f"验证规则: {row[4][:200] if row[4] else 'None'}")
    print(f"需要审批: {row[5]}")
    print(f"有回滚步骤: {row[6] is not None}")
    print()

conn.close()
