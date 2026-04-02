"""Web Dashboard for Memoria — REST API + interactive UI.

Zero-dependency dashboard that ships with the Python package.
Serves a REST API bridging to Memoria + a static SPA frontend.

Usage:
    from memoria import Memoria
    m = Memoria()
    m.start_dashboard(port=8080)
    # Visit http://localhost:8080
    m.stop_dashboard()
"""

from memoria.dashboard.api import DashboardAPI
from memoria.dashboard.server import DashboardServer

__all__ = ["DashboardServer", "DashboardAPI"]
