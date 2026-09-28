#!/usr/bin/env python3
"""
app.py — Main Entry Point
=========================
Homelab Dashboard (MVC Architecture)

Structure:
  models/           — Single source of truth for global state (state.py)
  controllers/      — Polling loops, hardware metrics, plug control, AI & network monitors
  views/            — NiceGUI UI views (server, energy, plugs, network, layout, styles)
  services/         — External adapters: db, tuya_local, aws_iot_publisher, cloud_db

Usage:
  python3 app.py
  (or via PM2: ecosystem.config.js)
"""
import os
import sys
import threading
import asyncio

from dotenv import load_dotenv

# ── Load environment ─────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

env_paths = [
    "/mnt/nvme/Projects/dashboard/.env",
    os.path.join(_project_root, ".env"),
]
for p in env_paths:
    if os.path.exists(p):
        load_dotenv(p)
        break
else:
    load_dotenv()

from nicegui import ui, app

# ── Controllers (imported after env loaded) ──────────────────────────────────
from controllers.server_controller import update_metrics, update_ai_insights
from controllers.plug_controller   import plug_polling_loop, energy_cache_loop
from controllers.network_controller import update_network_state

# ── Views / Routes ───────────────────────────────────────────────────────────
import views.layout  # registers @ui.page('/') and @ui.page('/cloud')  # noqa: F401

# ── Startup — launch background threads & async loops ────────────────────────
@app.on_startup
async def on_startup():
    # Daemon threads for hardware polling
    threading.Thread(target=plug_polling_loop, daemon=True, name="PlugPoller").start()
    threading.Thread(target=energy_cache_loop, daemon=True, name="EnergyCache").start()

    # Async loops for metrics, AI insights, and network probing
    asyncio.create_task(update_metrics())
    asyncio.create_task(update_ai_insights())
    asyncio.create_task(update_network_state())


# ── Run ──────────────────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    port = int(os.getenv("PORT", 3000))
    ui.run(
        host="0.0.0.0",
        port=port,
        title="Homelab Dashboard",
        favicon="🖥️",
        dark=True,
        reload=False,
    )
