from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import uuid
import json
import numpy as np
from decimal import Decimal
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import array
from ..database import async_session_maker
from ..models.anomaly import Anomaly
from ..models.report import CaseLibrary, anomaly_case_matches
from ..utils.logger import logger


class CaseMatcher:
    def __init__(self):
        self._feature_weights = {
            "system_name": 0.15,
            "anomaly_type": 0.25,
            "severity": 0.10,
            "title_similarity": 0.20,
            "tags_overlap": 0.10,
            "root_cause_category": 0.20,
        }

    async def find_similar_cases(
        self,
        anomaly_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        min_score: float = 0.5,
    ) -> List[Dict[str, Any]]:
        if anomaly_id:
            target = await self._load_anomaly_as_event(anomaly_id)
        elif event_data:
            target = event_data
        else:
            return []

        if target is None:
            return []

        all_cases = await self._load_all_cases()

        matches = []
        for case in all_cases:
            score = self._calculate_similarity(target, case)
            if score >= min_score:
                matches.append({
                    "case_id": str(case.id),
                    "case_no": case.case_no,
                    "title": case.title,
                    "system_name": case.system_name,
                    "anomaly_type": case.anomaly_type,
                    "severity": case.severity,
                    "category": case.category,
                    "match_score": round(score, 4),
                    "symptom_description": case.symptom_description,
                    "root_cause": case.root_cause,
                    "root_cause_category": case.root_cause_category,
                    "resolution_steps": case.resolution_steps,
                    "recommended_playbook_ids": (
                        [str(p) for p in case.recommended_playbook_ids]
                        if case.recommended_playbook_ids else []
                    ),
                    "prevention_measures": case.prevention_measures,
                    "occurrence_count": case.occurrence_count,
                    "resolution_time_avg_minutes": case.resolution_time_avg_minutes,
                    "success_rate": float(case.success_rate) if case.success_rate else None,
                    "match_details": self._get_match_details(target, case),
                })

        matches.sort(key=lambda x: x["match_score"], reverse=True)
        top_matches = matches[:top_k]

        if anomaly_id and top_matches:
            await self._save_case_matches(anomaly_id, top_matches)

        logger.info(
            f"Case matching completed for {anomaly_id or 'manual_event'}: "
            f"found {len(top_matches)} matches above {min_score}"
        )

        return top_matches

    async def import_event_to_case_library(
        self,
        event_data: Dict[str, Any],
        created_by: Optional[str] = None,
        source_anomaly_id: Optional[str] = None,
    ) -> Optional[CaseLibrary]:
        try:
            async with async_session_maker() as db:
                case_no = self._generate_case_no()

                case = CaseLibrary(
                    case_no=case_no,
                    title=event_data.get("title", ""),
                    system_name=event_data.get("system_name"),
                    anomaly_type=event_data.get("anomaly_type"),
                    severity=event_data.get("severity"),
                    category=event_data.get("category"),
                    tags=event_data.get("tags"),
                    keywords=event_data.get("keywords") or self._extract_keywords(
                        event_data.get("title", "") + " " +
                        event_data.get("symptom_description", "")
                    ),
                    symptom_description=event_data.get("symptom_description", ""),
                    root_cause=event_data.get("root_cause", ""),
                    root_cause_category=event_data.get("root_cause_category"),
                    resolution_steps=event_data.get("resolution_steps", []),
                    recommended_playbook_ids=(
                        [uuid.UUID(p) for p in event_data["recommended_playbook_ids"]]
                        if event_data.get("recommended_playbook_ids") else None
                    ),
                    affected_services=event_data.get("affected_services"),
                    prevention_measures=event_data.get("prevention_measures"),
                    reference_links=event_data.get("reference_links"),
                    occurrence_count=event_data.get("occurrence_count", 1),
                    resolution_time_avg_minutes=event_data.get("resolution_time_avg_minutes"),
                    success_rate=(
                        Decimal(str(event_data["success_rate"]))
                        if event_data.get("success_rate") is not None else Decimal("100.0")
                    ),
                    is_verified=event_data.get("is_verified", False),
                    feature_vector=self._compute_feature_vector(event_data),
                    imported_from=event_data.get("imported_from", "manual"),
                    source_anomaly_id=(
                        uuid.UUID(source_anomaly_id) if source_anomaly_id else None
                    ),
                    created_by=(
                        uuid.UUID(created_by) if created_by else None
                    ),
                )

                db.add(case)
                await db.commit()
                await db.refresh(case)

                logger.info(f"Imported case {case_no} to library from {case.imported_from}")
                return case

        except Exception as e:
            logger.error(f"Failed to import event to case library: {e}", exc_info=True)
            return None

    async def promote_anomaly_to_case(
        self,
        anomaly_id: str,
        resolution_note: str,
        root_cause: str,
        created_by: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[CaseLibrary]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Anomaly).where(Anomaly.id == anomaly_id)
            )
            anomaly = result.scalar_one_or_none()
            if anomaly is None:
                return None

            event_data = {
                "title": anomaly.title,
                "system_name": anomaly.system_name,
                "anomaly_type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "symptom_description": anomaly.description or "",
                "root_cause": root_cause,
                "root_cause_category": (extra_data or {}).get("root_cause_category"),
                "resolution_steps": (extra_data or {}).get("resolution_steps", [
                    {"step": "1", "action": "修复记录", "note": resolution_note}
                ]),
                "affected_services": anomaly.affected_services,
                "category": (extra_data or {}).get("category", anomaly.anomaly_type),
                "tags": anomaly.affected_services,
                "keywords": self._extract_keywords(anomaly.title + " " + (anomaly.description or "")),
                "prevention_measures": (extra_data or {}).get("prevention_measures"),
                "resolution_time_avg_minutes": None,
                "imported_from": "system",
                "is_verified": False,
            }

        return await self.import_event_to_case_library(
            event_data,
            created_by=created_by,
            source_anomaly_id=anomaly_id,
        )

    async def _load_anomaly_as_event(
        self, anomaly_id: str
    ) -> Optional[Dict[str, Any]]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Anomaly).where(Anomaly.id == anomaly_id)
            )
            anomaly = result.scalar_one_or_none()
            if anomaly is None:
                return None

            return {
                "system_name": anomaly.system_name,
                "anomaly_type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "title": anomaly.title,
                "description": anomaly.description,
                "impact_scope": anomaly.impact_scope,
                "tags": anomaly.affected_services,
                "root_cause_category": (
                    anomaly.root_cause_analysis.get("top_category")
                    if anomaly.root_cause_analysis else None
                ),
                "keywords": self._extract_keywords(
                    anomaly.title + " " + (anomaly.description or "")
                ),
            }

    async def _load_all_cases(self) -> List[CaseLibrary]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(CaseLibrary).where(CaseLibrary.is_verified == True)
            )
            return list(result.scalars().all())

    def _calculate_similarity(
        self, target: Dict[str, Any], case: CaseLibrary
    ) -> float:
        scores = {}

        scores["system_name"] = (
            1.0 if target.get("system_name") == case.system_name
            else 0.3 if target.get("system_name") and case.system_name
            and target["system_name"].split("_")[0] == case.system_name.split("_")[0]
            else 0.0
        )

        scores["anomaly_type"] = (
            1.0 if target.get("anomaly_type") == case.anomaly_type else 0.0
        )

        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        t_sev = severity_order.get(target.get("severity", "").lower(), 0)
        c_sev = severity_order.get((case.severity or "").lower(), 0)
        if t_sev > 0 and c_sev > 0:
            scores["severity"] = 1.0 - abs(t_sev - c_sev) / 4.0
        else:
            scores["severity"] = 0.5

        target_title = target.get("title", "") or target.get("symptom_description", "")
        case_title = case.title
        scores["title_similarity"] = self._text_similarity(target_title, case_title)

        target_tags = set(target.get("tags") or [])
        case_tags = set(case.tags or [])
        if target_tags or case_tags:
            overlap = target_tags & case_tags
            union = target_tags | case_tags
            scores["tags_overlap"] = len(overlap) / max(len(union), 1)
        else:
            scores["tags_overlap"] = 0.5

        scores["root_cause_category"] = (
            1.0 if target.get("root_cause_category") and case.root_cause_category
            and target["root_cause_category"] == case.root_cause_category
            else 0.5 if target.get("root_cause_category") or case.root_cause_category
            else 0.3
        )

        weighted_total = 0.0
        weight_sum = 0.0
        for key, weight in self._feature_weights.items():
            score = scores.get(key, 0.0)
            weighted_total += score * weight
            weight_sum += weight

        return weighted_total / max(weight_sum, 1.0)

    def _get_match_details(
        self, target: Dict[str, Any], case: CaseLibrary
    ) -> Dict[str, float]:
        details = {}

        details["system_match"] = target.get("system_name") == case.system_name
        details["type_match"] = target.get("anomaly_type") == case.anomaly_type

        target_title = target.get("title", "") or ""
        case_title = case.title or ""
        details["text_similarity"] = round(
            self._text_similarity(target_title, case_title), 4
        )

        return details

    def _text_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        text1 = text1.lower()
        text2 = text2.lower()

        words1 = set(self._tokenize(text1))
        words2 = set(self._tokenize(text2))

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union) if union else 0.0

        from difflib import SequenceMatcher
        seq_ratio = SequenceMatcher(None, text1, text2).ratio()

        return 0.6 * jaccard + 0.4 * seq_ratio

    def _tokenize(self, text: str) -> List[str]:
        import re
        tokens = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z_][a-zA-Z0-9_]{2,}', text.lower())
        return tokens

    def _extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        tokens = self._tokenize(text)
        token_freq = defaultdict(int)
        for t in tokens:
            token_freq[t] += 1

        sorted_tokens = sorted(token_freq.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tokens[:max_keywords]]

    def _compute_feature_vector(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        system_name = event_data.get("system_name", "")
        anomaly_type = event_data.get("anomaly_type", "")
        severity = event_data.get("severity", "")
        title = event_data.get("title", "")
        keywords = event_data.get("keywords", self._extract_keywords(title))

        return {
            "system_hash": hash(system_name) % 1000,
            "type_hash": hash(anomaly_type) % 1000,
            "severity_code": {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity.lower(), 0),
            "keyword_fingerprint": [hash(k) % 10000 for k in keywords[:10]],
            "category": event_data.get("category", anomaly_type),
        }

    def _generate_case_no(self) -> str:
        now = datetime.now(timezone.utc)
        import random
        rand = ''.join(random.choices('0123456789ABCDEF', k=6))
        return f"CASE{now.strftime('%Y%m%d%H%M%S')}{rand}"

    async def _save_case_matches(
        self, anomaly_id: str, matches: List[Dict[str, Any]]
    ):
        try:
            async with async_session_maker() as db:
                for match in matches:
                    insert_stmt = anomaly_case_matches.insert().values(
                        anomaly_id=anomaly_id,
                        case_id=match["case_id"],
                        match_score=match["match_score"],
                    )
                    try:
                        await db.execute(insert_stmt)
                    except Exception:
                        pass
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save case matches: {e}")


case_matcher = CaseMatcher()
