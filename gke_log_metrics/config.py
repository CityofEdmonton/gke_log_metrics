"""Configuration loader for gke_log_metrics.

Reads defaults, `.configs` (environment variables format) and OS environment variables (env wins).
"""
import os
from typing import Optional

from .exceptions import ValidationError


class Config:
    def __init__(self, config_file: Optional[str] = None):
        # defaults
        self.APP_NAME = "default_app"
        self.APP_TYPE = "default_type"
        self.OWNER = "default_owner"
        self.METRICS_ENABLED = True
        self.PROMETHEUS_ENABLED = False
        self.LOG_LEVEL = "INFO"

        # load file if provided (environment variables format: KEY=VALUE)
        cfg_path = config_file or os.getenv("CONFIG_FILE") or os.path.join(os.getcwd(), ".configs")
        if cfg_path and os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        # skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue
                        # parse KEY=VALUE format
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if hasattr(self, key):
                                setattr(self, key, value)
            except Exception as e:
                raise ValidationError(f"Failed to read config file {cfg_path}: {e}")

        # environment overrides
        self.APP_NAME = os.getenv("APP_NAME", self.APP_NAME)
        self.APP_TYPE = os.getenv("APP_TYPE", self.APP_TYPE)
        self.OWNER = os.getenv("OWNER", self.OWNER)
        self.METRICS_ENABLED = os.getenv("METRICS_ENABLED", str(self.METRICS_ENABLED)).lower() == "true"
        self.PROMETHEUS_ENABLED = os.getenv("PROMETHEUS_ENABLED", str(self.PROMETHEUS_ENABLED)).lower() == "true"
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", self.LOG_LEVEL).upper()

    def validate(self) -> None:
        # currently no mandatory fields; placeholder for future rules
        if not self.APP_NAME:
            raise ValidationError("APP_NAME must be set")
