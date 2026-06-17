import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..database import async_session_maker
from ..models.log import ProcessedLog
from ..models.baseline import MetricBaseline, BaselineHistory
from ..models.anomaly import Anomaly, BaselineConfig
from ..utils.logger import logger


class DynamicBaselineDetector:
    def __init__(self):
        self._running = False
        self._detection_interval = settings.ANOMALY_DETECT_INTERVAL
        self._stats = {
            "total_metrics_analyzed": 0,
            "total_anomalies_detected": 0,
            "last_run_time": None,
        }

    async def start(self):
        import asyncio
        self._running = True
        logger.info("Dynamic baseline detector started")
        while self._running:
            try:
                await self.run_detection_cycle()
            except Exception as e:
                logger.error(f"Error in detection cycle: {e}", exc_info=True)
            await asyncio.sleep(self._detection_interval)

    async def stop(self):
        self._running = False
        logger.info("Dynamic baseline detector stopped")

    async def run_detection_cycle(self):
        logger.info("Starting anomaly detection cycle...")
        self._stats["last_run_time"] = datetime.now(timezone.utc)

        systems = await self._get_active_systems()
        logger.info(f"Found {len(systems)} systems to analyze")

        for system_name in systems:
            try:
                await self._analyze_system(system_name)
            except Exception as e:
                logger.error(f"Error analyzing system {system_name}: {e}", exc_info=True)

        logger.info(
            f"Detection cycle completed - Analyzed: {self._stats['total_metrics_analyzed']}, "
            f"Anomalies: {self._stats['total_anomalies_detected']}"
        )

    async def _get_active_systems(self) -> List[str]:
        async with async_session_maker() as db:
            since = datetime.now(timezone.utc) - timedelta(hours=2)
            result = await db.execute(
                select(ProcessedLog.system_name)
                .where(ProcessedLog.log_time >= since)
                .distinct()
            )
            return [row[0] for row in result.fetchall()]

    async def _analyze_system(self, system_name: str):
        metrics = ["error_rate", "response_time", "throughput", "availability"]
        time_windows = ["5m", "15m", "1h"]

        for metric_name in metrics:
            for window in time_windows:
                try:
                    await self._detect_anomalies_for_metric(
                        system_name, metric_name, window
                    )
                    self._stats["total_metrics_analyzed"] += 1
                except Exception as e:
                    logger.debug(
                        f"Skipping {system_name}/{metric_name}/{window}: {e}"
                    )

    async def _detect_anomalies_for_metric(
        self, system_name: str, metric_name: str, time_window: str
    ):
        training_data, recent_data = await self._fetch_metric_data(
            system_name, metric_name, time_window
        )

        if training_data is None or len(training_data) < 50:
            return

        config = await self._get_or_create_baseline_config(
            system_name, metric_name
        )

        baseline_result = await self._compute_dynamic_baseline(
            system_name, metric_name, time_window, training_data, config
        )

        if baseline_result is None:
            return

        await self._save_baseline(system_name, metric_name, time_window, baseline_result)

        if recent_data is not None and len(recent_data) > 0:
            anomalies = await self._check_recent_data_against_baseline(
                system_name, metric_name, time_window, recent_data, baseline_result, config
            )

            for anomaly_info in anomalies:
                await self._create_anomaly_record(
                    system_name, metric_name, anomaly_info, baseline_result
                )
                self._stats["total_anomalies_detected"] += 1

    async def _fetch_metric_data(
        self, system_name: str, metric_name: str, time_window: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        async with async_session_maker() as db:
            training_end = datetime.now(timezone.utc) - timedelta(hours=1)
            training_start = training_end - timedelta(days=14)

            training_result = await db.execute(
                select(ProcessedLog)
                .where(
                    and_(
                        ProcessedLog.system_name == system_name,
                        ProcessedLog.metric_name == metric_name,
                        ProcessedLog.time_window == time_window,
                        ProcessedLog.log_time >= training_start,
                        ProcessedLog.log_time < training_end,
                    )
                )
                .order_by(ProcessedLog.log_time)
            )
            training_logs = training_result.scalars().all()

            recent_start = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_result = await db.execute(
                select(ProcessedLog)
                .where(
                    and_(
                        ProcessedLog.system_name == system_name,
                        ProcessedLog.metric_name == metric_name,
                        ProcessedLog.time_window == time_window,
                        ProcessedLog.log_time >= recent_start,
                    )
                )
                .order_by(ProcessedLog.log_time)
            )
            recent_logs = recent_result.scalars().all()

        if not training_logs:
            return None, None

        training_df = pd.DataFrame([
            {
                "time": log.log_time,
                "value": float(log.metric_value),
                "count": log.count,
                "error_count": log.error_count,
            }
            for log in training_logs
        ])
        training_df.set_index("time", inplace=True)
        training_df = training_df[~training_df.index.duplicated(keep="last")]
        training_df = training_df.resample(time_window).mean().interpolate(method="linear", limit=5)

        recent_df = None
        if recent_logs:
            recent_df = pd.DataFrame([
                {
                    "time": log.log_time,
                    "value": float(log.metric_value),
                    "count": log.count,
                    "error_count": log.error_count,
                }
                for log in recent_logs
            ])
            recent_df.set_index("time", inplace=True)

        return training_df, recent_df

    async def _get_or_create_baseline_config(
        self, system_name: str, metric_name: str
    ) -> BaselineConfig:
        async with async_session_maker() as db:
            result = await db.execute(
                select(BaselineConfig).where(
                    and_(
                        BaselineConfig.system_name == system_name,
                        BaselineConfig.metric_name == metric_name,
                    )
                )
            )
            config = result.scalar_one_or_none()

            if config is None:
                config = BaselineConfig(
                    system_name=system_name,
                    metric_name=metric_name,
                    algorithm="dynamic_baseline",
                    sensitivity=0.95,
                    seasonality_daily=True,
                    seasonality_weekly=True,
                    training_window_days=14,
                    upper_threshold_multiplier=3.0,
                    lower_threshold_multiplier=3.0,
                    min_samples=100,
                )
                db.add(config)
                await db.commit()
                await db.refresh(config)

            return config

    async def _compute_dynamic_baseline(
        self,
        system_name: str,
        metric_name: str,
        time_window: str,
        data: pd.DataFrame,
        config: BaselineConfig,
    ) -> Optional[Dict[str, Any]]:
        try:
            values = data["value"].values.astype(float)
            values = values[~np.isnan(values)]

            if len(values) < config.min_samples:
                return None

            clean_values = self._remove_outliers_iqr(values)

            if len(clean_values) < config.min_samples // 2:
                clean_values = values

            daily_component, weekly_component = None, None
            if config.seasonality_daily and len(clean_values) >= 288:
                daily_component = self._extract_daily_seasonality(clean_values, time_window)
            if config.seasonality_weekly and len(clean_values) >= 2016:
                weekly_component = self._extract_weekly_seasonality(clean_values, time_window)

            deseasonalized = clean_values.copy()
            if daily_component is not None:
                n = len(deseasonalized)
                daily_repeated = np.tile(daily_component, n // len(daily_component) + 1)[:n]
                deseasonalized = deseasonalized - daily_repeated
            if weekly_component is not None:
                n = len(deseasonalized)
                weekly_repeated = np.tile(weekly_component, n // len(weekly_component) + 1)[:n]
                deseasonalized = deseasonalized - weekly_repeated

            rolling_window = max(10, min(len(deseasonalized) // 10, 100))
            ewma_mean = pd.Series(deseasonalized).ewm(span=rolling_window, adjust=False).mean().values
            ewma_std = pd.Series(deseasonalized).ewm(span=rolling_window, adjust=False).std().values

            final_mean = np.nanmean(ewma_mean[-100:]) if len(ewma_mean) >= 100 else np.nanmean(ewma_mean)
            final_std = np.nanstd(ewma_std[-100:]) if len(ewma_std) >= 100 else np.nanstd(deseasonalized)

            if final_std <= 0:
                final_std = max(0.001, final_mean * 0.01)

            z_score_upper = config.upper_threshold_multiplier
            z_score_lower = config.lower_threshold_multiplier

            confidence_factor = float(config.sensitivity)
            upper_bound = final_mean + final_std * z_score_upper * (1 + (1 - confidence_factor))
            lower_bound = max(0, final_mean - final_std * z_score_lower * (1 + (1 - confidence_factor)))

            from scipy import stats
            is_stationary = False
            adf_stat, adf_p_value = None, None
            if len(clean_values) >= 50:
                try:
                    adf_result = stats.adfuller(clean_values, maxlag=10)
                    adf_stat, adf_p_value = float(adf_result[0]), float(adf_result[1])
                    is_stationary = adf_p_value < 0.05
                except Exception:
                    pass

            return {
                "baseline_value": float(final_mean),
                "upper_bound": float(upper_bound),
                "lower_bound": float(lower_bound),
                "mean_value": float(np.mean(clean_values)),
                "std_dev": float(np.std(clean_values)),
                "variance": float(np.var(clean_values)),
                "percentile_25": float(np.percentile(clean_values, 25)),
                "percentile_50": float(np.percentile(clean_values, 50)),
                "percentile_75": float(np.percentile(clean_values, 75)),
                "percentile_90": float(np.percentile(clean_values, 90)),
                "percentile_95": float(np.percentile(clean_values, 95)),
                "percentile_99": float(np.percentile(clean_values, 99)),
                "min_value": float(np.min(clean_values)),
                "max_value": float(np.max(clean_values)),
                "sample_count": int(len(clean_values)),
                "algorithm": "dynamic_baseline_ewma",
                "seasonality_components": {
                    "daily": daily_component.tolist() if daily_component is not None else None,
                    "weekly": weekly_component.tolist() if weekly_component is not None else None,
                },
                "trend_components": {
                    "ewma": ewma_mean[-100:].tolist() if len(ewma_mean) > 100 else ewma_mean.tolist(),
                },
                "confidence_level": float(config.sensitivity),
                "is_stationary": is_stationary,
                "adf_statistic": adf_stat,
                "adf_p_value": adf_p_value,
            }
        except Exception as e:
            logger.error(f"Error computing baseline for {system_name}/{metric_name}: {e}", exc_info=True)
            return None

    def _remove_outliers_iqr(self, data: np.ndarray, factor: float = 3.0) -> np.ndarray:
        q1, q3 = np.percentile(data, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        mask = (data >= lower_bound) & (data <= upper_bound)
        filtered = data[mask]
        return filtered if len(filtered) >= len(data) * 0.5 else data

    def _extract_daily_seasonality(self, data: np.ndarray, time_window: str) -> np.ndarray:
        periods_per_day = {
            "1m": 1440,
            "5m": 288,
            "15m": 96,
            "1h": 24,
        }
        p = periods_per_day.get(time_window, 288)
        if len(data) < p:
            return None

        full_days = len(data) // p
        if full_days < 2:
            return None

        reshaped = data[:full_days * p].reshape(full_days, p)
        daily_pattern = np.nanmedian(reshaped, axis=0)
        return daily_pattern - np.nanmean(daily_pattern)

    def _extract_weekly_seasonality(self, data: np.ndarray, time_window: str) -> np.ndarray:
        periods_per_day = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24}
        p = periods_per_day.get(time_window, 288) * 7
        if len(data) < p:
            return None

        full_weeks = len(data) // p
        if full_weeks < 2:
            return None

        reshaped = data[:full_weeks * p].reshape(full_weeks, p)
        weekly_pattern = np.nanmedian(reshaped, axis=0)
        return weekly_pattern - np.nanmean(weekly_pattern)

    async def _save_baseline(
        self,
        system_name: str,
        metric_name: str,
        time_window: str,
        baseline: Dict[str, Any],
    ):
        async with async_session_maker() as db:
            now = datetime.now(timezone.utc)
            period_start = now - timedelta(days=14)
            period_end = now

            new_baseline = MetricBaseline(
                system_name=system_name,
                metric_name=metric_name,
                metric_category=self._get_metric_category(metric_name),
                time_window=time_window,
                period_start=period_start,
                period_end=period_end,
                baseline_value=Decimal(str(baseline["baseline_value"])),
                upper_bound=Decimal(str(baseline["upper_bound"])),
                lower_bound=Decimal(str(baseline["lower_bound"])),
                mean_value=Decimal(str(baseline["mean_value"])),
                std_dev=Decimal(str(baseline["std_dev"])),
                variance=Decimal(str(baseline["variance"])),
                percentile_25=Decimal(str(baseline["percentile_25"])),
                percentile_50=Decimal(str(baseline["percentile_50"])),
                percentile_75=Decimal(str(baseline["percentile_75"])),
                percentile_90=Decimal(str(baseline["percentile_90"])),
                percentile_95=Decimal(str(baseline["percentile_95"])),
                percentile_99=Decimal(str(baseline["percentile_99"])),
                min_value=Decimal(str(baseline["min_value"])),
                max_value=Decimal(str(baseline["max_value"])),
                sample_count=baseline["sample_count"],
                algorithm=baseline["algorithm"],
                seasonality_components=baseline["seasonality_components"],
                trend_components=baseline["trend_components"],
                confidence_level=Decimal(str(baseline["confidence_level"])),
                is_stationary=baseline["is_stationary"],
                adf_statistic=Decimal(str(baseline["adf_statistic"])) if baseline["adf_statistic"] is not None else None,
                adf_p_value=Decimal(str(baseline["adf_p_value"])) if baseline["adf_p_value"] is not None else None,
                is_valid=True,
            )
            db.add(new_baseline)
            await db.commit()

    def _get_metric_category(self, metric_name: str) -> str:
        categories = {
            "error_rate": "error_rate",
            "response_time": "latency",
            "throughput": "throughput",
            "availability": "availability",
        }
        return categories.get(metric_name, "custom")

    async def _check_recent_data_against_baseline(
        self,
        system_name: str,
        metric_name: str,
        time_window: str,
        recent_data: pd.DataFrame,
        baseline: Dict[str, Any],
        config: BaselineConfig,
    ) -> List[Dict[str, Any]]:
        anomalies = []
        upper_bound = baseline["upper_bound"]
        lower_bound = baseline["lower_bound"]
        baseline_value = baseline["baseline_value"]
        std_dev = max(baseline["std_dev"], 0.001)

        for time_idx, row in recent_data.iterrows():
            value = float(row["value"])
            is_anomaly = False
            severity = None
            z_score = (value - baseline_value) / std_dev

            if value > upper_bound:
                is_anomaly = True
                if z_score > 5:
                    severity = "critical"
                elif z_score > 4:
                    severity = "high"
                elif z_score > 3:
                    severity = "medium"
                else:
                    severity = "low"
            elif value < lower_bound and metric_name in ["availability", "throughput"]:
                is_anomaly = True
                deviation_ratio = (lower_bound - value) / max(lower_bound, 0.001)
                if deviation_ratio > 0.5:
                    severity = "critical"
                elif deviation_ratio > 0.3:
                    severity = "high"
                elif deviation_ratio > 0.1:
                    severity = "medium"
                else:
                    severity = "low"

            if is_anomaly:
                anomalies.append({
                    "time": time_idx,
                    "value": value,
                    "baseline_value": baseline_value,
                    "upper_bound": upper_bound,
                    "lower_bound": lower_bound,
                    "z_score": z_score,
                    "severity": severity,
                    "metric_name": metric_name,
                    "time_window": time_window,
                    "count": int(row.get("count", 0)),
                    "error_count": int(row.get("error_count", 0)),
                })

        return anomalies

    async def _create_anomaly_record(
        self,
        system_name: str,
        metric_name: str,
        anomaly_info: Dict[str, Any],
        baseline: Dict[str, Any],
    ):
        async with async_session_maker() as db:
            severity_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            severity_ranking = severity_priority.get(anomaly_info["severity"], 1)

            cooldown_start = datetime.now(timezone.utc) - timedelta(minutes=30)
            existing = await db.execute(
                select(Anomaly).where(
                    and_(
                        Anomaly.system_name == system_name,
                        Anomaly.anomaly_type == metric_name,
                        Anomaly.severity.in_(["critical", "high", "medium", "low"]),
                        Anomaly.status.in_(["open", "investigating"]),
                        Anomaly.detected_time >= cooldown_start,
                    )
                )
            )
            if existing.scalar_one_or_none():
                return

            anomaly_code = self._generate_anomaly_code()

            impact_score = self._calculate_impact_score(
                anomaly_info["severity"], anomaly_info["z_score"], anomaly_info["count"]
            )

            anomaly = Anomaly(
                anomaly_code=anomaly_code,
                system_name=system_name,
                anomaly_type=metric_name,
                severity=anomaly_info["severity"],
                title=self._generate_anomaly_title(
                    system_name, metric_name, anomaly_info
                ),
                description=self._generate_anomaly_description(
                    system_name, metric_name, anomaly_info, baseline
                ),
                detected_time=datetime.now(timezone.utc),
                first_occurrence_time=anomaly_info["time"].to_pydatetime()
                if hasattr(anomaly_info["time"], "to_pydatetime")
                else anomaly_info["time"],
                last_occurrence_time=anomaly_info["time"].to_pydatetime()
                if hasattr(anomaly_info["time"], "to_pydatetime")
                else anomaly_info["time"],
                occurrence_count=1,
                impact_scope="single" if severity_ranking <= 2 else "module",
                impact_score=Decimal(str(impact_score)),
                status="open",
                baseline_snapshot={
                    k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                    for k, v in baseline.items()
                    if k in ["baseline_value", "upper_bound", "lower_bound", "std_dev", "mean_value"]
                },
                metric_values={
                    "value": anomaly_info["value"],
                    "z_score": float(anomaly_info["z_score"]),
                    "baseline": anomaly_info["baseline_value"],
                    "upper_bound": anomaly_info["upper_bound"],
                    "lower_bound": anomaly_info["lower_bound"],
                    "time_window": anomaly_info["time_window"],
                    "log_count": anomaly_info["count"],
                    "error_count": anomaly_info["error_count"],
                },
                is_auto_detected=True,
                detection_algorithm="dynamic_baseline",
                confidence=Decimal(str(max(50, min(100, 80 + abs(float(anomaly_info["z_score"]) * 2))))),
            )
            db.add(anomaly)
            await db.commit()

            logger.info(
                f"Created anomaly {anomaly_code} for {system_name}/{metric_name}: "
                f"value={anomaly_info['value']:.4f}, z_score={anomaly_info['z_score']:.2f}, "
                f"severity={anomaly_info['severity']}"
            )

    def _generate_anomaly_code(self) -> str:
        now = datetime.now(timezone.utc)
        import random
        random_str = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
        return f"ANOM{now.strftime('%Y%m%d%H%M%S')}{random_str}"

    def _calculate_impact_score(
        self, severity: str, z_score: float, log_count: int
    ) -> float:
        severity_weights = {"critical": 100, "high": 75, "medium": 50, "low": 25}
        base = severity_weights.get(severity, 25)
        z_factor = min(abs(z_score) * 3, 30)
        volume_factor = min(log_count / 100, 20) if log_count > 0 else 0
        return min(100, base + z_factor + volume_factor)

    def _generate_anomaly_title(
        self, system_name: str, metric_name: str, anomaly_info: Dict[str, Any]
    ) -> str:
        metric_labels = {
            "error_rate": "错误率",
            "response_time": "响应时间",
            "throughput": "吞吐量",
            "availability": "可用性",
        }
        label = metric_labels.get(metric_name, metric_name)
        severity_labels = {
            "critical": "严重",
            "high": "高危",
            "medium": "中等",
            "low": "低危",
        }
        sev_label = severity_labels.get(anomaly_info["severity"], "")
        return f"[{sev_label}] {system_name} - {label}异常 (Z={anomaly_info['z_score']:.1f})"

    def _generate_anomaly_description(
        self,
        system_name: str,
        metric_name: str,
        anomaly_info: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> str:
        metric_labels = {
            "error_rate": "错误率",
            "response_time": "响应时间",
            "throughput": "吞吐量",
            "availability": "可用性",
        }
        label = metric_labels.get(metric_name, metric_name)
        value = anomaly_info["value"]
        baseline_val = anomaly_info["baseline_value"]
        deviation_pct = ((value - baseline_val) / max(baseline_val, 0.001)) * 100

        return (
            f"系统 {system_name} 的 {label} 指标出现异常。\n"
            f"当前值: {value:.4f}\n"
            f"基线值: {baseline_val:.4f}\n"
            f"偏离程度: {deviation_pct:+.2f}% (Z-Score: {anomaly_info['z_score']:.2f})\n"
            f"上界阈值: {anomaly_info['upper_bound']:.4f}\n"
            f"下界阈值: {anomaly_info['lower_bound']:.4f}\n"
            f"时间窗口: {anomaly_info['time_window']}\n"
            f"关联日志数: {anomaly_info['count']}, 错误日志: {anomaly_info['error_count']}"
        )


baseline_detector = DynamicBaselineDetector()
