import asyncio
import sys
import os

sys.path.insert(0, 'e:\\新项目\\606')

from app.database import async_session_maker
from app.models.playbook import Playbook
from app.models.ticket import WorkOrder
from sqlalchemy import select

async def main():
    async with async_session_maker() as db:
        result = await db.execute(select(Playbook).limit(3))
        playbooks = result.scalars().all()
        print("=== 预案列表 ===")
        for pb in playbooks:
            print(f"ID: {pb.id}")
            print(f"名称: {pb.name}")
            print(f"类型: {pb.playbook_type}")
            print(f"需要审批: {pb.require_approval}")
            print()
        
        result = await db.execute(select(WorkOrder).limit(2))
        orders = result.scalars().all()
        print("=== 工单列表 ===")
        for wo in orders:
            print(f"ID: {wo.id}")
            print(f"标题: {wo.title}")
            print(f"状态: {wo.status}")
            print(f"异常ID: {wo.anomaly_id}")
            print()

asyncio.run(main())
