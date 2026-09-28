#!/usr/bin/env python3
"""
frontend/dashboard.py
=====================
Backwards-compatible wrapper that launches the MVC application via app.py.
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import and execute the MVC main app
import app

if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import ui
    port = int(os.getenv("PORT", 3000))
    ui.run(
        host="0.0.0.0",
        port=port,
        title="Homelab Dashboard",
        favicon="🖥️",
        dark=True,
        reload=False,
    )
