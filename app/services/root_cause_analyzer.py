from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import uuid
from decimal import Decimal
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import async_session_maker
from ..models.anomaly import Anomaly
from ..models.topology import ServiceNode, ServiceDependency, ChangeRecord
from ..models.ticket import WorkOrder
from ..utils.logger import logger


class RootCauseAnalyzer:
    def __init__(self):
        self._dependency_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300

    async def analyze_anomaly(
        self, anomaly_id: str, db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        try:
            if db is None:
                async with async_session_maker() as db:
                    return await self._perform_analysis(anomaly_id, db)
            else:
                return await self._perform_analysis(anomaly_id, db)
        except Exception as e:
            logger.error(f"Root cause analysis failed for anomaly {anomaly_id}: {e}", exc_info=True)
            return self._empty_result(anomaly_id, f"分析执行失败: {str(e)}")

    def _empty_result(self, anomaly_id: str = "", message: str = "") -> Dict[str, Any]:
        return {
            "anomaly_id": anomaly_id,
            "analysis_time": datetime.now(timezone.utc).isoformat(),
            "candidate_root_causes": [],
            "related_changes": [],
            "impact_chain": [],
            "affected_downstream_services": [],
            "affected_upstream_services": [],
            "recommended_teams": [],
            "summary": message or "暂无匹配的相关变更、拓扑依赖和同期异常数据",
            "has_data": False,
        }

    async def _perform_analysis(
        self, anomaly_id: str, db: AsyncSession
    ) -> Dict[str, Any]:
        result = await db.execute(select(Anomaly).where(Anomaly.id == anomaly_id))
        anomaly = result.scalar_one_or_none()
        if anomaly is None:
            return self._empty_result(anomaly_id, "异常记录不存在")

        analysis_result = {
            "anomaly_id": str(anomaly.id),
            "analysis_time": datetime.now(timezone.utc).isoformat(),
            "candidate_root_causes": [],
            "related_changes": [],
            "impact_chain": [],
            "affected_downstream_services": [],
            "affected_upstream_services": [],
            "recommended_teams": [],
            "summary": "",
            "has_data": False,
        }

        system_name = anomaly.system_name
        detected_time = anomaly.detected_time

        service_node = await self._get_service_node(system_name, db)
        if service_node:
            analysis_result["service_tier"] = service_node.tier
            analysis_result["owner_team_id"] = str(service_node.owner_team_id) if service_node.owner_team_id else None

        changes = await self._find_related_changes(
            system_name, detected_time, db
        )
        analysis_result["related_changes"] = [
            self._serialize_change(change) for change in changes
        ]

        impact_chain = []
        if service_node:
            upstream, downstream = await self._analyze_dependencies(
                service_node.id, db
            )
            analysis_result["affected_upstream_services"] = upstream
            analysis_result["affected_downstream_services"] = downstream

            impact_chain = await self._build_impact_chain(
                service_node.id, detected_time, db
            )
            analysis_result["impact_chain"] = impact_chain

        concurrent_anomalies = await self._find_concurrent_anomalies(
            system_name, detected_time, db
        )

        root_causes = self._score_root_causes(
            anomaly=anomaly,
            changes=changes,
            upstream_services=analysis_result["affected_upstream_services"],
            concurrent_anomalies=concurrent_anomalies,
        )
        analysis_result["candidate_root_causes"] = root_causes

        has_matches = bool(changes) or bool(impact_chain) or bool(root_causes) or bool(concurrent_anomalies)
        analysis_result["has_data"] = has_matches

        if root_causes:
            top_cause = root_causes[0]
            try:
                anomaly.root_cause_analysis = analysis_result
                anomaly.related_change_ids = [
                    c["id"] for c in analysis_result["related_changes"]
                ]
                anomaly.related_dependencies = {
                    "upstream": analysis_result["affected_upstream_services"],
                    "downstream": analysis_result["affected_downstream_services"],
                    "impact_chain": analysis_result["impact_chain"],
                }

                if changes:
                    change = changes[0]
                    if change.owner_team_id:
                        analysis_result["recommended_teams"].append(str(change.owner_team_id))
                elif service_node and service_node.owner_team_id:
                    analysis_result["recommended_teams"].append(str(service_node.owner_team_id))

                analysis_result["summary"] = self._generate_summary(
                    anomaly, top_cause, changes, impact_chain
                )

                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to save root cause analysis to anomaly {anomaly_id}: {e}")
        elif not has_matches:
            analysis_result["summary"] = "未找到相关变更记录、拓扑依赖或同期异常，建议人工排查"

        return analysis_result

    async def _get_service_node(
        self, system_name: str, db: AsyncSession
    ) -> Optional[ServiceNode]:
        result = await db.execute(
            select(ServiceNode).where(
                and_(
                    ServiceNode.system_name == system_name,
                    ServiceNode.is_active == True,
                )
            )
        )
        return result.scalars().first()

    async def _find_related_changes(
        self,
        system_name: str,
        detected_time: datetime,
        db: AsyncSession,
    ) -> List[ChangeRecord]:
        time_window_start = detected_time - timedelta(hours=4)
        time_window_end = detected_time + timedelta(minutes=30)

        query = (
            select(ChangeRecord)
            .where(
                and_(
                    ChangeRecord.change_time >= time_window_start,
                    ChangeRecord.change_time <= time_window_end,
                    ChangeRecord.status.in_(["completed", "failed", "rolled_back"]),
                )
            )
            .order_by(ChangeRecord.change_time.desc())
        )
        result = await db.execute(query)
        all_changes = list(result.scalars().all())

        related_changes = []
        for change in all_changes:
            if change.affected_system == system_name:
                related_changes.append(change)
                continue
            affected_services = change.affected_services or []
            if isinstance(affected_services, list) and system_name in affected_services:
                related_changes.append(change)

        return related_changes

    def _serialize_change(self, change: ChangeRecord) -> Dict[str, Any]:
        return {
            "id": str(change.id),
            "change_no": change.change_no,
            "change_type": change.change_type,
            "title": change.title,
            "affected_system": change.affected_system,
            "affected_services": change.affected_services or [],
            "change_time": change.change_time.isoformat(),
            "status": change.status,
            "risk_level": change.risk_level,
            "initiator": change.initiator,
            "change_source": change.change_source,
            "is_rollback": change.is_rollback,
        }

    async def _analyze_dependencies(
        self, service_id: str, db: AsyncSession
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        upstream_result = await db.execute(
            select(ServiceDependency, ServiceNode)
            .join(
                ServiceNode,
                ServiceDependency.source_service_id == ServiceNode.id,
            )
            .where(ServiceDependency.target_service_id == service_id)
            .where(ServiceDependency.is_active == True)
        )

        upstream = []
        for dep, node in upstream_result.fetchall():
            upstream.append({
                "service_id": str(node.id),
                "service_name": node.service_name,
                "system_name": node.system_name,
                "dependency_type": dep.dependency_type,
                "criticality": dep.criticality,
                "failure_impact": dep.failure_impact,
                "owner_team_id": str(node.owner_team_id) if node.owner_team_id else None,
                "tier": node.tier,
            })

        downstream_result = await db.execute(
            select(ServiceDependency, ServiceNode)
            .join(
                ServiceNode,
                ServiceDependency.target_service_id == ServiceNode.id,
            )
            .where(ServiceDependency.source_service_id == service_id)
            .where(ServiceDependency.is_active == True)
        )

        downstream = []
        for dep, node in downstream_result.fetchall():
            downstream.append({
                "service_id": str(node.id),
                "service_name": node.service_name,
                "system_name": node.system_name,
                "dependency_type": dep.dependency_type,
                "criticality": dep.criticality,
                "failure_impact": dep.failure_impact,
                "owner_team_id": str(node.owner_team_id) if node.owner_team_id else None,
                "tier": node.tier,
            })

        return upstream, downstream

    async def _build_impact_chain(
        self, service_id: str, detected_time: datetime, db: AsyncSession
    ) -> List[Dict[str, Any]]:
        visited = set()
        chain = []
        queue = deque([(service_id, 0, [])])

        while queue:
            current_id, depth, path = queue.popleft()
            if current_id in visited or depth > 3:
                continue
            visited.add(current_id)

            result = await db.execute(
                select(ServiceNode).where(ServiceNode.id == current_id)
            )
            node = result.scalar_one_or_none()
            if node is None:
                continue

            anomaly_count = 0
            if depth > 0:
                time_window = timedelta(minutes=30 * (depth + 1))
                anomaly_result = await db.execute(
                    select(Anomaly).where(
                        and_(
                            Anomaly.system_name == node.system_name,
                            Anomaly.detected_time >= detected_time - time_window,
                            Anomaly.detected_time <= detected_time + time_window,
                            Anomaly.status.in_(["open", "investigating", "resolved"]),
                        )
                    )
                )
                anomaly_count = len(anomaly_result.scalars().all())

            chain.append({
                "depth": depth,
                "service_id": str(node.id),
                "service_name": node.service_name,
                "system_name": node.system_name,
                "tier": node.tier,
                "path": path + [node.service_name],
                "anomaly_count": anomaly_count,
                "has_active_anomaly": anomaly_count > 0,
            })

            if depth < 3:
                downstream_result = await db.execute(
                    select(ServiceDependency).where(
                        and_(
                            ServiceDependency.source_service_id == current_id,
                            ServiceDependency.is_active == True,
                        )
                    )
                )
                for dep in downstream_result.scalars().all():
                    queue.append(
                        (
                            str(dep.target_service_id),
                            depth + 1,
                            path + [node.service_name],
                        )
                    )

        chain.sort(key=lambda x: (x["depth"], -x["anomaly_count"]))
        return chain

    async def _find_concurrent_anomalies(
        self,
        system_name: str,
        detected_time: datetime,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        time_window = timedelta(hours=2)
        query = (
            select(Anomaly)
            .where(
                and_(
                    Anomaly.system_name != system_name,
                    Anomaly.detected_time >= detected_time - time_window,
                    Anomaly.detected_time <= detected_time + time_window,
                    Anomaly.status.in_(["open", "investigating", "resolved"]),
                )
            )
            .order_by(Anomaly.detected_time)
            .limit(20)
        )
        result = await db.execute(query)
        anomalies = result.scalars().all()

        return [
            {
                "id": str(a.id),
                "anomaly_code": a.anomaly_code,
                "system_name": a.system_name,
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "detected_time": a.detected_time.isoformat(),
                "time_diff_minutes": abs(
                    (a.detected_time - detected_time).total_seconds() / 60
                ),
            }
            for a in anomalies
        ]

    def _score_root_causes(
        self,
        anomaly: Anomaly,
        changes: List[ChangeRecord],
        upstream_services: List[Dict[str, Any]],
        concurrent_anomalies: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates = []

        for change in changes:
            score = 0.0
            reasons = []

            score += 40
            reasons.append("异常发生前存在相关变更记录")

            if change.risk_level == "critical":
                score += 25
                reasons.append("变更为高风险级别")
            elif change.risk_level == "high":
                score += 15
                reasons.append("变更为较高风险级别")
            elif change.risk_level == "medium":
                score += 10
                reasons.append("变更为中等风险级别")

            if change.status == "failed":
                score += 20
                reasons.append("变更执行失败")
            elif change.status == "rolled_back":
                score += 15
                reasons.append("变更已执行回滚")

            if change.change_type in ("deploy", "config", "database"):
                score += 10
                reasons.append(f"变更类型({change.change_type})易引发异常")

            candidates.append({
                "type": "change_record",
                "change_id": str(change.id),
                "change_no": change.change_no,
                "title": f"变更操作: {change.title}",
                "score": min(100, score),
                "confidence": min(100, score),
                "reasons": reasons,
                "details": self._serialize_change(change),
            })

        hard_deps = [d for d in upstream_services if d["criticality"] in ("hard", "high")]
        for dep in hard_deps:
            related_anomalies = [
                a
                for a in concurrent_anomalies
                if a["system_name"] == dep["system_name"] and a["time_diff_minutes"] < 60
            ]

            score = 0.0
            reasons = []

            if related_anomalies:
                score += 35
                reasons.append(f"上游依赖{dep['service_name']}存在同期异常")

                for a in related_anomalies:
                    if a["severity"] in ("critical", "high"):
                        score += 20
                        reasons.append(f"上游异常严重等级为{a['severity']}")
                    if a["time_diff_minutes"] < 10:
                        score += 15
                        reasons.append(f"上游异常发生时间高度相关({a['time_diff_minutes']:.0f}分钟前)")

            if dep["failure_impact"] == "full_outage":
                score += 15
                reasons.append("该依赖故障会导致服务完全不可用")
            elif dep["failure_impact"] == "partial_degradation":
                score += 5
                reasons.append("该依赖故障会导致服务降级")

            if dep["tier"] == 1:
                score += 10
                reasons.append("上游服务为核心服务")

            if score > 0:
                candidates.append({
                    "type": "upstream_dependency",
                    "service_id": dep["service_id"],
                    "service_name": dep["service_name"],
                    "system_name": dep["system_name"],
                    "title": f"上游依赖异常: {dep['service_name']}",
                    "score": min(100, score),
                    "confidence": min(100, score),
                    "reasons": reasons,
                    "details": dep,
                    "related_anomalies": related_anomalies,
                })

        same_system_anomalies = [
            a
            for a in concurrent_anomalies
            if a["anomaly_type"] == anomaly.anomaly_type and a["time_diff_minutes"] < 120
        ]
        if len(same_system_anomalies) >= 2:
            score = 30 + len(same_system_anomalies) * 5
            candidates.append({
                "type": "recurring_pattern",
                "title": f"同类异常重复发生 (共{len(same_system_anomalies) + 1}次)",
                "score": min(100, score),
                "confidence": min(100, score),
                "reasons": [
                    f"过去2小时内同类异常发生{len(same_system_anomalies) + 1}次",
                    "可能存在潜在未解决问题"
                ],
                "details": {"recurrence_count": len(same_system_anomalies) + 1},
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def _generate_summary(
        self,
        anomaly: Anomaly,
        top_cause: Dict[str, Any],
        changes: List[ChangeRecord],
        impact_chain: List[Dict[str, Any]],
    ) -> str:
        lines = []

        cause_type = top_cause["type"]
        if cause_type == "change_record":
            lines.append(
                f"最可能根因: 系统 {anomaly.system_name} 在异常发生前执行的变更操作 "
                f"'{top_cause['change_no']}' 可能是异常的主要原因。"
            )
        elif cause_type == "upstream_dependency":
            lines.append(
                f"最可能根因: 上游依赖服务 '{top_cause['service_name']}' "
                f"({top_cause['system_name']}) 存在同期异常，通过依赖传导影响当前系统。"
            )
        elif cause_type == "recurring_pattern":
            lines.append(
                f"最可能根因: 该类型异常存在重复发生模式，表明存在尚未解决的潜在问题。"
            )

        if changes:
            lines.append(
                f"在异常发生前4小时内，系统共执行了 {len(changes)} 次变更操作，"
                f"需重点关注高风险变更的影响。"
            )

        affected_downstream = [
            item for item in impact_chain if item["depth"] > 0 and item["depth"] <= 2
        ]
        if affected_downstream:
            services = [item["service_name"] for item in affected_downstream[:5]]
            lines.append(
                f"异常可能向下游传导，影响的主要服务包括: {', '.join(services)}。"
            )

        lines.append(
            f"建议处理优先级: {self._get_priority_label(anomaly.severity)}。"
        )

        return " ".join(lines)

    def _get_priority_label(self, severity: str) -> str:
        labels = {
            "critical": "紧急(P0) - 立即处理",
            "high": "高(P1) - 15分钟内响应",
            "medium": "中(P2) - 1小时内响应",
            "low": "低(P3) - 4小时内响应",
        }
        return labels.get(severity, "普通")

    async def batch_analyze_pending(self):
        logger.info("Starting batch root cause analysis for pending anomalies...")
        async with async_session_maker() as db:
            result = await db.execute(
                select(Anomaly).where(
                    and_(
                        Anomaly.root_cause_analysis.is_(None),
                        Anomaly.status.in_(["open", "investigating"]),
                    )
                ).limit(50)
            )
            anomalies = result.scalars().all()

        analyzed = 0
        for anomaly in anomalies:
            try:
                await self.analyze_anomaly(str(anomaly.id))
                analyzed += 1
            except Exception as e:
                logger.error(f"Failed to analyze anomaly {anomaly.id}: {e}")

        logger.info(f"Batch analysis completed: {analyzed}/{len(anomalies)} anomalies analyzed")
        return analyzed


root_cause_analyzer = RootCauseAnalyzer()
