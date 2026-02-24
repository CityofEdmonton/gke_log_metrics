import os
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib import config as cfg_mod
from lib.backup_checker import BackupChecker
from lib.utils import metrics


def reset_metrics():
    metrics.counters.clear()
    metrics.gauges.clear()
    metrics.histograms.clear()


def test_app_name_defaults(monkeypatch, capsys):
    # Ensure APP_NAME not set
    monkeypatch.delenv('APP_NAME', raising=False)
    # reload config to pick up env change
    cfg = cfg_mod.config
    # force defaults
    cfg.app_name = os.getenv('APP_NAME', cfg.app_name)

    reset_metrics()

    checker = BackupChecker()
    checker.output_log_entry(
        job_name='job1',
        instance_id='inst1',
        status='success',
        storage_type='gcs',
        backup_info={'found': True, 'size_bytes': 1234, 'newest_name': 'file1'},
        message='Test run',
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data['app_name'] == cfg.app_name
    assert data['message'] == 'Test run'
    assert 'counter' in data and isinstance(data['counter'], int)
    assert data['info']['backup_info']['newest_name'] == 'file1'


def test_app_name_env_overrides(monkeypatch, capsys):
    monkeypatch.setenv('APP_NAME', 'my_app_env')
    cfg = cfg_mod.config
    # environment variable should take precedence when reading new config
    cfg.app_name = os.getenv('APP_NAME', cfg.app_name)

    reset_metrics()

    checker = BackupChecker()
    checker.output_log_entry(
        job_name='job2',
        instance_id='inst2',
        status='failed',
        storage_type='gcs',
        backup_info={'found': False, 'error_detail': 'no backup'},
        message='Failure run',
        extra_fields={'custom_field': 'custom_value'},
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data['app_name'] == 'my_app_env'
    assert data['message'] == 'Failure run'
    assert data['custom_field'] == 'custom_value'
    assert data['status'] == 'failed'
