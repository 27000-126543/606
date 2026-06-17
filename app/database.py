from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from .config import settings


class Base:
    __abstract__ = True
    __table_args__ = {"sqlite_autoincrement": True, "implicit_returning": False}
    __mapper_args__ = {"eager_defaults": True}


Base = declarative_base(cls=Base)


def _get_db_url():
    return settings.DATABASE_URL


def _get_sync_db_url():
    return settings.SYNC_DATABASE_URL


async_engine = create_async_engine(
    _get_db_url(),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.APP_DEBUG,
    future=True,
    implicit_returning=False,
)

async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

sync_engine = create_engine(
    _get_sync_db_url(),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(drop_first: bool = False):
    from app.models.user import User, Team, UserTeam
    from app.models.log import RawLog, ProcessedLog
    from app.models.anomaly import Anomaly, BaselineConfig
    from app.models.baseline import MetricBaseline, BaselineHistory
    from app.models.ticket import WorkOrder, FollowUpTask
    from app.models.playbook import Playbook, PlaybookExecution
    from app.models.topology import ServiceNode, ServiceDependency, ChangeRecord
    from app.models.audit import AuditLog
    from app.models.report import CaseLibrary, DailyReport, anomaly_case_matches

    async with async_engine.begin() as conn:
        if drop_first:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
