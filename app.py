#!/usr/bin/env python3
"""
app.py — Entry Point
=====================
Homelab Dashboard (MVC)

Structure:
  models/           — shared state (state.py)
  controllers/      — polling loops, commands, AI
  views/            — NiceGUI UI (server, energy, plugs, network, layout)
  services/         — tuya_local, db, aws_iot_publisher, cloud_db (unchanged)

Usage:
  python3 app.py
  (or via PM2: ecosystem.config.js)
"""
import os
import sys
import threading
import asyncio

from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

env_path = "/mnt/nvme/Projects/dashboard/.env"
load_dotenv(env_path)

from nicegui import ui, app

# ── Controllers (import after env load) ───────────────────────────────────────
from controllers.server_controller import update_metrics, update_ai_insights
from controllers.plug_controller   import plug_polling_loop, energy_cache_loop
from controllers.network_controller import update_network_state

# ── Views / Routes ────────────────────────────────────────────────────────────
import views.layout  # registers @ui.page('/') and @ui.page('/cloud')  # noqa: F401

# ── Startup — launch background threads & async loops ─────────────────────────
@app.on_startup
async def on_startup():
    # Daemon threads — hardware polling
    threading.Thread(target=plug_polling_loop, daemon=True, name="PlugPoller").start()
    threading.Thread(target=energy_cache_loop, daemon=True, name="EnergyCache").start()

    # Async loops — metrics, AI, network
    asyncio.create_task(update_metrics())
    asyncio.create_task(update_ai_insights())
    asyncio.create_task(update_network_state())


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ui.run(
        host="0.0.0.0",
        port=8080,
        title="Homelab Dashboard",
        favicon="🖥️",
        dark=True,
        reload=False,
    )
