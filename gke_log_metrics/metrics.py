"""Simple in-process metrics collector and Prometheus exporter."""
from typing import Dict, List


class Metrics:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + int(value)

    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = float(value)

    def record_histogram(self, name: str, value: float) -> None:
        self.histograms.setdefault(name, []).append(float(value))

    def to_prometheus(self) -> str:
        lines: List[str] = []
        for k, v in self.counters.items():
            lines.append(f"# HELP {k} Counter metric")
            lines.append(f"# TYPE {k} counter")
            lines.append(f"{k} {v}")

        for k, v in self.gauges.items():
            lines.append(f"# HELP {k} Gauge metric")
            lines.append(f"# TYPE {k} gauge")
            lines.append(f"{k} {v}")

        for k, vals in self.histograms.items():
            if vals:
                lines.append(f"# HELP {k} Histogram metric")
                lines.append(f"# TYPE {k} histogram")
                lines.append(f"{k}_count {len(vals)}")
                lines.append(f"{k}_sum {sum(vals)}")
        return "\n".join(lines)


# global instance
metrics = Metrics()
