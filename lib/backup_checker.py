"""
Backup verification module.
Checks GCS buckets for recent backups and outputs JSON logs.
Includes retry logic, timeout handling, and metrics collection.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
try:
    from google.cloud import storage
except Exception:
    storage = None
from google.api_core import exceptions as gcp_exceptions

from .config import config
from .utils import retry_with_backoff, metrics

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class BackupChecker:
    """Handles backup verification across different storage backends."""
    
    def __init__(self):
        self.gcs_client = None
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize storage clients."""
        if storage is None:
            logger.warning("google.cloud.storage module not available; GCS client not initialized")
            self.gcs_client = None
            return

        try:
            self.gcs_client = storage.Client(project=config.project_id)
            logger.info("GCS client initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize GCS client: {e}")
    
    @retry_with_backoff(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        exceptions=(
            gcp_exceptions.GoogleAPIError,
            gcp_exceptions.NotFound,
            gcp_exceptions.PermissionDenied,
            TimeoutError,
            IOError,
        )
    )
    def check_gcs_backup(
        self,
        bucket_name: str,
        prefix: str,
        retention_hours: int,
        timeout_seconds: int
    ) -> Dict[str, Any]:
        """
        Check for recent backups in a GCS bucket.
        
        Args:
            bucket_name: GCS bucket name
            prefix: Prefix/folder within the bucket
            retention_hours: How many hours back to check
            timeout_seconds: Timeout for the operation
        
        Returns:
            Dictionary with backup status and metadata
        """
        metrics.increment("gcs_backup_check_entries")

        if not self.gcs_client:
            raise RuntimeError("GCS client not initialized")
        
        start_time = time.time()
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
        
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            
            # List blobs with timeout consideration
            blobs = list(
                self.gcs_client.list_blobs(
                    bucket,
                    prefix=prefix,
                    timeout=timeout_seconds
                )
            )
            
            # Find recent backups
            recent_blobs = [b for b in blobs if b.updated > cutoff_time]
            
            if not recent_blobs:
                elapsed = time.time() - start_time
                metrics.record_histogram("backup_check_duration_seconds", elapsed)
                # No recent backup found -> mark as failed
                return {
                    "found": False,
                    "status": "failed",
                    "size_bytes": 0,
                    "file_count": len(blobs),
                    "recent_count": 0,
                    "newest_updated": None,
                    "error_detail": "No recent backup found",
                }
            
            newest_blob = max(recent_blobs, key=lambda b: b.updated)
            elapsed = time.time() - start_time
            metrics.record_histogram("backup_check_duration_seconds", elapsed)
            
            size_bytes = newest_blob.size if hasattr(newest_blob, 'size') else 0
            # If a backup was found but its size is zero, consider it a failure
            if size_bytes <= 0:
                logger.warning(
                    "Backup found but size is zero: %s/%s", bucket_name, newest_blob.name
                )
                data = {
                    "found": True,
                    "status": "failed",
                    "size_bytes": size_bytes,
                    "file_count": len(blobs),
                    "recent_count": len(recent_blobs),
                    "newest_updated": newest_blob.updated.isoformat(),
                    "newest_name": newest_blob.name,
                    "error_detail": "Backup has zero bytes",
                }
                logger.info(data)
                return data
            
            # Successful backup
            data = {
                "found": True,
                "status": "success",
                "size_bytes": size_bytes,
                "file_count": len(blobs),
                "recent_count": len(recent_blobs),
                "newest_updated": newest_blob.updated.isoformat(),
                "newest_name": newest_blob.name,
            }
            logger.info(data)
            return data
        
        except gcp_exceptions.NotFound:
            logger.error(f"GCS bucket not found: {bucket_name}")
            metrics.increment("backup_checks_failed")
            raise
        except gcp_exceptions.PermissionDenied:
            logger.error(f"Permission denied accessing GCS bucket: {bucket_name}")
            metrics.increment("backup_checks_failed")
            raise
        except TimeoutError as e:
            logger.error(f"Timeout checking GCS bucket {bucket_name}: {e}")
            metrics.increment("backup_checks_timeout")
            raise
        except Exception as e:
            logger.error(f"Error checking GCS bucket {bucket_name}: {e}")
            metrics.increment("backup_checks_failed")
            raise

    @retry_with_backoff(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        exceptions=(
            gcp_exceptions.GoogleAPIError,
            gcp_exceptions.NotFound,
            gcp_exceptions.PermissionDenied,
            TimeoutError,
            IOError,
        )
    )
    def check_postgres_backup(
        self,
        bucket_name: str,
        prefix: str,
        retention_hours: int,
        timeout_seconds: int
    ) -> Dict[str, Any]:
        """
        Check Postgres backups by verifying the latest daily/weekly/monthly
        folders under the given instance prefix (e.g. 'psdb01').

        Returns the same schema as `check_gcs_backup`. If any of the three
        checks (daily, weekly, monthly) fails, the job is considered failed
        and the `error_detail` explains which check(s) failed.
        """
        metrics.increment("postgres_backup_check_entries")

        if not self.gcs_client:
            raise RuntimeError("GCS client not initialized")

        # Ensure prefix ends with '/'
        if prefix and not prefix.endswith('/'):
            prefix = prefix.rstrip('/') + '/'

        start_time = time.time()
        now = datetime.now(timezone.utc)

        try:
            bucket = self.gcs_client.bucket(bucket_name)

            # List blobs under the instance prefix
            blobs = list(
                self.gcs_client.list_blobs(
                    bucket,
                    prefix=prefix,
                    timeout=timeout_seconds,
                )
            )

            # Group blobs by top-level folder immediately under prefix
            folders = {}
            for b in blobs:
                if not b.name.startswith(prefix):
                    continue
                remainder = b.name[len(prefix):]
                if not remainder:
                    continue
                folder = remainder.split('/', 1)[0]
                folders.setdefault(folder, []).append(b)

            # Detect folders of types daily/weekly/monthly and parse dates
            types = {"daily": [], "weekly": [], "monthly": []}
            for folder_name in folders.keys():
                if len(folder_name) < 10:
                    continue
                date_str = folder_name[:10]
                try:
                    folder_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                lname = folder_name.lower()
                if "daily" in lname:
                    types["daily"].append((folder_date, folder_name))
                elif "weekly" in lname:
                    types["weekly"].append((folder_date, folder_name))
                elif "monthly" in lname:
                    types["monthly"].append((folder_date, folder_name))

            # Evaluate newest folder for each type
            results = {}
            failures = []
            total_size = 0
            total_files = 0

            # thresholds: daily <=24 hours, weekly <=7 days, monthly <=30 days
            for t in ["daily", "weekly", "monthly"]:
                entries = types.get(t, [])

                # If evaluating daily, allow fallback to the newest available
                # backup among daily/weekly/monthly (weekly/monthly may run
                # on days when daily is skipped). For weekly/monthly checks
                # we only consider their own entries.
                if t == "daily":
                    # build candidate list from all types
                    candidates = []
                    for tt in ["daily", "weekly", "monthly"]:
                        candidates.extend(types.get(tt, []))

                    if not candidates:
                        results[t] = {"found": False, "passed": False}
                        failures.append(f"{t} missing")
                        continue

                    newest_date, newest_folder = max(candidates, key=lambda x: x[0])
                else:
                    if not entries:
                        results[t] = {"found": False, "passed": False}
                        failures.append(f"{t} missing")
                        continue

                    newest_date, newest_folder = max(entries, key=lambda x: x[0])

                blobs_in_folder = folders.get(newest_folder, [])
                folder_size = sum((getattr(b, "size", 0) or 0) for b in blobs_in_folder)
                file_count = len(blobs_in_folder)

                # compute elapsed since folder date
                folder_dt = datetime.combine(newest_date, datetime.min.time(), timezone.utc)
                hours_since = (now - folder_dt).total_seconds() / 3600.0
                days_since = (now.date() - newest_date).days

                passed = True
                if file_count == 0 or folder_size <= 0:
                    passed = False
                else:
                    if t == "daily":
                        # For daily, accept a backup from daily/weekly/monthly
                        # as long as its date is within the daily threshold.
                        passed = passed and (hours_since <= 24)
                    elif t == "weekly":
                        passed = passed and (days_since <= 7)
                    elif t == "monthly":
                        passed = passed and (days_since <= 30)

                results[t] = {
                    "found": True,
                    "folder_name": newest_folder,
                    "folder_date": newest_date.isoformat(),
                    "size_bytes": folder_size,
                    "file_count": file_count,
                    "hours_since": round(hours_since, 2),
                    "days_since": days_since,
                    "passed": passed,
                }

                total_size += folder_size
                total_files += file_count

                if not passed:
                    failures.append(f"{t} fails")

            elapsed = time.time() - start_time
            metrics.record_histogram("backup_check_duration_seconds", elapsed)

            if failures:
                error_detail = ", ".join(failures)
                return {
                    "found": False,
                    "status": "failed",
                    "size_bytes": total_size,
                    "file_count": total_files,
                    "recent_count": 0,
                    "newest_updated": None,
                    "error_detail": error_detail,
                    "per_type": results,
                }

            # All three types passed
            # choose newest blob for timestamp across all types
            newest_blob = None
            for info in results.values():
                if not info.get("found"):
                    continue
                folder_name = info.get("folder_name")
                for b in folders.get(folder_name, []):
                    if newest_blob is None or b.updated > newest_blob.updated:
                        newest_blob = b

            newest_updated = newest_blob.updated.isoformat() if newest_blob else None
            data = {
                "found": True,
                "status": "success",
                "size_bytes": total_size,
                "file_count": total_files,
                "recent_count": 3,
                "newest_updated": newest_updated,
                "newest_name": newest_blob.name if newest_blob else None,
                "per_type": results,
            }
            logger.info("Postgres backup OK: %s/%s - %d bytes", bucket_name, newest_blob.name if newest_blob else "", total_size)
            return data

        except gcp_exceptions.NotFound:
            logger.error(f"GCS bucket not found: {bucket_name}")
            metrics.increment("postgres_backup_checks_failed")
            raise
        except gcp_exceptions.PermissionDenied:
            logger.error(f"Permission denied accessing GCS bucket: {bucket_name}")
            metrics.increment("postgres_backup_checks_failed")
            raise
        except TimeoutError as e:
            logger.error(f"Timeout checking Postgres backups in {bucket_name}: {e}")
            metrics.increment("postgres_backup_checks_timeout")
            raise
        except Exception as e:
            logger.error(f"Error checking Postgres backups in {bucket_name}: {e}")
            metrics.increment("postgres_backup_checks_failed")
            raise

    def output_log_entry(
        self,
        job_name: str,
        instance_id: str,
        status: str,
        storage_type: str,
        backup_info: Optional[Dict[str, Any]] = None,
        error_detail: str = "",
        app_name: Optional[str] = None,
        app_type: Optional[str] = None,
    ) -> None:
        """
        Output a standardized JSON log entry.
        
        Args:
            job_name: Name of the backup job
            instance_id: Instance identifier
            status: "success" or "failed"
            storage_type: Type of storage (gcs)
            backup_info: Additional backup metadata
            error_detail: Error message if applicable
        """
        size_bytes = 0
        if backup_info and backup_info.get("found"):
            size_bytes = backup_info.get("size_bytes", 0)
        
        # Use provided app_name/app_type or fall back to configured defaults
        entry_app_name = app_name or config.app_name
        entry_app_type = app_type or config.app_type

        log_entry = {
            "event_type": "backup_verification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app_name": entry_app_name,
            "app_type": entry_app_type,
            "job_name": job_name,
            "instance_id": instance_id,
            "status": status,
            "size_bytes": size_bytes,
            "storage_type": storage_type,
            "error_detail": error_detail,
        }
        
        if backup_info:
            log_entry["backup_info"] = {
                k: v for k, v in backup_info.items()
                if k not in ["found", "size_bytes"]
            }
        
        print(json.dumps(log_entry))
        metrics.increment("log_entries_output")


