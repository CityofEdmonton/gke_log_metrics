from setuptools import setup, find_packages

setup(
    name="gke_log_metrics",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.8",
    description="GKE-friendly JSON logging and optional Prometheus metrics",
)
