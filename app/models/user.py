from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from ..database import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"comment": "运维团队表"}

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="团队ID")
    name = Column(String(100), nullable=False, unique=True, comment="团队名称")
    description = Column(Text, nullable=True, comment="团队描述")
    parent_team_id = Column(String(64), ForeignKey("teams.id"), nullable=True, comment="父团队ID")
    leader_id = Column(String(64), ForeignKey("users.id"), nullable=True, comment="团队主管ID")
    notification_emails = Column(JSON, nullable=True, comment="通知邮箱列表")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    users = relationship("UserTeam", back_populates="team", cascade="all, delete-orphan")
    parent_team = relationship("Team", remote_side=[id], backref="sub_teams")
    work_orders = relationship("app.models.ticket.WorkOrder", back_populates="assigned_team", lazy="selectin")
    leader = relationship("User", foreign_keys=[leader_id], backref="leading_teams")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "用户表"}

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="用户ID")
    username = Column(String(50), nullable=False, unique=True, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    real_name = Column(String(100), nullable=False, comment="真实姓名")
    email = Column(String(100), nullable=False, unique=True, comment="邮箱")
    phone = Column(String(20), nullable=True, comment="手机号")
    role = Column(String(20), nullable=False, default="operator", comment="角色: supervisor/operator")
    is_active = Column(Boolean, default=True, comment="是否激活")
    last_login_at = Column(DateTime(timezone=True), nullable=True, comment="最后登录时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    teams = relationship("UserTeam", back_populates="user", cascade="all, delete-orphan")
    created_work_orders = relationship("WorkOrder", foreign_keys="WorkOrder.creator_id", back_populates="creator")
    assigned_work_orders = relationship("WorkOrder", foreign_keys="WorkOrder.assignee_id", back_populates="assignee")
    created_audits = relationship("AuditLog", foreign_keys="AuditLog.user_id", back_populates="user")
    playbook_executions = relationship("PlaybookExecution", foreign_keys="PlaybookExecution.executor_id", back_populates="executor")


class UserTeam(Base):
    __tablename__ = "user_teams"
    __table_args__ = {"comment": "用户-团队关联表"}

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, comment="用户ID")
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, comment="团队ID")
    is_team_leader = Column(Boolean, default=False, comment="是否团队负责人")
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), comment="加入时间")

    user = relationship("User", back_populates="teams")
    team = relationship("Team", back_populates="users")
