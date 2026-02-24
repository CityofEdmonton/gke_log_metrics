import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath('.'))

from gke_log_metrics import Config, get_logger, ValidationError


def test_json_metric_prints_when_enabled(capsys, monkeypatch):
    """Verify json_metric prints JSON to stdout when METRICS_ENABLED."""
    monkeypatch.delenv('APP_NAME', raising=False)
    monkeypatch.delenv('METRICS_ENABLED', raising=False)
    cfg = Config()
    cfg.METRICS_ENABLED = True
    logger = get_logger(cfg)

    logger.json_metric('test_metric', 1.0, info={'a': 1}, extra={'x': 'y'})
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert obj['metric_name'] == 'test_metric'
    assert obj['metric_value'] == 1.0
    assert obj['info']['a'] == 1
    assert obj['x'] == 'y'
    assert obj['app_name'] == 'default_app'
    assert obj['event_type'] == 'metric'


def test_json_metric_not_prints_when_disabled(capsys, monkeypatch):
    """Verify json_metric does not print when METRICS_ENABLED is False."""
    monkeypatch.delenv('METRICS_ENABLED', raising=False)
    cfg = Config()
    cfg.METRICS_ENABLED = False
    logger = get_logger(cfg)

    logger.json_metric('test_metric', 1.0, info={'a': 1})
    out = capsys.readouterr().out.strip()

    assert out == ''


def test_app_name_defaulting(monkeypatch, capsys):
    """Verify app_name defaults from config when not provided."""
    monkeypatch.delenv('APP_NAME', raising=False)
    cfg = Config()
    logger = get_logger(cfg)

    logger.json_metric('msg1', 1.0, info={})
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert obj['app_name'] == 'default_app'


def test_app_name_env_override(monkeypatch, capsys):
    """Verify APP_NAME from env overrides config."""
    monkeypatch.setenv('APP_NAME', 'my_custom_app')
    cfg = Config()
    logger = get_logger(cfg)

    logger.json_metric('msg1', 1.0, info={})
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert obj['app_name'] == 'my_custom_app'


def test_metric_updates_prometheus_and_json(capsys, monkeypatch):
    """Verify metric() updates both Prometheus metrics and emits JSON."""
    monkeypatch.delenv('PROMETHEUS_ENABLED', raising=False)
    monkeypatch.delenv('METRICS_ENABLED', raising=False)
    cfg = Config()
    cfg.PROMETHEUS_ENABLED = True
    cfg.METRICS_ENABLED = True
    logger = get_logger(cfg)

    logger.metric('backup_checks', 1, labels={'job': 'j1'}, message='Check done', info={'size': 100})
    
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert obj['message'] == 'Check done'
    assert obj['metric_name'] == 'backup_checks'
    assert obj['metric_value'] == 1
    assert obj['labels'] == {'job': 'j1'}
    assert obj['info']['size'] == 100

    # verify prometheus metric was recorded
    prom = logger.metrics_to_prometheus()
    assert 'backup_checks' in prom


def test_config_loads_from_file(tmp_path, monkeypatch):
    """Verify config loads from JSON file."""
    cfg_file = tmp_path / ".configs"
    cfg_file.write_text(json.dumps({"APP_NAME": "from_file", "LOG_LEVEL": "DEBUG"}))
    
    monkeypatch.delenv('APP_NAME', raising=False)
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    cfg = Config(config_file=str(cfg_file))
    
    assert cfg.APP_NAME == 'from_file'
    assert cfg.LOG_LEVEL == 'DEBUG'


def test_config_env_overrides_file(tmp_path, monkeypatch):
    """Verify environment variables override file config."""
    cfg_file = tmp_path / ".configs"
    cfg_file.write_text(json.dumps({"APP_NAME": "from_file"}))
    
    monkeypatch.setenv('APP_NAME', 'from_env')
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    cfg = Config(config_file=str(cfg_file))
    
    assert cfg.APP_NAME == 'from_env'


def test_metrics_counter_increments(capsys, monkeypatch):
    """Verify metric_value is exactly the provided value (no internal increment)."""
    monkeypatch.delenv('METRICS_ENABLED', raising=False)
    cfg = Config()
    cfg.METRICS_ENABLED = True
    logger = get_logger(cfg)

    logger.json_metric('m', 1.0)
    obj1 = json.loads(capsys.readouterr().out.strip())

    logger.json_metric('m', 2.0)
    obj2 = json.loads(capsys.readouterr().out.strip())

    logger.json_metric('m', 3.5)
    obj3 = json.loads(capsys.readouterr().out.strip())

    # metric_value should match the provided value exactly
    assert obj1['metric_value'] == 1.0
    assert obj2['metric_value'] == 2.0
    assert obj3['metric_value'] == 3.5
