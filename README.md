# gke_log_metrics

Minimal, production-ready library for emitting structured JSON metrics/logs (designed for GKE, compatible with Grafana log-based metrics) and optional Prometheus-format metric export.

**Key features:**
- JSON-based structured logging with fixed and extensible fields
- JSON metrics that accept `name` and `value` (no internal auto-increment)
- Optional Prometheus-format metrics export
- Configuration precedence: env vars > `.configs` JSON file > defaults
- Minimal dependencies (stdlib only)
- Thread-safe metric aggregation

## Installation

```bash
pip install gke_log_metrics
```

Or for development:
```bash
cd /path/to/gke_log_metrics
pip install -e .
```

## Quick Start

```python
from gke_log_metrics import Config, get_logger

# Load config (from .configs file and env var overrides)
cfg = Config()

# Get logger instance
logger = get_logger(cfg)

# Normal application log
logger.log("Application started", info={"phase": "startup"})

# Emit a log-based metric (JSON to stdout if METRICS_ENABLED)
logger.json_metric("backup_completed", 1, info={"job": "j1", "status": "success"})

# Unified metric API (updates Prometheus + emits JSON if enabled)
logger.metric("backup_checks_total", 1, labels={"job": "j1"})

# Export Prometheus metrics
print(logger.metrics_to_prometheus())
```

## Configuration

Configuration is loaded in this order (later overrides earlier):
1. Library defaults
2. `.configs` file (environment variables format, or custom path via `CONFIG_FILE` env var)
3. OS environment variables

### Environment Variables

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `APP_NAME` | string | `"default_app"` | Application name in log entries |
| `APP_TYPE` | string | `"default_type"` | Application type (e.g., `gke_job`, `gke_api`, `shinyproxy_app`) |
| `OWNER` | string | `"default_owner"` | Owner or team name in log entries |
| `METRICS_ENABLED` | bool | `true` | Enable JSON metrics to stdout (ignores `LOG_LEVEL`) |
| `PROMETHEUS_ENABLED` | bool | `false` | Enable Prometheus-format metrics collection |
| `LOG_LEVEL` | string | `"INFO"` | Python logging level (only affects `logger.log()`, not metrics) |
| `CONFIG_FILE` | string | `".configs"` | Path to environment variables format config file |

### Example `.configs` file

```
APP_NAME=my_backup_app
APP_TYPE=gke_job
OWNER=data_team
METRICS_ENABLED=true
PROMETHEUS_ENABLED=true
LOG_LEVEL=DEBUG
```

## API Reference

### `Config(config_file=None)`
Loads configuration from file and environment. Validates on instantiation.

```python
cfg = Config(config_file='.configs')
# or
cfg = Config()  # uses default '.configs' or CONFIG_FILE env
```

### `get_logger(cfg)`
Factory function; creates and returns a validated `Logger` instance.

```python
from gke_log_metrics import get_logger, ValidationError

try:
    logger = get_logger(cfg)
except ValidationError as e:
    print(f"Config error: {e}")
    sys.exit(1)
```

### `Logger.log(...)`
Normal application logging (respects `LOG_LEVEL`).

```python
logger.log(
    message: str,
    info: Optional[Dict[str, Any]] = None,
    level: str = "info",  # "debug", "info", "warning", "error"
    app_name: Optional[str] = None,
    app_type: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None
)
```

**Example:**
```python
logger.log("Backup started", info={"job_id": "12345"}, level="info")
```

### `Logger.json_metric(...)`
Emit a JSON metric to stdout (always prints if `METRICS_ENABLED=true`, regardless of `LOG_LEVEL`).

```python
logger.json_metric(
        name: str,
        value: float = 1.0,
        info: Optional[Dict[str, Any]] = None,
        app_name: Optional[str] = None,
        app_type: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
)
```

