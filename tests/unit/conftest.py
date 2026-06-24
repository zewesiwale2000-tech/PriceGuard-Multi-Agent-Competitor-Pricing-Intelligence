# conftest.py — unit test configuration for PriceGuard
#
# Prevents pytest from importing app/__init__.py (which chains into agent.py
# and calls google.auth.default() + google_cloud_logging.Client() at module
# level, hanging indefinitely without live GCP credentials).
#
# Each test file that needs app sub-modules loads them via importlib directly.

collect_ignore_glob = ["../../app/*.py", "../../app/**/*.py"]
