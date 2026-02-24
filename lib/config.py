"""
Configuration management for job checker.
Loads configuration from environment variables and files.
"""
import os
import json
import logging
import runpy
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Load .env file into environment (optional). Prefer python-dotenv when available,
# but fall back to a small parser to avoid adding a hard dependency.
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env using python-dotenv")
except Exception:
    pass

class BackupJobConfig:
    """Configuration for a single backup job."""
    
    def __init__(
        self,
        job_name: str,
        instance_id: str,
        storage_type: str,
        bucket_name: str,
        prefix: str = "",
        timeout_seconds: int = 30,
        retention_hours: int = 24,
        job_type: str = "gcs_files",
    ):
        self.job_name = job_name
        self.instance_id = instance_id
        self.storage_type = storage_type  # "gcs"
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.timeout_seconds = timeout_seconds
        self.retention_hours = retention_hours
        self.job_type = job_type  # e.g. 'gcs_files' or 'postgres_backup'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_name": self.job_name,
            "instance_id": self.instance_id,
            "storage_type": self.storage_type,
            "bucket_name": self.bucket_name,
            "prefix": self.prefix,
            "timeout_seconds": self.timeout_seconds,
            "retention_hours": self.retention_hours,
            "job_type": self.job_type,
        }


class Config:
    """Main configuration manager."""
    
    def __init__(self):
        self.backup_jobs: List[BackupJobConfig] = []
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.metrics_enabled = os.getenv("METRICS_ENABLED", "true").lower() == "true"
        self.retry_max_attempts = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
        self.retry_initial_delay = float(os.getenv("RETRY_INITIAL_DELAY", "1.0"))
        self.gcs_timeout = int(os.getenv("GCS_TIMEOUT", "30"))
        self.project_id = os.getenv("GCP_PROJECT_ID", None)
        # Application identification - can be overridden via environment
        # variables. These provide defaults used by log entries when the
        # caller does not supply an explicit `app_name` or `app_type`.
        self.app_name = os.getenv("APP_NAME", "default_app")
        self.app_type = os.getenv("APP_TYPE", "gke_job")
    
    def load_from_env(self) -> None:
        """Load backup job configurations from environment variables.

        BACKUP_JOBS_CONFIG supports either:
        - A JSON string (e.g. '['{...}']')
        - A path to a Python file that defines a top-level BACKUP_JOBS list
          (e.g. /app/backup-jobs.py). Using a Python file allows comments.
        """
        config_value = os.getenv("BACKUP_JOBS_CONFIG", "")
        if not config_value:
            logger.warning("BACKUP_JOBS_CONFIG environment variable not set")
        else:
            # BACKUP_JOBS_CONFIG may be a JSON string (preferred) or a path to a file.
            jobs_data = None
            try:
                parsed = json.loads(config_value)
                if isinstance(parsed, list):
                    jobs_data = parsed
                    for job_data in jobs_data:
                        self.add_backup_job(**job_data)
                    logger.info(f"Loaded {len(self.backup_jobs)} backup jobs from environment")
                    return
            except json.JSONDecodeError:
                # Not a JSON string; treat as potential file path and fall back to file loading below
                pass
        try:
            with open('backup-jobs.json', 'r') as f:
                jobs_data = json.load(f)

            if isinstance(jobs_data, list):
                for job_data in jobs_data:
                    self.add_backup_job(**job_data)
            else:
                logger.error("Loaded configuration is not a list of job definitions")
                raise ValueError("Configuration must be a list of job dicts")

            logger.info(f"Loaded {len(self.backup_jobs)} backup jobs from environment")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load BACKUP_JOBS_CONFIG: {e}")
            raise
    
    def load_from_file(self, config_file: str) -> None:
        """Load backup job configurations from a file.

        Supports JSON (.json) files and Python (.py) files that define a
        top-level BACKUP_JOBS list.
        """
        try:
            if config_file.endswith('.py') and os.path.isfile(config_file):
                ns = runpy.run_path(config_file)
                jobs_data = ns.get('BACKUP_JOBS') or ns.get('BACKUP_JOBS_CONFIG') or ns.get('JOBS')
                if jobs_data is None:
                    raise ValueError(f"Python config file {config_file} must define BACKUP_JOBS list")

            else:
                with open(config_file, 'r') as f:
                    jobs_data = json.load(f)

            if isinstance(jobs_data, list):
                for job_data in jobs_data:
                    self.add_backup_job(**job_data)
            else:
                logger.error("Loaded configuration is not a list of job definitions")
                raise ValueError("Configuration must be a list of job dicts")

            logger.info(f"Loaded {len(self.backup_jobs)} backup jobs from {config_file}")
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_file}")
            raise
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse configuration file: {e}")
            raise
    
    def add_backup_job(
        self,
        job_name: str,
        instance_id: str,
        storage_type: str,
        bucket_name: str,
        prefix: str = "",
        timeout_seconds: int = 30,
        retention_hours: int = 24,
        job_type: str = "gcs_files",
    ) -> None:
        """Add a backup job configuration."""
        job = BackupJobConfig(
            job_name=job_name,
            instance_id=instance_id,
            storage_type=storage_type,
            bucket_name=bucket_name,
            prefix=prefix,
            timeout_seconds=timeout_seconds,
            retention_hours=retention_hours,
            job_type=job_type,
        )
        self.backup_jobs.append(job)
    
    def validate(self) -> bool:
        """Validate configuration."""
        if not self.backup_jobs:
            logger.error("No backup jobs configured")
            return False
        
        valid_job_types = ("gcs_files", "postgres_backup")
        for job in self.backup_jobs:
            if job.storage_type != "gcs":
                logger.error(
                    f"Invalid storage_type '{job.storage_type}' for job {job.job_name}. "
                    f"Only 'gcs' is supported"
                )
                return False

            if job.job_type not in valid_job_types:
                logger.error(
                    f"Invalid job_type '{job.job_type}' for job {job.job_name}. "
                    f"Supported types: {valid_job_types}"
                )
                return False

            if job.job_type == "postgres_backup" and not job.prefix:
                logger.error(f"prefix (instance folder) is required for postgres_backup job {job.job_name}")
                return False
            
            if not job.bucket_name:
                logger.error(f"bucket_name is required for job {job.job_name}")
                return False
            
            if job.retention_hours <= 0:
                logger.error(f"retention_hours must be positive for job {job.job_name}")
                return False
        
        logger.info(f"Configuration validated successfully ({len(self.backup_jobs)} jobs)")
        return True


# Global config instance
config = Config()
