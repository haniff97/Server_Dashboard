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

import services.tuya_local as tuya_local
import services.db as db
import services.aws_iot_publisher as aws_iot_publisher
import models.state as state
from controllers.server_controller import publish_local_mqtt


def persist_reading(dev_key, status, wh_delta):
    """Local telemetry is independent of optional cloud/MQTT publishers."""
    try:
        db.insert_energy(
            device_id=tuya_local.DEVICES[dev_key]['id'],
            device_name=status['device_name'], watts=status['watts'],
            wh_delta=wh_delta, voltage=status['voltage'],
            current_ma=status['current_ma'],
        )
    except Exception as exc:
        print(f"[db] insert error ({dev_key}): {exc}")
    else:
        try:
            db.aggregate_daily(tuya_local.DEVICES[dev_key]['id'])
        except Exception as exc:
            print(f"[db] daily summary error ({dev_key}): {exc}")
    for name, publish in (
        ('aws', lambda: aws_iot_publisher.publish(dev_key, status, wh_delta)),
        ('mqtt', lambda: publish_local_mqtt(dev_key, status['watts'])),
    ):
        try:
            publish()
        except Exception as exc:
            print(f"[{name}] publish error ({dev_key}): {exc}")


def plug_polling_loop():
    """Poll plugs; release the UI state lock before any database/network I/O."""
    last_poll_time = {key: None for key in tuya_local.DEVICES}
    while True:
        for dev_key in tuya_local.DEVICES:
            status = tuya_local.get_status(dev_key)
            now = time.monotonic()
            with state.plug_lock:
                state.plug_state[dev_key]['ok'] = bool(status)
                if status:
                    state.plug_state[dev_key]['status'] = status
                    state.plug_state[dev_key]['history'].append({
                        't': datetime.now().strftime('%H:%M:%S'), 'w': status['watts']})
            if status:
                previous = last_poll_time[dev_key]
                wh_delta = status['watts'] * (now-previous)/3600 if previous is not None else 0.0
                last_poll_time[dev_key] = now
                persist_reading(dev_key, status, wh_delta)
        time.sleep(state.PLUG_POLL_INTERVAL)


def refresh_device_energy(dev_key):
    """Publish today's cache before optional monthly summary maintenance."""
    device_id = tuya_local.DEVICES[dev_key]['id']
    summary = db.get_today_summary(device_id)
    with state.energy_cache_lock:
        state.energy_cache[dev_key].update(summary)
    month_kwh = db.get_current_month_usage(device_id)
    with state.energy_cache_lock:
        state.energy_cache[dev_key]['month_kwh'] = month_kwh
    db.aggregate_monthly(device_id)


def energy_cache_loop():
    while True:
        for dev_key in tuya_local.DEVICES:
            try:
                refresh_device_energy(dev_key)
            except Exception as exc:
                print(f"[energy_cache] {dev_key}: {exc}")
        time.sleep(10)


# ── Commands (async — call from UI event handlers) ─────────────────────────────
_state_log_tasks: set[asyncio.Task] = set()


async def _log_switch_change(dev_key: str, target_state: bool) -> None:
    try:
        await run.io_bound(
            db.insert_state_change,
            tuya_local.DEVICES[dev_key]["id"],
            tuya_local.DEVICES[dev_key]["name"],
            target_state,
        )
    except Exception as exc:
        # A logging failure must not turn a successful physical command into failure.
        print(f"[db] switch log failed ({dev_key}): {exc}")


async def toggle_plug(dev_key: str, target_state: bool) -> bool:
    """Return after device acknowledgement; persist the event independently."""
    ok = await run.io_bound(tuya_local.set_switch, dev_key, target_state)
    if ok:
        with state.plug_lock:
            cached = state.plug_state.get(dev_key, {}).get("status")
            if cached is not None:
                cached["switch"] = target_state
        task = asyncio.create_task(_log_switch_change(dev_key, target_state))
        _state_log_tasks.add(task)
        task.add_done_callback(_state_log_tasks.discard)
    return ok


async def exec_plug_cmd(fn, label: str) -> tuple[bool, str]:
    """Generic command executor. Returns (success, message)."""
    ok = await run.io_bound(fn)
    msg = f"✅ {label}" if ok else f"⚠ {label} failed"
    return ok, msg