**Emitted JSON schema:**
```json
{
    "info": { "custom": "object" },
    "app_name": "my_app",
    "owner": "data_team",
    "app_type": "gke_job",
    "metric_name": "backup_completed",
    "metric_value": 1.0,
    "event_type": "metric",
    "timestamp": "2026-02-24T19:12:52.123456+00:00",
    "custom_field": "value"
}
```

**Example:**
```python
logger.json_metric(
        "backup_verified",
        1.0,
        info={"job": "daily", "status": "success", "size_bytes": 1048576},
        extra={"duration_seconds": 45.3}
)
```

### `Logger.prometheus_metric(...)`
Update internal Prometheus-style metrics (counters, gauges, histograms).

```python
logger.prometheus_metric(
    name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None
)
```

**Example:**
```python
logger.prometheus_metric("backup_checks_total", 1, labels={"job": "daily", "status": "success"})
```

### `Logger.metric(...)`
Unified API: updates Prometheus metrics AND emits JSON metric (both if enabled).

```python
logger.metric(
    name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None,
    message: Optional[str] = None,
    info: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    app_name: Optional[str] = None,
    app_type: Optional[str] = None
)
```

**Example:**
```python
logger.metric(
    "backup_checks_total",
    1,
    labels={"job": "daily", "status": "success"},
    message="Backup check succeeded",
    info={"duration": 45.3}
)
```

### `Logger.metrics_to_prometheus()`
Export accumulated Prometheus metrics in text format.

```python
prom_text = logger.metrics_to_prometheus()
print(prom_text)
```

## Examples

See `examples/basic_usage.py` for a complete working example:

```bash
cd /path/to/gke_log_metrics
PYTHONPATH=. python3 examples/basic_usage.py
```

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

## Use Cases

### GKE Log-Based Metrics
Use `json_metric()` or `metric()` to emit structured logs that GKE/Stackdriver can parse as log-based metrics, then visualize in Grafana.

**Example workflow:**
1. Your app calls `logger.json_metric("backup_status", info={"job":"daily", "status":"success"})`
2. JSON is printed to stdout
3. GKE captures stdout as logs
4. Stackdriver creates a log-based metric from the JSON
5. Grafana queries and visualizes the metric

### Prometheus Scraping
Set `PROMETHEUS_ENABLED=true` and expose metrics via your app's HTTP endpoint (caller responsible).

**Example (Flask):**
```python
from flask import Flask
from gke_log_metrics import Config, get_logger

app = Flask(__name__)
cfg = Config()
logger = get_logger(cfg)

@app.route('/metrics')
def metrics():
    return logger.metrics_to_prometheus(), 200, {'Content-Type': 'text/plain'}
```

## Behavior Details

### Metrics-Enabled Behavior
When `METRICS_ENABLED=true`:
- `json_metric()` prints JSON to stdout **always**, ignoring `LOG_LEVEL`
- `metric()` emits JSON to stdout (if `METRICS_ENABLED`) and updates Prometheus (if enabled)
- `json_metric()` accepts `name` and `value`; there is no internal auto-incrementing `counter` field

### Disabled Metrics
When `METRICS_ENABLED=false`:
- `json_metric()` does nothing (silent)
- `metric()` only updates Prometheus (if enabled), no JSON output

### App Name / Type Defaulting
- `app_name` defaults to `config.APP_NAME` when not provided
- `app_type` defaults to `config.APP_TYPE` when not provided
- Both can be overridden per call

Notes:
- When you call `json_metric(...)` or `metric(...)` and do not provide `app_name`/`app_type`, the library will use `Config.APP_NAME` and `Config.APP_TYPE` respectively.
- `metric(...)` will pass these effective values to the JSON metric output so the emitted log always contains `app_name` and `app_type`.

## Development

Clone and install in editable mode:
```bash
git clone https://github.com/CityofEdmonton/gke_log_metrics.git
cd gke_log_metrics
pip install -e .
pytest tests/
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Support

For issues, questions, or contributions, contact the maintainers.
