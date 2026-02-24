"""
Shared utilities for job checker modules.
"""
import time
import logging
from functools import wraps
from typing import Callable, Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
) -> Callable[[F], F]:
    """
    Decorator for retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retries
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for exponential backoff
        max_delay: Maximum delay between retries
        exceptions: Tuple of exceptions to catch and retry on
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}"
                        )
            
            raise last_exception
        return wrapper
    return decorator


class Metrics:
    """Simple metrics collector for monitoring."""
    
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
    
    def increment(self, key: str, value: int = 1) -> None:
        """Increment a counter metric."""
        if key not in self.counters:
            self.counters[key] = 0
        self.counters[key] += value
    
    def set_gauge(self, key: str, value: float) -> None:
        """Set a gauge metric."""
        self.gauges[key] = value
    
    def record_histogram(self, key: str, value: float) -> None:
        """Record a histogram value."""
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)
    
    def to_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Counters
        for key, value in self.counters.items():
            lines.append(f"# HELP {key} Counter metric")
            lines.append(f"# TYPE {key} counter")
            lines.append(f"{key} {value}")
        
        # Gauges
        for key, value in self.gauges.items():
            lines.append(f"# HELP {key} Gauge metric")
            lines.append(f"# TYPE {key} gauge")
            lines.append(f"{key} {value}")
        
        # Histograms (simplified)
        for key, values in self.histograms.items():
            if values:
                lines.append(f"# HELP {key} Histogram metric")
                lines.append(f"# TYPE {key} histogram")
                lines.append(f"{key}_sum {sum(values)}")
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_avg {sum(values) / len(values):.2f}")
        
        return "\n".join(lines)


# Global metrics instance
metrics = Metrics()
