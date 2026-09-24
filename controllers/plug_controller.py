"""
controllers/plug_controller.py
================================
Smart plug polling, toggle commands, energy cache loop.
"""
import os
import sys
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional

from nicegui import run

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tuya_local
import db
import aws_iot_publisher
import models.state as state
from controllers.server_controller import publish_local_mqtt


# ── Polling thread (runs in daemon thread) ────────────────────────────────────
def plug_polling_loop():
    """Poll all smart plugs via tinytuya and persist to DB."""
    last_poll_time: Dict[str, Optional[float]] = {
        "plug": None, "server": None, "extension": None
    }

    while True:
        for dev_key in ("plug", "server", "extension"):
            status = tuya_local.get_status(dev_key)
            now = time.time()

            with state.plug_lock:
                if status:
                    state.plug_state[dev_key]["status"] = status
                    state.plug_state[dev_key]["ok"]     = True
                    state.plug_state[dev_key]["history"].append({
                        "t": datetime.now().strftime("%H:%M:%S"),
                        "w": status["watts"],
                    })

                    wh_delta = 0.0
                    if last_poll_time[dev_key]:
                        elapsed_h = (now - last_poll_time[dev_key]) / 3600
                        wh_delta  = status["watts"] * elapsed_h

                    last_poll_time[dev_key] = now

                    try:
                        aws_iot_publisher.publish(dev_key, status, wh_delta)
                        publish_local_mqtt(dev_key, status["watts"])
                        db.insert_energy(
                            device_id=tuya_local.DEVICES[dev_key]["id"],
                            device_name=status["device_name"],
                            watts=status["watts"],
                            wh_delta=wh_delta,
                            voltage=status["voltage"],
                            current_ma=status["current_ma"],
                        )
                        db.aggregate_daily(tuya_local.DEVICES[dev_key]["id"])
                    except Exception as e:
                        print(f"[db] insert error ({dev_key}): {e}")
                else:
                    state.plug_state[dev_key]["ok"] = False

        time.sleep(state.PLUG_POLL_INTERVAL)


# ── Energy cache loop (daemon thread) ─────────────────────────────────────────
def energy_cache_loop():
    """Poll DB summaries every 10s and cache for UI timers."""
    while True:
        for dev_key in ("plug", "server", "extension"):
            try:
                summary = db.get_today_summary(tuya_local.DEVICES[dev_key]["id"])
                db.aggregate_monthly(tuya_local.DEVICES[dev_key]["id"])
                monthly = db.get_monthly_history(tuya_local.DEVICES[dev_key]["id"], months=1)
                month_kwh = float(monthly[0]["total_kwh"]) if monthly else summary["total_kwh"]
                with state.energy_cache_lock:
                    state.energy_cache[dev_key] = {**summary, "month_kwh": month_kwh}
            except Exception as e:
                print(f"[energy_cache] {dev_key}: {e}")
        time.sleep(10)


# ── Commands (async — call from UI event handlers) ─────────────────────────────
async def toggle_plug(dev_key: str, target_state: bool) -> bool:
    """Turn plug on/off and log to DB. Returns True on success."""
    ok = await run.io_bound(tuya_local.set_switch, dev_key, target_state)
    if ok:
        await run.io_bound(
            db.insert_state_change,
            tuya_local.DEVICES[dev_key]["id"],
            tuya_local.DEVICES[dev_key]["name"],
            target_state,
        )
    return ok


async def exec_plug_cmd(fn, label: str) -> tuple[bool, str]:
    """Generic command executor. Returns (success, message)."""
    ok = await run.io_bound(fn)
    msg = f"✅ {label}" if ok else f"⚠ {label} failed"
    return ok, msg
