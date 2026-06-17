import sqlite3

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, name, playbook_type, require_approval FROM playbooks LIMIT 3")
print("=== 预案列表 ===")
for row in cursor.fetchall():
    print(f"ID: {row[0]}")
    print(f"名称: {row[1]}")
    print(f"类型: {row[2]}")
    print(f"需要审批: {row[3]}")
    print()

cursor.execute("SELECT id, title, status, anomaly_id FROM work_orders LIMIT 2")
print("=== 工单列表 ===")
for row in cursor.fetchall():
    print(f"ID: {row[0]}")
    print(f"标题: {row[1]}")
    print(f"状态: {row[2]}")
    print(f"异常ID: {row[3]}")
    print()

conn.close()
