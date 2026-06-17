import sqlite3

db_path = "e:/新项目/606/data/ops_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, title, status, anomaly_id FROM work_orders WHERE status = 'assigned' ORDER BY id")
print("=== 待处理工单 ===")
for i, row in enumerate(cursor.fetchall()):
    print(f"{i+1}. ID: {row[0]}")
    print(f"   标题: {row[1]}")
    print(f"   状态: {row[2]}")
    print(f"   异常ID: {row[3]}")
    print()

conn.close()