def check_backups() -> None:
    """
    Main function to check all configured backup jobs.
    Loads configuration, validates it, and checks each backup job.
    """
    # Load configuration
    config.load_from_env()
    
    # Validate configuration
    if not config.validate():
        logger.error("Configuration validation failed")
        return
    
    # Initialize checker
    checker = BackupChecker()
    metrics.increment("backup_checks_started")
    
    # Check each backup job
    for job in config.backup_jobs:
        logger.info(f"Checking backup job: {job.job_name} ({job.instance_id})")
        
        try:
            if getattr(job, "job_type", "gcs_files") == "postgres_backup":
                backup_info = checker.check_postgres_backup(
                    bucket_name=job.bucket_name,
                    prefix=job.prefix,
                    retention_hours=job.retention_hours,
                    timeout_seconds=job.timeout_seconds,
                )
            else:
                backup_info = checker.check_gcs_backup(
                    bucket_name=job.bucket_name,
                    prefix=job.prefix,
                    retention_hours=job.retention_hours,
                    timeout_seconds=job.timeout_seconds,
                )

            status = backup_info.get("status")
            if status == "success":
                # Successful backup
                metrics.increment("backups_check_success")
                checker.output_log_entry(
                    job_name=job.job_name,
                    instance_id=job.instance_id,
                    status="success",
                    storage_type=job.storage_type,
                    backup_info=backup_info,
                )
                logger.info(
                    f"Backup found: {job.job_name}/{job.instance_id} "
                    f"({backup_info.get('size_bytes', 0)} bytes)"
                )
            else:
                # Failed: either not found or zero-size backup or per-type failures
                metrics.increment("backups_check_failure")
                error = backup_info.get("error_detail", "No recent backup found")
                checker.output_log_entry(
                    job_name=job.job_name,
                    instance_id=job.instance_id,
                    status="failed",
                    storage_type=job.storage_type,
                    backup_info=backup_info,
                    error_detail=error,
                )
                logger.warning(f"No valid backup: {job.job_name}/{job.instance_id} - {error}")
        
        except Exception as e:
            logger.error(
                f"Failed to check backup {job.job_name}/{job.instance_id}: {e}",
                exc_info=True
            )
            checker.output_log_entry(
                job_name=job.job_name,
                instance_id=job.instance_id,
                status="failed",
                storage_type=job.storage_type,
                error_detail=str(e),
            )
            metrics.increment("backup_checks_failed")
    
    # Output metrics if enabled
    if config.metrics_enabled:
        logger.info("Metrics:\n" + metrics.to_prometheus())
    
    metrics.increment("backup_checks_completed")


if __name__ == "__main__":
    check_backups()