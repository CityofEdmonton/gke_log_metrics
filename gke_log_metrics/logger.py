"""Logger API: normal logs + JSON metric logs + Prometheus integration."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import Config
from .metrics import metrics


class Logger:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.logger = logging.getLogger("gke_log_metrics")
        self.logger.setLevel(getattr(logging, cfg.LOG_LEVEL, logging.INFO))

        # small stdout handler for normal logs
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            self.logger.addHandler(ch)

        # no internal json counter anymore; json_metric receives name/value

    def log(self, message: str, info: Optional[Dict[str, Any]] = None, level: str = "info", extra: Optional[Dict[str, Any]] = None, app_name: Optional[str] = None, app_type: Optional[str] = None) -> None:
        """Normal application log that follows LOG_LEVEL."""
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        if extra:
            log_method(f"{message} | extra={extra} | info={info}")
        else:
            log_method(f"{message} | info={info}")

    def json_metric(self, name: str, value: float = 1.0, info: Optional[Dict[str, Any]] = None, app_name: Optional[str] = None, app_type: Optional[str] = None, extra: Optional[Dict[str, Any]] = None, message: Optional[str] = None) -> None:
        """Emit a log-based metric as JSON to STDOUT.

        Signature mirrors `prometheus_metric` by accepting `name` and `value`.
        If `METRICS_ENABLED` in config is True, this will be printed regardless
        of `LOG_LEVEL`.
        """
        if not self.cfg.METRICS_ENABLED:
            return

        entry = {
            "info": info or {},
            "app_name": app_name or self.cfg.APP_NAME,
            "app_type": app_type or self.cfg.APP_TYPE,
            "owner": self.cfg.OWNER,
            # include metric identification and value
            "metric_name": name,
            "metric_value": value,
            "event_type": "metric",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # optional human message
        if message:
            entry["message"] = message

        if extra:
            for k, v in extra.items():
                if k in entry:
                    continue
                entry[k] = v

        # Print to stdout for log-based metrics ingestion
        print(json.dumps(entry))

    def prometheus_metric(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Update internal Prometheus-style metrics."""
        # For simplicity, treat all as counters when incrementing
        metrics.increment(name, int(value))

    def metric(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None, message: Optional[str] = None, info: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, Any]] = None, app_name: Optional[str] = None, app_type: Optional[str] = None) -> None:
        """Unified metric API: updates Prometheus metrics and emits JSON log-based metric.

        Behavior:
        - If PROMETHEUS_ENABLED: update internal Prometheus metrics.
        - If METRICS_ENABLED: emit JSON metric to STDOUT.
        """
        if self.cfg.PROMETHEUS_ENABLED:
            # update prometheus-style metric
            self.prometheus_metric(name, value, labels=labels)

        if self.cfg.METRICS_ENABLED:
            # build extra payload and call json_metric with name/value
            extra2 = extra or {}
            # include labels and other metadata
            if labels:
                extra2.setdefault("labels", labels)
            # pass optional human message through
            # determine effective app_name/app_type using config defaults when None
            effective_app_name = app_name or self.cfg.APP_NAME
            effective_app_type = app_type or self.cfg.APP_TYPE

            self.json_metric(name, value, info=info, extra=extra2, app_name=effective_app_name, app_type=effective_app_type, message=message)

    def metrics_to_prometheus(self) -> str:
        return metrics.to_prometheus()


def get_logger(cfg: Config) -> Logger:
    cfg.validate()
    return Logger(cfg)
