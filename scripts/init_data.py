"""
初始化数据脚本
运行方式: python scripts/init_data.py
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker, Base
from app.models.user import User, Team, UserTeam
from app.models.log import RawLog, ProcessedLog
from app.models.anomaly import Anomaly, BaselineConfig
from app.models.baseline import MetricBaseline, BaselineHistory
from app.models.ticket import WorkOrder, FollowUpTask
from app.models.playbook import Playbook, PlaybookExecution
from app.models.topology import ServiceNode, ServiceDependency, ChangeRecord
from app.models.audit import AuditLog
from app.models.report import CaseLibrary, DailyReport, anomaly_case_matches
from app.utils.auth import hash_password
from app.utils.logger import logger


async def init_default_teams(db):
    teams_data = [
        {"name": "平台运维组", "description": "负责底层平台基础设施运维"},
        {"name": "应用运维组", "description": "负责业务应用系统运维"},
        {"name": "数据库组", "description": "负责数据库集群运维与优化"},
        {"name": "网络安全组", "description": "负责网络安全与合规"},
        {"name": "监控告警组", "description": "负责监控系统与告警处理"},
    ]

    teams = {}
    for td in teams_data:
        team = Team(**td)
        db.add(team)
        await db.flush()
        teams[td["name"]] = team
        logger.info(f"Created team: {team.name}")

    return teams


async def init_default_users(db, teams):
    users_data = [
        {
            "username": "admin",
            "password": "Admin@123456",
            "real_name": "系统管理员",
            "email": "admin@ops.com",
            "phone": "13800138000",
            "role": "supervisor",
            "team": "平台运维组",
            "is_leader": True,
        },
        {
            "username": "supervisor1",
            "password": "Super@123",
            "real_name": "运维主管张工",
            "email": "supervisor@ops.com",
            "phone": "13800138001",
            "role": "supervisor",
            "team": "平台运维组",
            "is_leader": False,
        },
        {
            "username": "operator1",
            "password": "Oper@123",
            "real_name": "运维工程师李工",
            "email": "operator1@ops.com",
            "phone": "13800138011",
            "role": "operator",
            "team": "应用运维组",
            "is_leader": False,
        },
        {
            "username": "operator2",
            "password": "Oper@123",
            "real_name": "运维工程师王工",
            "email": "operator2@ops.com",
            "phone": "13800138012",
            "role": "operator",
            "team": "数据库组",
            "is_leader": True,
        },
        {
            "username": "operator3",
            "password": "Oper@123",
            "real_name": "运维工程师赵工",
            "email": "operator3@ops.com",
            "phone": "13800138013",
            "role": "operator",
            "team": "监控告警组",
            "is_leader": False,
        },
    ]

    for ud in users_data:
        user = User(
            username=ud["username"],
            password_hash=hash_password(ud["password"]),
            real_name=ud["real_name"],
            email=ud["email"],
            phone=ud["phone"],
            role=ud["role"],
        )
        db.add(user)
        await db.flush()

        team = teams.get(ud["team"])
        if team:
            ut = UserTeam(
                user_id=user.id,
                team_id=team.id,
                is_team_leader=ud["is_leader"],
            )
            db.add(ut)

        logger.info(f"Created user: {user.username} ({user.role}) - {ud['password']}")


async def init_default_playbooks(db, teams):
    playbooks_data = [
        {
            "name": "服务重启预案",
            "description": "当服务出现异常时，执行滚动重启操作",
            "playbook_type": "restart",
            "applicable_severities": ["high", "critical"],
            "trigger_condition_type": "manual",
            "execution_steps": [
                {"name": "检查服务状态", "type": "check_condition", "action": "check_health", "stop_on_failure": True},
                {"name": "停止流量接入", "type": "action", "action": "drain_traffic"},
                {"name": "滚动重启实例", "type": "restart_service", "action": "rolling_restart",
                 "params": {"service_name": "", "strategy": "rolling", "instance_count": 3},
                 "stop_on_failure": True},
                {"name": "等待服务就绪", "type": "wait", "params": {"seconds": 30}},
                {"name": "恢复流量接入", "type": "action", "action": "restore_traffic"},
                {"name": "发送通知", "type": "notification", "action": "send_email"},
            ],
            "rollback_steps": [
                {"name": "回滚到上一版本", "type": "rollback_config", "action": "rollback_version"},
            ],
            "verification_method": "health_check",
            "verification_rules": {"expected_instances": 3, "total_instances": 3},
            "verification_timeout_seconds": 300,
            "is_auto_executable": False,
            "require_approval": True,
            "approver_role": "supervisor",
            "estimated_duration_seconds": 180,
            "is_enabled": True,
        },
        {
            "name": "配置回滚预案",
            "description": "配置变更引起异常时，快速回滚到上一版本配置",
            "playbook_type": "rollback",
            "applicable_anomaly_types": ["config_change", "deploy"],
            "applicable_severities": ["high", "critical", "medium"],
            "trigger_condition_type": "auto",
            "execution_steps": [
                {"name": "确认变更记录", "type": "check_condition", "action": "check_change_record",
                 "stop_on_failure": True},
                {"name": "备份当前配置", "type": "action", "action": "backup_config"},
                {"name": "回滚配置", "type": "rollback_config", "action": "apply_previous_version",
                 "params": {"version": "auto"}, "stop_on_failure": True},
                {"name": "重新加载配置", "type": "action", "action": "reload_config"},
                {"name": "等待配置生效", "type": "wait", "params": {"seconds": 15}},
            ],
            "verification_method": "metric_check",
            "verification_rules": {
                "thresholds": {
                    "error_rate": {"max": 1.0},
                    "success_rate": {"min": 99.0},
                }
            },
            "verification_timeout_seconds": 180,
            "is_auto_executable": True,
            "auto_execute_max_severity": "critical",
            "require_approval": False,
            "estimated_duration_seconds": 60,
            "is_enabled": True,
        },
        {
            "name": "数据库故障转移预案",
            "description": "主数据库故障时，自动切换到备用节点",
            "playbook_type": "db_failover",
            "applicable_severities": ["critical"],
            "trigger_condition_type": "auto",
            "execution_steps": [
                {"name": "检测主库状态", "type": "check_condition", "action": "check_db_status",
                 "stop_on_failure": True},
                {"name": "断开主库连接", "type": "action", "action": "fence_master"},
                {"name": "提升备库为主", "type": "db_failover", "action": "promote_replica",
                 "params": {"cluster_name": "", "target_node": ""}, "stop_on_failure": True},
                {"name": "更新路由配置", "type": "config_change", "action": "update_db_proxy"},
                {"name": "验证数据一致性", "type": "check_condition", "action": "check_data_consistency"},
            ],
            "rollback_steps": [
                {"name": "恢复原主库角色", "type": "action", "action": "restore_replication"},
            ],
            "verification_method": "custom",
            "verification_timeout_seconds": 600,
            "is_auto_executable": False,
            "require_approval": True,
            "approver_role": "supervisor",
            "estimated_duration_seconds": 300,
            "is_enabled": True,
        },
        {
            "name": "缓存清理预案",
            "description": "缓存异常导致服务问题时，清理指定缓存键",
            "playbook_type": "cleanup",
            "applicable_anomaly_types": ["cache", "memory"],
            "applicable_severities": ["medium", "high"],
            "trigger_condition_type": "manual",
            "execution_steps": [
                {"name": "定位问题缓存", "type": "check_condition", "action": "identify_bad_cache"},
                {"name": "清理指定缓存", "type": "clear_cache", "action": "delete_keys",
                 "params": {"cache_type": "redis", "pattern": ""}},
            ],
            "verification_method": "log_check",
            "verification_rules": {"window_minutes": 10, "max_error_rate": 0.5},
            "verification_timeout_seconds": 120,
            "is_auto_executable": True,
            "auto_execute_max_severity": "high",
            "require_approval": False,
            "estimated_duration_seconds": 30,
            "is_enabled": True,
        },
        {
            "name": "紧急扩容预案",
            "description": "流量突增时，自动扩展服务实例数",
            "playbook_type": "scale_up",
            "applicable_anomaly_types": ["throughput", "traffic_abnormal", "high_load"],
            "applicable_severities": ["high", "critical"],
            "trigger_condition_type": "auto",
            "execution_steps": [
                {"name": "检查资源配额", "type": "check_condition", "action": "check_quota",
                 "stop_on_failure": True},
                {"name": "扩展服务实例", "type": "scale_up", "action": "add_instances",
                 "params": {"service_name": "", "target_count": 6, "current_count": 3},
                 "stop_on_failure": True},
                {"name": "等待实例就绪", "type": "wait", "params": {"seconds": 60}},
                {"name": "验证服务健康", "type": "check_condition", "action": "check_health"},
            ],
            "verification_method": "health_check",
            "verification_rules": {"expected_instances": 6},
            "verification_timeout_seconds": 300,
            "is_auto_executable": True,
            "auto_execute_max_severity": "critical",
            "require_approval": False,
            "estimated_duration_seconds": 120,
            "is_enabled": True,
        },
    ]

    for pd in playbooks_data:
        pb = Playbook(**pd)
        db.add(pb)
        await db.flush()
        logger.info(f"Created playbook: {pb.name} ({pb.playbook_type})")


async def init_default_topology(db, teams):
    systems = [
        {"name": "订单系统", "services": [
            {"name": "order-service", "type": "service", "tier": 1},
            {"name": "order-gateway", "type": "gateway", "tier": 1},
            {"name": "order-db", "type": "database", "tier": 1},
        ]},
        {"name": "支付系统", "services": [
            {"name": "payment-service", "type": "service", "tier": 1},
            {"name": "payment-gateway", "type": "gateway", "tier": 1},
        ]},
        {"name": "用户系统", "services": [
            {"name": "user-service", "type": "service", "tier": 2},
            {"name": "user-cache", "type": "cache", "tier": 2},
        ]},
        {"name": "商品系统", "services": [
            {"name": "product-service", "type": "service", "tier": 2},
            {"name": "product-search", "type": "service", "tier": 2},
        ]},
        {"name": "消息系统", "services": [
            {"name": "message-queue", "type": "mq", "tier": 2},
        ]},
    ]

    created_nodes = {}
    for sys in systems:
        for svc in sys["services"]:
            team = teams.get("平台运维组") if svc["tier"] == 1 else teams.get("应用运维组")
            node = ServiceNode(
                service_name=svc["name"],
                system_name=sys["name"],
                node_type=svc["type"],
                description=f"{sys['name']} - {svc['name']}",
                instance_count=3 if svc["type"] == "service" else 1,
                owner_team_id=team.id if team else None,
                tier=svc["tier"],
            )
            db.add(node)
            await db.flush()
            created_nodes[svc["name"]] = node
            logger.info(f"Created service node: {node.service_name} ({node.system_name})")

    dependencies = [
        ("order-service", "user-service", "sync_http", "hard", "full_outage"),
        ("order-service", "payment-service", "sync_http", "hard", "full_outage"),
        ("order-service", "product-service", "sync_http", "medium", "partial_degradation"),
        ("order-service", "message-queue", "async_mq", "medium", "partial_degradation"),
        ("order-service", "order-db", "database_read", "hard", "full_outage"),
        ("payment-service", "user-service", "sync_http", "medium", "partial_degradation"),
        ("product-service", "product-search", "sync_http", "medium", "partial_degradation"),
        ("product-search", "message-queue", "async_mq", "low", "performance_impact"),
        ("user-service", "user-cache", "sync_http", "medium", "partial_degradation"),
        ("order-gateway", "order-service", "sync_http", "hard", "full_outage"),
        ("payment-gateway", "payment-service", "sync_http", "hard", "full_outage"),
    ]

    for src, tgt, dep_type, crit, impact in dependencies:
        if src in created_nodes and tgt in created_nodes:
            dep = ServiceDependency(
                source_service_id=created_nodes[src].id,
                target_service_id=created_nodes[tgt].id,
                dependency_type=dep_type,
                criticality=crit,
                failure_impact=impact,
                avg_latency_ms=50 if "sync" in dep_type else 200,
            )
            db.add(dep)
            logger.info(f"Created dependency: {src} -> {tgt} ({dep_type})")


async def init_sample_changes(db):
    from app.models.topology import ChangeRecord
    import random

    change_types = ["deploy", "config", "infra", "database", "security"]
    systems = ["订单系统", "支付系统", "用户系统", "商品系统"]
    risk_levels = ["low", "medium", "high", "critical"]
    statuses = ["completed", "failed", "rolled_back"]

    now = datetime.now(timezone.utc)
    for i in range(15):
        change_time = now - timedelta(hours=random.randint(1, 72), minutes=random.randint(0, 60))
        cr = ChangeRecord(
            change_no=f"CHG{now.strftime('%Y%m%d')}{random.randint(1000,9999)}",
            change_type=random.choice(change_types),
            change_subtype="v" + str(random.randint(1, 10)) + "." + str(random.randint(0, 20)),
            title=f"{random.choice(['功能发布', '配置更新', '补丁修复', '参数调优', '版本升级'])} #{i+1}",
            description="自动生成的测试变更记录",
            affected_system=random.choice(systems),
            change_time=change_time,
            expected_end_time=change_time + timedelta(minutes=random.randint(10, 60)),
            actual_end_time=change_time + timedelta(minutes=random.randint(8, 80)),
            initiator=random.choice(["admin", "operator1", "operator2", "system"]),
            implementer=random.choice(["CI/CD", "operator1", "operator2"]),
            status=random.choices(statuses, weights=[0.7, 0.15, 0.15])[0],
            risk_level=random.choices(risk_levels, weights=[0.3, 0.4, 0.2, 0.1])[0],
            change_source=random.choice(["ci_cd", "manual", "api"]),
        )
        db.add(cr)

    logger.info("Created 15 sample change records")


async def init_sample_anomalies_and_tickets(db):
    from app.models.anomaly import Anomaly
    from app.models.ticket import WorkOrder, FollowUpTask
    import random
    from decimal import Decimal

    now = datetime.now(timezone.utc)
    systems = ["订单系统", "支付系统", "用户系统", "商品系统", "消息系统"]
    anomaly_types = ["error_rate", "response_time", "availability", "throughput", "custom"]
    severities = ["critical", "high", "medium", "low"]
    impact_scopes = ["single", "module", "system", "multi_system"]
    statuses = ["open", "investigating", "resolved", "closed"]

    created_anomalies = []

    for i in range(20):
        detected_time = now - timedelta(hours=random.randint(0, 48), minutes=random.randint(0, 60))
        severity = random.choices(severities, weights=[0.1, 0.25, 0.4, 0.25])[0]
        anomaly_code = f"ANOM{detected_time.strftime('%Y%m%d%H%M%S')}{random.randint(1000,9999)}"

        anomaly = Anomaly(
            anomaly_code=anomaly_code,
            system_name=random.choice(systems),
            anomaly_type=random.choice(anomaly_types),
            severity=severity,
            title=f"[{severity.upper()}] 模拟异常事件 #{i+1}",
            description=f"这是一个自动生成的模拟异常记录，用于演示系统功能。严重等级: {severity}",
            detected_time=detected_time,
            first_occurrence_time=detected_time - timedelta(minutes=random.randint(0, 10)),
            last_occurrence_time=detected_time,
            occurrence_count=random.randint(1, 50),
            impact_scope=random.choices(impact_scopes, weights=[0.5, 0.3, 0.15, 0.05])[0],
            impact_score=Decimal(str(random.randint(10, 100))),
            status=random.choices(statuses, weights=[0.15, 0.2, 0.45, 0.2])[0],
            confidence=Decimal(str(random.randint(50, 99))),
            is_auto_detected=True,
            detection_algorithm="dynamic_baseline",
        )
        db.add(anomaly)
        await db.flush()
        created_anomalies.append(anomaly)

    logger.info(f"Created {len(created_anomalies)} sample anomalies")

    team_result = await db.execute(select(Team))
    teams = team_result.scalars().all()
    user_result = await db.execute(select(User).where(User.role == "operator"))
    operators = user_result.scalars().all()

    for i, anomaly in enumerate(created_anomalies[:15]):
        from app.models.ticket import WorkOrder as WO
        priority_map = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}
        priority = priority_map.get(anomaly.severity, "P3")
        sla_map = {"P0": 60, "P1": 240, "P2": 480, "P3": 1440}
        sla_deadline = anomaly.detected_time + timedelta(minutes=sla_map.get(priority, 1440))

        team = random.choice(teams) if teams else None
        assignee = random.choice(operators) if operators else None
        wo_status = random.choices(["pending", "assigned", "in_progress", "completed", "escalated"],
                                    weights=[0.1, 0.15, 0.25, 0.4, 0.1])[0]

        order_no = f"WO{anomaly.detected_time.strftime('%Y%m%d%H%M%S')}{random.randint(1000,9999)}"
        work_order = WO(
            order_no=order_no,
            anomaly_id=anomaly.id,
            title=anomaly.title,
            description=anomaly.description,
            anomaly_type=anomaly.anomaly_type,
            severity=anomaly.severity,
            priority=priority,
            impact_scope=anomaly.impact_scope,
            assigned_team_id=team.id if team else None,
            assignee_id=assignee.id if assignee else None,
            auto_assigned=True,
            status=wo_status,
            sla_deadline=sla_deadline,
        )

        if wo_status in ["assigned", "in_progress"]:
            work_order.first_response_at = anomaly.detected_time + timedelta(minutes=random.randint(1, 30))
        if wo_status in ["in_progress"]:
            work_order.started_at = anomaly.detected_time + timedelta(minutes=random.randint(10, 60))
        if wo_status == "completed":
            work_order.started_at = anomaly.detected_time + timedelta(minutes=random.randint(5, 30))
            work_order.resolved_at = anomaly.detected_time + timedelta(minutes=random.randint(30, 180))
            work_order.actual_resolution_minutes = random.randint(20, 180)
        if wo_status == "escalated":
            work_order.is_escalated = True
            work_order.escalation_count = 1

        db.add(work_order)
        await db.flush()

        if wo_status in ["pending", "escalated"]:
            task = FollowUpTask(
                work_order_id=work_order.id,
                task_type="manual_follow_up" if wo_status == "pending" else "escalation",
                title=f"工单跟进: {order_no}",
                description="系统自动生成的跟进任务",
                priority=priority,
                next_follow_up_at=now + timedelta(hours=random.randint(1, 4)),
                follow_up_interval_hours=4,
            )
            db.add(task)

    logger.info("Created 15 sample work orders with follow-up tasks")


async def init_sample_case_library(db):
    from app.models.report import CaseLibrary
    import random
    from decimal import Decimal

    case_data = [
        {
            "category": "配置错误",
            "severity": "high",
            "root_cause_category": "配置变更",
            "desc": "JVM参数配置不合理导致频繁Full GC",
            "cause": "新版本发布时误将Xmx参数设置过小，导致老年代空间不足",
            "steps": [
                {"step": 1, "action": "分析GC日志", "detail": "确认频繁Full GC现象"},
                {"step": 2, "action": "调整JVM参数", "detail": "-Xmx4g -Xms4g，调整垃圾回收器为G1"},
                {"step": 3, "action": "滚动重启服务", "detail": "按实例组滚动重启，观察GC指标"},
            ],
            "prevention": "发布前检查配置模板，增加预发布环境压测流程",
        },
        {
            "category": "数据库问题",
            "severity": "critical",
            "root_cause_category": "性能问题",
            "desc": "慢查询导致数据库CPU飙升，响应超时",
            "cause": "新增查询缺少索引，大表全表扫描",
            "steps": [
                {"step": 1, "action": "抓取慢SQL", "detail": "使用pg_stat_statements定位问题SQL"},
                {"step": 2, "action": "添加索引", "detail": "CREATE INDEX CONCURRENTLY避免锁表"},
                {"step": 3, "action": "验证执行计划", "detail": "EXPLAIN ANALYZE确认索引生效"},
            ],
            "prevention": "上线前SQL审核，增加慢查询阈值告警",
        },
        {
            "category": "依赖故障",
            "severity": "high",
            "root_cause_category": "外部依赖",
            "desc": "Redis连接池耗尽导致请求阻塞",
            "cause": "业务流量突增，连接池未动态扩容",
            "steps": [
                {"step": 1, "action": "紧急扩容连接池", "detail": "maxTotal从100调整到300"},
                {"step": 2, "action": "优化连接配置", "detail": "启用连接池监控，增加borrow等待超时"},
                {"step": 3, "action": "增加熔断降级", "detail": "对非核心缓存操作增加降级逻辑"},
            ],
            "prevention": "连接池动态扩容，提前容量规划",
        },
        {
            "category": "发布故障",
            "severity": "critical",
            "root_cause_category": "版本变更",
            "desc": "新版本引入空指针异常，订单创建失败率飙升",
            "cause": "边界条件未覆盖，用户特定场景触发NPE",
            "steps": [
                {"step": 1, "action": "紧急回滚版本", "detail": "回滚到上一稳定版本v2.3.1"},
                {"step": 2, "action": "隔离问题流量", "detail": "问题用户灰度到修复版本"},
                {"step": 3, "action": "补充单元测试", "detail": "覆盖边界条件场景"},
            ],
            "prevention": "增强灰度发布策略，增加错误率自动回滚阈值",
        },
        {
            "category": "消息积压",
            "severity": "medium",
            "root_cause_category": "性能问题",
            "desc": "MQ消费端积压，延迟持续上升",
            "cause": "消费者处理逻辑变慢，跟不上生产速度",
            "steps": [
                {"step": 1, "action": "扩容消费者", "detail": "消费者实例从3个扩容到8个"},
                {"step": 2, "action": "优化消费逻辑", "detail": "批量处理替代逐条处理"},
                {"step": 3, "action": "处理积压消息", "detail": "临时增加消费线程池处理历史积压"},
            ],
            "prevention": "增加消费延迟预警，消费者水平自动扩展",
        },
    ]

    for i, cd in enumerate(case_data):
        case = CaseLibrary(
            case_no=f"CASE{datetime.now().strftime('%Y%m%d')}{1000+i:04d}",
            title=f"案例库: {cd['desc']}",
            system_name=random.choice(["订单系统", "支付系统", "用户系统", "商品系统"]),
            anomaly_type=random.choice(["error_rate", "response_time", "availability", "throughput"]),
            severity=cd["severity"],
            category=cd["category"],
            tags=["案例库", "最佳实践", cd["category"]],
            keywords=cd["desc"].split() + cd["category"].split(),
            symptom_description=cd["desc"],
            root_cause=cd["cause"],
            root_cause_category=cd["root_cause_category"],
            resolution_steps=cd["steps"],
            prevention_measures=cd["prevention"],
            occurrence_count=random.randint(3, 50),
            resolution_time_avg_minutes=random.randint(20, 120),
            success_rate=Decimal(str(random.randint(85, 100))),
            is_verified=True,
            imported_from="system",
        )
        db.add(case)

    logger.info(f"Created {len(case_data)} sample case library entries")


async def main():
    logger.info("=" * 60)
    logger.info("开始初始化系统数据...")
    logger.info("=" * 60)

    logger.info("Creating database tables...")
    from app.database import init_db
    await init_db(drop_first=True)
    logger.info("Database tables created successfully")

    async with async_session_maker() as db:
        teams = await init_default_teams(db)
        await init_default_users(db, teams)
        await init_default_playbooks(db, teams)
        await init_default_topology(db, teams)
        await init_sample_changes(db)
        await init_sample_anomalies_and_tickets(db)
        await init_sample_case_library(db)

        await db.commit()

    logger.info("=" * 60)
    logger.info("系统数据初始化完成!")
    logger.info("默认账号:")
    logger.info("  管理员: admin / Admin@123456 (supervisor)")
    logger.info("  主管:   supervisor1 / Super@123 (supervisor)")
    logger.info("  运维:   operator1 / Oper@123 (operator)")
    logger.info("  运维:   operator2 / Oper@123 (operator)")
    logger.info("  运维:   operator3 / Oper@123 (operator)")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
