import asyncio
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict
from decimal import Decimal
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..database import async_session_maker
from ..models.log import RawLog, ProcessedLog
from ..utils.logger import logger


class LogCollector:
    def __init__(self):
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_size = settings.KAFKA_BATCH_SIZE
        self._flush_interval = 5
        self._running = False
        self._process_tasks: List[asyncio.Task] = []
        self._processing_stats = {
            "total_received": 0,
            "total_processed": 0,
            "total_failed": 0,
            "last_flush_time": time.time(),
            "per_system_counts": defaultdict(int),
        }

    async def start(self):
        self._running = True
        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC_LOGS,
            bootstrap_servers=settings.KAFKA_BROKERS_LIST,
            group_id=settings.KAFKA_GROUP_ID,
            enable_auto_commit=True,
            auto_commit_interval_ms=settings.KAFKA_AUTO_COMMIT_INTERVAL_MS,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            max_poll_records=settings.KAFKA_BATCH_SIZE,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )

        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKERS_LIST,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=3,
            linger_ms=5,
            batch_size=16384,
        )

        await self.consumer.start()
        await self.producer.start()
        logger.info("Log collector started, Kafka consumer initialized")

        for i in range(settings.LOG_PROCESS_CONCURRENCY):
            task = asyncio.create_task(self._consume_loop(worker_id=i))
            self._process_tasks.append(task)

        asyncio.create_task(self._periodic_flush())
        asyncio.create_task(self._periodic_aggregate())
        asyncio.create_task(self._stats_reporter())

        logger.info(f"Started {settings.LOG_PROCESS_CONCURRENCY} log processing workers")

    async def stop(self):
        self._running = False
        for task in self._process_tasks:
            task.cancel()
        await self._flush_batch()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        logger.info("Log collector stopped")

    async def _consume_loop(self, worker_id: int):
        logger.info(f"Log worker {worker_id} started")
        try:
            async for msg in self.consumer:
                if not self._running:
                    break
                try:
                    log_data = msg.value
                    processed = await self._process_single_log(log_data)
                    if processed:
                        self._batch_buffer.append(processed)
                        self._processing_stats["total_received"] += 1
                        self._processing_stats["per_system_counts"][processed["system_name"]] += 1

                    if len(self._batch_buffer) >= self._batch_size:
                        await self._flush_batch()

                except Exception as e:
                    self._processing_stats["total_failed"] += 1
                    logger.error(f"Worker {worker_id} error processing log: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info(f"Log worker {worker_id} cancelled")
        except Exception as e:
            logger.error(f"Worker {worker_id} fatal error: {e}", exc_info=True)

    async def _process_single_log(self, log_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        required_fields = ["system_name", "log_time", "message", "log_level"]
        for field in required_fields:
            if field not in log_data:
                return None

        log_time = log_data["log_time"]
        if isinstance(log_time, str):
            try:
                if log_time.endswith("Z"):
                    log_time = log_time.replace("Z", "+00:00")
                log_time = datetime.fromisoformat(log_time)
            except ValueError:
                log_time = datetime.now(timezone.utc)
        elif not isinstance(log_time, datetime):
            log_time = datetime.now(timezone.utc)

        if log_time.tzinfo is None:
            log_time = log_time.replace(tzinfo=timezone.utc)

        return {
            "system_name": str(log_data["system_name"])[:100],
            "host_ip": str(log_data.get("host_ip", ""))[:45] or None,
            "log_time": log_time,
            "log_level": str(log_data["log_level"]).upper()[:10],
            "module": str(log_data.get("module", ""))[:100] or None,
            "trace_id": str(log_data.get("trace_id", ""))[:64] or None,
            "message": str(log_data["message"]),
            "tags": log_data.get("tags"),
            "extra_data": log_data.get("extra_data"),
            "is_processed": False,
            "partition_key": self._get_partition_key(log_data["system_name"]),
        }

    def _get_partition_key(self, system_name: str) -> str:
        now = datetime.now(timezone.utc)
        return f"{system_name}_{now.strftime('%Y%m%d')}"

    async def _flush_batch(self):
        if not self._batch_buffer:
            return

        batch = self._batch_buffer.copy()
        self._batch_buffer.clear()
        self._processing_stats["last_flush_time"] = time.time()

        try:
            async with async_session_maker() as db:
                raw_logs = []
                for item in batch:
                    raw_logs.append(RawLog(**item))

                db.add_all(raw_logs)
                await db.commit()
                self._processing_stats["total_processed"] += len(batch)

                anomaly_logs = [
                    log for log in batch
                    if log["log_level"] in ("ERROR", "FATAL", "CRITICAL")
                ]
                if anomaly_logs and self.producer:
                    for log in anomaly_logs:
                        await self.producer.send_and_wait(
                            settings.KAFKA_TOPIC_ANOMALIES,
                            value={
                                "type": "error_log",
                                "log": log,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )

        except Exception as e:
            logger.error(f"Failed to flush log batch: {e}", exc_info=True)
            self._processing_stats["total_failed"] += len(batch)

    async def _periodic_flush(self):
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._batch_buffer:
                    time_since_flush = time.time() - self._processing_stats["last_flush_time"]
                    if time_since_flush >= self._flush_interval:
                        await self._flush_batch()
            except Exception as e:
                logger.error(f"Periodic flush error: {e}", exc_info=True)

    async def _periodic_aggregate(self):
        while self._running:
            try:
                await asyncio.sleep(300)
                await self._aggregate_metrics()
            except Exception as e:
                logger.error(f"Aggregation error: {e}", exc_info=True)

    async def _aggregate_metrics(self):
        logger.info("Starting metrics aggregation...")
        async with async_session_maker() as db:
            time_windows = [
                ("1m", "1 minute"),
                ("5m", "5 minutes"),
                ("15m", "15 minutes"),
                ("1h", "1 hour"),
            ]

            for window_name, window_sql in time_windows:
                try:
                    await self._aggregate_for_window(db, window_name, window_sql)
                except Exception as e:
                    logger.error(f"Aggregation for window {window_name} failed: {e}")

        await db.commit()
        logger.info("Metrics aggregation completed")

    async def _aggregate_for_window(self, db: AsyncSession, window_name: str, window_sql: str):
        query = text(f"""
            WITH time_buckets AS (
                SELECT
                    date_trunc('{window_sql.replace(" ", "")}', log_time) AS bucket_start,
                    system_name,
                    log_level,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE log_level IN ('ERROR', 'FATAL', 'CRITICAL')) as error_count,
                    COUNT(*) FILTER (WHERE log_level = 'WARN') as warn_count
                FROM raw_logs
                WHERE log_time >= NOW() - INTERVAL '2 hours'
                  AND is_processed = false
                GROUP BY 1, 2, 3
            )
            SELECT
                bucket_start,
                system_name,
                SUM(count) as total_count,
                SUM(error_count) as total_errors,
                SUM(warn_count) as total_warns
            FROM time_buckets
            GROUP BY 1, 2
            ORDER BY 1, 2
        """)

        result = await db.execute(query)
        rows = result.fetchall()

        for row in rows:
            bucket_start, system_name, count, error_count, warn_count = row
            error_rate = (float(error_count) / float(count) * 100) if count > 0 else 0.0

            processed = ProcessedLog(
                system_name=system_name,
                metric_name="error_rate",
                log_time=bucket_start,
                time_window=window_name,
                metric_value=Decimal(str(round(error_rate, 4))),
                count=int(count),
                error_count=int(error_count),
                warn_count=int(warn_count),
                avg_value=Decimal(str(round(error_rate, 4))),
            )
            db.add(processed)

    async def _stats_reporter(self):
        while self._running:
            try:
                await asyncio.sleep(60)
                stats = self._processing_stats.copy()
                per_system = dict(stats["per_system_counts"])
                top_systems = sorted(per_system.items(), key=lambda x: x[1], reverse=True)[:5]

                logger.info(
                    f"Log collection stats - Received: {stats['total_received']}, "
                    f"Processed: {stats['total_processed']}, Failed: {stats['total_failed']}, "
                    f"Buffer size: {len(self._batch_buffer)}, "
                    f"Top systems: {top_systems}"
                )
                self._processing_stats["per_system_counts"].clear()
            except Exception as e:
                logger.error(f"Stats reporter error: {e}", exc_info=True)


log_collector = LogCollector()
