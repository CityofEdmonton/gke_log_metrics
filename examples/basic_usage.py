"""Example usage of gke_log_metrics library."""
import os
from gke_log_metrics import Config, get_logger


def main():
    # Create config (loads from .configs or env vars)
    cfg = Config()
    
    # Get logger instance
    logger = get_logger(cfg)
    
    print("=== Normal Log Example ===")
    logger.log("Application started", info={"version": "1.0", "phase": "startup"})
    
    print("\n=== JSON Metric Examples ===")
    
    # Emit a JSON metric for log-based metrics ingestion
    logger.json_metric(
        "backup_check_completed",
        info={
            "job": "daily_backup",
            "status": "success",
            "duration_seconds": 45.3
        },
        extra={
            "backup_size_bytes": 1048576,
            "files_backed_up": 250
        }
    )
    
    # Counter increments per json_metric call
    logger.json_metric("backup_check_completed", info={"job": "weekly_backup", "status": "success"})
    
    print("\n=== Unified Metric API (Both JSON + Prometheus) ===")
    
    # This will:
    # 1. Update Prometheus metrics (if PROMETHEUS_ENABLED)
    # 2. Emit JSON log (if METRICS_ENABLED)
    logger.metric(
        name="backup_checks_total",
        value=1,
        labels={"job": "daily_backup", "status": "success"},
        message="Backup check succeeded",
        info={"duration": 45.3}
    )
    
    logger.metric(
        name="backup_checks_total",
        value=1,
        labels={"job": "weekly_backup", "status": "failed"},
        message="Backup check failed",
        info={"error": "timeout"}
    )
    
    print("\n=== Prometheus Metrics (if enabled) ===")
    print(logger.metrics_to_prometheus())
    
    print("\n=== Configuration Info ===")
    print(f"APP_NAME: {cfg.APP_NAME}")
    print(f"APP_TYPE: {cfg.APP_TYPE}")
    print(f"METRICS_ENABLED: {cfg.METRICS_ENABLED}")
    print(f"PROMETHEUS_ENABLED: {cfg.PROMETHEUS_ENABLED}")
    print(f"LOG_LEVEL: {cfg.LOG_LEVEL}")


if __name__ == "__main__":
    main()
