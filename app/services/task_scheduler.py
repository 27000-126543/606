import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import JobEvent, EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from .log_collector import log_collector
from .anomaly_detector import baseline_detector
from .root_cause_analyzer import root_cause_analyzer
from .ticket_service import ticket_service
from .report_service import report_service
from ..utils.logger import logger


class TaskScheduler:
    def __init__(self):
        self.scheduler: AsyncIOScheduler = None
        self._job_ids: List[str] = []
        self._task_stats: Dict[str, Dict[str, Any]] = {}

    async def start(self):
        self.scheduler = AsyncIOScheduler(
            timezone="Asia/Shanghai",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )

        self._register_jobs()
        self.scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self.scheduler.start()

        logger.info("Task scheduler started with jobs: %s", self._job_ids)

    async def stop(self):
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Task scheduler stopped")

    def _register_jobs(self):
        self._add_job(
            id="process_new_anomalies_for_tickets",
            func=ticket_service.process_new_anomalies,
            trigger=IntervalTrigger(minutes=1),
            description="新异常工单自动创建",
        )

        self._add_job(
            id="batch_root_cause_analysis",
            func=root_cause_analyzer.batch_analyze_pending,
            trigger=IntervalTrigger(minutes=2),
            description="待处理异常根因分析",
        )

        self._add_job(
            id="work_order_escalations",
            func=ticket_service.process_escalations_and_reminders,
            trigger=IntervalTrigger(minutes=15),
            description="工单升级与催办处理",
        )

        self._add_job(
            id="daily_report_generation",
            func=self._generate_daily_report,
            trigger=CronTrigger(hour=0, minute=30),
            description="每日凌晨报表生成",
        )

        self._add_job(
            id="cleanup_old_exports",
            func=self._cleanup_export_files,
            trigger=CronTrigger(hour=2, minute=0),
            description="清理过期导出文件",
        )

        self._add_job(
            id="hourly_health_check",
            func=self._system_health_check,
            trigger=IntervalTrigger(hours=1),
            description="系统健康检查",
        )

        self._add_job(
            id="anomaly_detection_cycle",
            func=baseline_detector.run_detection_cycle,
            trigger=IntervalTrigger(minutes=5),
            description="基线异常检测周期",
        )

    def _add_job(
        self,
        id: str,
        func: Callable,
        trigger: Any,
        description: str = "",
    ):
        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=id,
            name=description or id,
            replace_existing=True,
        )
        self._job_ids.append(id)
        self._task_stats[id] = {
            "description": description,
            "run_count": 0,
            "success_count": 0,
            "error_count": 0,
            "last_run_at": None,
            "last_duration_ms": None,
            "last_error": None,
        }
        logger.info(f"Registered scheduled job: {id} - {description}")

    async def _generate_daily_report(self):
        logger.info("Starting scheduled daily report generation...")
        try:
            report = await report_service.generate_daily_report()
            if report:
                try:
                    pdf_path = await report_service.export_report_pdf(str(report.id))
                    logger.info(f"PDF report generated: {pdf_path}")
                except Exception as e:
                    logger.error(f"PDF generation failed: {e}")

                try:
                    excel_path = report_service.export_report_excel(str(report.id))
                    logger.info(f"Excel report generated: {excel_path}")
                except Exception as e:
                    logger.error(f"Excel generation failed: {e}")

            logger.info(f"Daily report generation completed: {report.report_date.date()}")
        except Exception as e:
            logger.error(f"Daily report generation error: {e}", exc_info=True)

    async def _cleanup_export_files(self):
        import os
        from ..config import settings

        export_dir = settings.REPORT_EXPORT_DIR
        max_age_days = settings.MAX_EXPORT_FILE_AGE
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400

        cleaned = 0
        if os.path.exists(export_dir):
            for filename in os.listdir(export_dir):
                filepath = os.path.join(export_dir, filename)
                try:
                    if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                        os.remove(filepath)
                        cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to remove file {filepath}: {e}")

        logger.info(f"Cleanup completed: removed {cleaned} old export files")

    async def _system_health_check(self):
        from ..database import async_session_maker
        from sqlalchemy import select, text

        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_ok": False,
            "kafka_ok": False,
            "redis_ok": False,
            "active_jobs": len(self._job_ids),
            "collector_stats": {
                "total_processed": log_collector._processing_stats.get("total_processed", 0),
                "total_failed": log_collector._processing_stats.get("total_failed", 0),
            },
            "detector_stats": {
                "total_anomalies": baseline_detector._stats.get("total_anomalies_detected", 0),
                "total_metrics": baseline_detector._stats.get("total_metrics_analyzed", 0),
            },
        }

        try:
            async with async_session_maker() as db:
                result = await db.execute(text("SELECT 1"))
                health_data["database_ok"] = result.scalar() == 1
        except Exception as e:
            logger.error(f"Health check - DB connection failed: {e}")

        logger.info(
            f"Health check - DB: {health_data['database_ok']}, "
            f"Processed logs: {health_data['collector_stats']['total_processed']}, "
            f"Anomalies detected: {health_data['detector_stats']['total_anomalies']}"
        )
        return health_data

    def _on_job_event(self, event: JobEvent):
        job_id = event.job_id
        if job_id not in self._task_stats:
            return

        stats = self._task_stats[job_id]
        stats["run_count"] += 1
        stats["last_run_at"] = datetime.now(timezone.utc)

        if event.code == EVENT_JOB_EXECUTED:
            stats["success_count"] += 1
            stats["last_duration_ms"] = int(getattr(event, "scheduled_run_time", 0) or 0)
            stats["last_error"] = None
            logger.info(f"Job {job_id} executed successfully")

        elif event.code == EVENT_JOB_ERROR:
            stats["error_count"] += 1
            stats["last_error"] = str(getattr(event, "exception", "Unknown"))
            logger.error(
                f"Job {job_id} failed: {stats['last_error']}",
                exc_info=getattr(event, "exception", None),
            )

    def get_job_status(self) -> Dict[str, Any]:
        statuses = {}
        for job_id, stats in self._task_stats.items():
            job = self.scheduler.get_job(job_id) if self.scheduler else None
            statuses[job_id] = {
                **stats,
                "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
                "is_running": job is not None,
            }
        return statuses


task_scheduler = TaskScheduler()
