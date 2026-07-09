#!/usr/bin/env python3
"""
Homelab Dashboard
Built with NiceGUI + Prometheus + tinytuya (local LAN)
Pages: / (Server) | /energy (Energy Monitor) | /plugs (Smart Plugs)
"""
import os
import sys
import asyncio
import subprocess
import threading
import time

from collections import deque
from datetime import datetime
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from nicegui import ui, app, run
from prometheus_api_client import PrometheusConnect


# ─────────────────────────────────────────────────────────────────────────────
#  Ensure project root is importable (tuya_local, db live in parent dir)
# ─────────────────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tuya_local
import db
import aws_iot_publisher
import cloud_db
# ─────────────────────────────────────────────────────────────────────────────
#  PROMETHEUS
# ─────────────────────────────────────────────────────────────────────────────
prom = PrometheusConnect(url="http://localhost:9090", disable_ssl=True)

# ─────────────────────────────────────────────────────────────────────────────
#  ENV
# ─────────────────────────────────────────────────────────────────────────────
env_path = "/mnt/nvme/Projects/dashboard/.env" 
load_dotenv(env_path)

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — system
# ─────────────────────────────────────────────────────────────────────────────
system_stats = {
    'cpu_percent': 0, 'cpu_temp': 0,
    'memory_percent': 0, 'memory_used_gb': 0, 'memory_total_gb': 0,
    'nvme_percent': 0, 'nvme_used_gb': 0, 'nvme_total_gb': 0, 'nvme_temp': 0,
    'hdd_percent': 0, 'hdd_used_gb': 0, 'hdd_total_gb': 0, 'hdd_status': 'unknown',
}
iot_devices: dict = {}
AI_CACHE_PATH = "/mnt/nvme/Projects/dashboard/gemini_cache.txt"
ai_insights   = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update   = ""

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — Smart Plugs (tinytuya local LAN)
# ─────────────────────────────────────────────────────────────────────────────
PLUG_POLL_INTERVAL = 10  # seconds

plug_state: Dict[str, Dict[str, Any]] = {
    "plug":   {"status": None, "ok": False, "history": deque(maxlen=120)},
    "server": {"status": None, "ok": False, "history": deque(maxlen=120)},
}
plug_lock = threading.Lock()
db_error_notified = False

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — Energy DB cache (avoids blocking UI timers with DB queries)
# ─────────────────────────────────────────────────────────────────────────────
energy_cache: Dict[str, dict] = {
    "plug":   {"total_kwh": 0, "cost_rm": 0},
    "server": {"total_kwh": 0, "cost_rm": 0},
}
energy_cache_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return round(float(f.read()) / 1000.0, 1)
    except:
        return 0

def get_nvme_temp():
    try:
        result = subprocess.run(['smartctl', '-A', '/dev/nvme0n1'],
                                capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'Temperature' in line and 'Celsius' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'Celsius' and i > 0:
                        return int(parts[i-1])
        return 0
    except:
        return 0

def get_hdd_status():
    try:
        result = subprocess.run(['iostat', '-d', 'sda', '1', '2'],
                                capture_output=True, text=True, timeout=3)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 3:
            last_line = lines[-1].split()
            if len(last_line) > 3 and float(last_line[3]) > 0.1:
                return 'active'
        return 'idle'
    except:
        return 'idle'

# ─────────────────────────────────────────────────────────────────────────────
#  PLUG POLLING THREAD (tinytuya local LAN)
# ─────────────────────────────────────────────────────────────────────────────
def plug_polling_loop():
    """Poll both smart plugs via tinytuya and store to DB."""
    last_poll_time: Dict[str, Optional[float]] = {"plug": None, "server": None}

    while True:
        for dev_key in ("plug", "server"):
            status = tuya_local.get_status(dev_key)
            now = time.time()

            with plug_lock:
                if status:
                    plug_state[dev_key]["status"] = status
                    plug_state[dev_key]["ok"]     = True
                    plug_state[dev_key]["history"].append({
                        "t": datetime.now().strftime("%H:%M:%S"),
                        "w": status["watts"],
                    })

                    # Wh delta calculation
                    wh_delta = 0.0
                    if last_poll_time[dev_key]:
                        elapsed_h = (now - last_poll_time[dev_key]) / 3600
                        wh_delta  = status["watts"] * elapsed_h

                    last_poll_time[dev_key] = now

                    # Store to MariaDB
                    try:
                        # Publish to AWS IoT Core
                        aws_iot_publisher.publish(dev_key, status, wh_delta)
                        
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
                    plug_state[dev_key]["ok"] = False

        time.sleep(PLUG_POLL_INTERVAL)

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM METRICS LOOP
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_all_metrics() -> dict:
    """Pure sync function — runs in thread pool via run.io_bound(), never blocks event loop."""
    stats = {}
    iot = {}

    cpu_q = prom.custom_query(
        query='100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
    stats['cpu_percent'] = round(float(cpu_q[0]['value'][1]), 1) if cpu_q else 0
    stats['cpu_temp']    = get_cpu_temp()

    mem_used  = prom.custom_query(query='node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
    mem_total = prom.custom_query(query='node_memory_MemTotal_bytes')
    if mem_used and mem_total:
        stats['memory_used_gb']  = round(float(mem_used[0]['value'][1]) / (1024**3), 2)
        stats['memory_total_gb'] = round(float(mem_total[0]['value'][1]) / (1024**3), 2)
        stats['memory_percent']  = round(
            stats['memory_used_gb'] / stats['memory_total_gb'] * 100, 1)

    nvme_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"} - node_filesystem_avail_bytes{mountpoint="/mnt/nvme"}')
    nvme_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"}')
    if nvme_used and nvme_total:
        stats['nvme_used_gb']  = round(float(nvme_used[0]['value'][1]) / (1024**3), 1)
        stats['nvme_total_gb'] = round(float(nvme_total[0]['value'][1]) / (1024**3), 1)
        stats['nvme_percent']  = round(
            stats['nvme_used_gb'] / stats['nvme_total_gb'] * 100, 1)
    stats['nvme_temp'] = get_nvme_temp()

    hdd_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"} - node_filesystem_avail_bytes{mountpoint="/mnt/hdd-public"}')
    hdd_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"}')
    if hdd_used and hdd_total:
        stats['hdd_used_gb']  = round(float(hdd_used[0]['value'][1]) / (1024**3), 1)
        stats['hdd_total_gb'] = round(float(hdd_total[0]['value'][1]) / (1024**3), 1)
        stats['hdd_percent']  = round(
            stats['hdd_used_gb'] / stats['hdd_total_gb'] * 100, 1)
    stats['hdd_status'] = get_hdd_status()

    esp32_temps    = prom.custom_query(query='esp32_temperature_celsius')
    esp32_humidity = prom.custom_query(query='esp32_humidity_percent')
    for metric in esp32_temps:
        did = metric['metric']['device_id']
        iot.setdefault(did, {})['temperature'] = round(float(metric['value'][1]), 1)
    for metric in esp32_humidity:
        did = metric['metric']['device_id']
        iot.setdefault(did, {})['humidity'] = round(float(metric['value'][1]), 1)

    return {'system': stats, 'iot': iot}


async def update_metrics():
    while True:
        global system_stats, iot_devices, last_update
        try:
            result = await run.io_bound(_fetch_all_metrics)
            system_stats.update(result['system'])
            iot_devices.update(result['iot'])
            last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Metrics error: {e}")
        await asyncio.sleep(7)

# ─────────────────────────────────────────────────────────────────────────────
#  AI INSIGHTS LOOP
# ─────────────────────────────────────────────────────────────────────────────
async def update_ai_insights():
    global ai_insights
    while True:
        try:
            if os.path.exists(AI_CACHE_PATH):
                mtime = datetime.fromtimestamp(os.path.getmtime(AI_CACHE_PATH))
                with open(AI_CACHE_PATH, "r") as f:
                    content = f.read()
                ai_insights = f"🕒 Last Analysis: {mtime.strftime('%H:%M')}\n\n{content}"
            else:
                ai_insights = "🤖 Waiting for Gemini..."
        except Exception as e:
            ai_insights = f"❌ AI Read Error: {e}"
        await asyncio.sleep(300)

# ─────────────────────────────────────────────────────────────────────────────
#  SHARED STYLES
# ─────────────────────────────────────────────────────────────────────────────
def add_common_styles():
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
            
            body { 
                font-family: 'Inter', sans-serif; 
                background: #F4F4F5;
                color: #111827; 
                transition: background 0.3s, color 0.3s; 
                min-height: 100vh;
            }
            body.body--dark { 
                background: #000000;
                color: #FFFFFF; 
            }
            .glass-card { 
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.05); 
                border-radius: 24px; 
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03); 
                transition: transform 0.2s ease, box-shadow 0.2s ease; 
            }
            .glass-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.06);
            }
            body.body--dark .glass-card { 
                background: #1A1A1A; 
                border: none; 
                box-shadow: none;
            }
            body.body--dark .glass-card:hover {
                transform: translateY(-2px);
            }
            
            .dark-highlight-card {
                background: #0F172A;
                color: #FFFFFF;
                border-radius: 24px;
                box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
            }
            body.body--dark .dark-highlight-card {
                background: #222222;
                border: 1px solid rgba(255,255,255,0.05);
                box-shadow: none;
            }

            .split-card {
                border-radius: 24px;
                overflow: hidden;
                display: flex;
                background: #FFFFFF;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
                border: 1px solid rgba(0, 0, 0, 0.05);
            }
            .split-left {
                background: #E11D48;
                color: #FFFFFF;
                padding: 24px;
                flex: 1;
            }
            .split-right {
                background: #FFFFFF;
                padding: 24px;
                flex: 2;
            }
            body.body--dark .split-card {
                background: #1A1A1A;
                border: none;
                box-shadow: none;
            }
            body.body--dark .split-left {
                background: #222222;
                color: #FFFFFF;
            }
            body.body--dark .split-right {
                background: #1A1A1A;
            }

            .glass-header { 
                background: rgba(244, 244, 245, 0.8); 
                backdrop-filter: blur(16px); 
                -webkit-backdrop-filter: blur(16px);
                border-bottom: 1px solid rgba(0, 0, 0, 0.05); 
            }
            body.body--dark .glass-header { 
                background: rgba(0, 0, 0, 0.8); 
                border-bottom: 1px solid rgba(255, 255, 255, 0.1); 
            }
            
            .stat-value { font-family:'Inter',sans-serif; font-size:1.5rem; font-weight:800; color:#E11D48; }
            body.body--dark .stat-value { color: #39FF14; }
            .stat-label { font-size:.75rem; color:#6B7280; text-transform:uppercase; font-weight:700; letter-spacing:.05em; }
            body.body--dark .stat-label { color:#A1A1AA; }

            /* Plug page styles */
            .plug-card { background:#FFFFFF; border:1px solid rgba(0,0,0,.05); border-radius:24px; overflow:hidden; transition:all .3s; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
            body.body--dark .plug-card { background:#1A1A1A; border:none; box-shadow:none; }
            .plug-card.plug-on { border: 1px solid rgba(225, 29, 72, 0.3); box-shadow:0 0 20px rgba(225, 29, 72, 0.1); }
            body.body--dark .plug-card.plug-on { border: 1px solid rgba(57, 255, 20, 0.3); box-shadow:none; }
            
            .plug-stat-strip { display:flex; flex-wrap:wrap; gap:16px; align-items:center; background:#F9FAFB; border-radius:16px; padding:14px 18px; }
            body.body--dark .plug-stat-strip { background:#222222; border:none; }
            
            .plug-stat-num { font-family:'Inter',sans-serif; font-size:1.4rem; font-weight:800; line-height:1; color:#111827; }
            body.body--dark .plug-stat-num { color:#FFFFFF; }
            
            .plug-stat-lbl { font-size:.6rem; color:#6B7280; text-transform:uppercase; letter-spacing:.08em; margin-top:3px; font-weight: 700; }
            body.body--dark .plug-stat-lbl { color:#A1A1AA; }
            
            .plug-sep { width:1px; height:36px; background:rgba(0,0,0,.05); }
            body.body--dark .plug-sep { background:rgba(255,255,255,.05); }

            .plug-toggle { width:100%; padding:14px 0!important; border-radius:999px!important; font-family:'Inter',sans-serif!important; font-size:.85rem!important; font-weight:700!important; letter-spacing:.05em!important; transition:all .3s ease!important; border:none!important;}
            .plug-toggle-on  { background:#E11D48!important; color:#ffffff!important; box-shadow: 0 4px 15px rgba(225, 29, 72, 0.2)!important;}
            body.body--dark .plug-toggle-on { background:#39FF14!important; color:#000000!important; box-shadow: none!important; }
            .plug-toggle-off { background:#F3F4F6!important; color:#4B5563!important; }
            body.body--dark .plug-toggle-off { background:#222222!important; color:#A1A1AA!important; }
            .plug-toggle-warn { background:#FF5E00!important; color:#ffffff!important; box-shadow: 0 4px 15px rgba(255, 94, 0, 0.3)!important;}
            body.body--dark .plug-toggle-warn { background:#FF5E00!important; color:#000000!important; box-shadow: none!important; }

            .plug-energy-row { display:flex; flex-wrap:wrap; gap:10px; background:#F9FAFB; border-radius:16px; padding:14px 18px; }
            body.body--dark .plug-energy-row { background:#222222; }

            .plug-ctrl-btn { background:#F3F4F6!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-family:'Inter',sans-serif!important; font-weight:600!important; font-size:.75rem!important; padding:9px 16px!important; transition:all .2s!important; }
            body.body--dark .plug-ctrl-btn { background:#222222!important; color:#E5E7EB!important; }
            .plug-ctrl-btn:hover { background:#E5E7EB!important; color:#111827!important; }
            body.body--dark .plug-ctrl-btn:hover { background:#333333!important; color:#FFFFFF!important; }

            .plug-led-btn { background:#F3F4F6!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-weight:600!important; font-size:.7rem!important; padding:8px 12px!important; transition:all .2s!important; flex:1; min-width:70px; }
            body.body--dark .plug-led-btn { background:#222222!important; color:#A1A1AA!important; }
            .plug-led-btn:hover { background:#E5E7EB!important; color:#111827!important; }
            body.body--dark .plug-led-btn:hover { background:#333333!important; color:#FFFFFF!important; }

            .dot-ok  { width:10px;height:10px;border-radius:50%;background:#E11D48;display:inline-block; }
            body.body--dark .dot-ok { background:#39FF14; }
            .dot-err { width:10px;height:10px;border-radius:50%;background:#F87171;display:inline-block; }
            body.body--dark .dot-err { background:#FF5E00; }

            .plug-warn-banner { background:#FEF2F2; border-radius:16px; padding:12px 16px; margin-top:10px; font-family:'Inter',sans-serif; font-size:.75rem; color:#991B1B; font-weight:500; display:none; }
            body.body--dark .plug-warn-banner { background:#431407; color:#FFEDD5; }
            .plug-warn-banner.visible { display:block; }

            .plug-section-title { font-family:'Inter',sans-serif; font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; color:#6B7280; margin-bottom:10px; font-weight: 700; }
            body.body--dark .plug-section-title { color:#A1A1AA; }
            
            .plug-inner-card { background:#F9FAFB; border-radius:20px; padding:16px 18px; margin-top:12px; }
            body.body--dark .plug-inner-card { background:#222222; }

            /* Select & Dropdown styling */
            .q-field--outlined .q-field__control { border-radius: 999px !important; }
            .q-field--outlined .q-field__control:before { border: 1px solid rgba(0, 0, 0, 0.1) !important; background: #FFFFFF !important; transition: all 0.3s; }
            body.body--dark .q-field--outlined .q-field__control:before { border: none !important; background: #222222 !important; }
            .q-field:hover .q-field__control:before { border-color: rgba(0, 0, 0, 0.2) !important; }
            body.body--dark .q-field:hover .q-field__control:before { background: #2A2A2A !important; }
            
            .glass-menu { background: #FFFFFF !important; border: 1px solid rgba(0, 0, 0, 0.05) !important; border-radius: 16px !important; box-shadow: 0 10px 25px rgba(0,0,0,0.1) !important; padding: 4px 0; }
            body.body--dark .glass-menu { background: #1A1A1A !important; border: 1px solid rgba(255,255,255,0.05) !important; color: #FFFFFF !important; box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;}
            .glass-menu .q-item { border-radius: 12px; margin: 2px 6px; transition: all 0.2s; }
            .glass-menu .q-item:hover { background: #F3F4F6 !important; }
            body.body--dark .glass-menu .q-item:hover { background: #222222 !important; }
            .glass-menu .q-item--active { background: #E11D48 !important; color: #FFFFFF !important; font-weight: 600; }
            body.body--dark .glass-menu .q-item--active { background: #39FF14 !important; color: #000000 !important; }

            /* Active Toggle for navigation */
            .q-btn-group { border-radius: 999px !important; background: #F3F4F6 !important; padding: 4px; box-shadow: none !important; border: 1px solid rgba(0,0,0,0.05) !important; }
            body.body--dark .q-btn-group { background: #1A1A1A !important; border: none !important; }
            .q-btn-group .q-btn { border-radius: 999px !important; font-weight: 600 !important; color: #6B7280 !important; }
            body.body--dark .q-btn-group .q-btn { color: #A1A1AA !important; }
            .q-btn-group .q-btn.bg-primary { background: #0F172A !important; color: #FFFFFF !important; }
            body.body--dark .q-btn-group .q-btn.bg-primary { background: #333333 !important; color: #FFFFFF !important; border: 1px solid rgba(255,255,255,0.1) !important; }
        </style>
    ''')

# ─────────────────────────────────────────────────────────────────────────────
#  (nav_toggle removed, using index_page SPA toggle instead)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — SERVER
# ─────────────────────────────────────────────────────────────────────────────
def render_server_content():
    with ui.column().classes('w-full gap-4 sm:gap-8'):


        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        with ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4'):

            with ui.card().classes('glass-card p-5 flex flex-col items-center relative overflow-hidden'):
                ui.label('CPU Load').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('speed', size='sm', color='primary').classes('absolute top-4 right-4 opacity-50')
                with ui.circular_progress(min=0, max=100, show_value=True, size='110px', color='primary').props('thickness=0.1').classes('mt-4') as p:
                    p.bind_value_from(system_stats, 'cpu_percent')
                ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'{x}°C').classes('text-2xl font-bold text-slate-900 dark:text-white mt-4')
                ui.label('Core Temp').classes('text-xs text-slate-500')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MEMORY').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                with ui.row().classes('items-end gap-2'):
                    ui.label().bind_text_from(system_stats, 'memory_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-secondary')
                    ui.label('Used').classes('text-sm text-slate-600 dark:text-slate-500 mb-2')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'memory_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=secondary track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'memory_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'memory_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('NVME STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'nvme_temp', backward=lambda x: f'{x}°C').classes('absolute top-4 right-5 text-lg text-accent font-bold')
                with ui.row().classes('items-end gap-2'):
                    ui.label().bind_text_from(system_stats, 'nvme_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-accent')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'nvme_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=accent track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'nvme_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'nvme_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MASS STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: x.upper()).classes('absolute top-4 right-5 text-lg font-bold text-slate-400 dark:text-slate-300')
                with ui.row().classes('items-end justify-between w-full'):
                    ui.label().bind_text_from(system_stats, 'hdd_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-positive')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'hdd_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=positive track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'hdd_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

        with ui.row().classes('items-center gap-2 mt-8 mb-2'):
            ui.icon('sensors', color='secondary')
            ui.label('IoT Environment').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        iot_container = ui.row().classes(
            'w-full gap-4 sm:gap-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 items-stretch')

        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if iot_devices:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes(
                            'glass-card p-4 min-w-[200px] hover:scale-105 '
                            'transition-transform h-full flex flex-col justify-between'):
                            with ui.row().classes('items-center gap-3 mb-3'):
                                ui.icon('wifi', size='xs').classes('text-slate-400 dark:text-slate-300')
                                with ui.column().classes('gap-0'):
                                    ui.label(device_id.replace('esp32-', '').title()).classes(
                                        'text-md font-bold text-slate-700 dark:text-slate-200')
                                    ui.label('Active').classes(
                                        'text-[10px] text-positive uppercase tracking-wide')
                            ui.separator().classes('bg-slate-300/50 dark:bg-slate-700/50 mb-3')
                            with ui.row().classes('justify-between items-center gap-6 mt-auto'):
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('thermostat', size='xs', color='orange')
                                    ui.label(f"{data.get('temperature', 0)}°C").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('water_drop', size='xs', color='blue')
                                    ui.label(f"{data.get('humidity', 0)}%").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')

                # Quick plug status summary cards
                for dev_key in ("plug", "server"):
                    with plug_lock:
                        s  = plug_state[dev_key]["status"]
                        ok = plug_state[dev_key]["ok"]
                    cfg = tuya_local.DEVICES[dev_key]

                    with ui.card().classes(
                        'glass-card p-4 min-w-[200px] hover:scale-105 '
                        'transition-transform h-full flex flex-col justify-between'):
                        with ui.row().classes('items-center gap-3 mb-3'):
                            ui.icon('power', size='xs',
                                    color='positive' if (s and s["switch"]) else 'grey')
                            with ui.column().classes('gap-0'):
                                ui.label(cfg["name"]).classes(
                                    'text-md font-bold text-slate-700 dark:text-slate-200')
                                if ok and s:
                                    ui.label('ON' if s["switch"] else 'OFF').classes(
                                        f'text-[10px] uppercase tracking-wide font-semibold '
                                        f'{"text-positive" if s["switch"] else "text-slate-400"}')
                                else:
                                    ui.label('Offline').classes(
                                        'text-[10px] text-red-400 uppercase tracking-wide')
                        ui.separator().classes('bg-slate-300/50 dark:bg-slate-700/50 mb-3')
                        if s:
                            with ui.row().classes('justify-between items-center gap-6 mt-auto'):
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('bolt', size='xs', color='warning')
                                    ui.label(f"{s['watts']:.1f}W").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('electrical_services', size='xs', color='blue')
                                    ui.label(f"{s['voltage']:.1f}V").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                        else:
                            ui.label('No data').classes('text-sm text-slate-500 mt-auto')

        ui.timer(6.0, update_iot_display)

        with ui.card().classes(
            'glass-card w-full p-4 sm:p-6 mt-2 sm:mt-4 bg-slate-200/50 dark:bg-slate-800/50 '
            'border-l-4 border-slate-300 dark:border-white'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    ui.label('DeepMind Analysis').classes(
                        'text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest mb-1')
                    ui.label().bind_text_from(globals(), 'ai_insights').classes(
                        'text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed')

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — ENERGY
# ─────────────────────────────────────────────────────────────────────────────
def render_energy_content():
    peak_watt = [0.0]
    selected_device = {'value': 'all'}  # default device for energy view

    with ui.column().classes('w-full gap-4 sm:gap-6'):


        with ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 md:grid-cols-3 items-stretch'):

            # 1. Live Power
            with ui.card().classes('glass-card p-6 flex flex-col items-center justify-center relative overflow-hidden'):
                ui.label('LIVE POWER').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('bolt', size='sm', color='warning').classes('absolute top-4 right-4 opacity-30')
                live_power_label = ui.label('0.0').classes('text-5xl sm:text-6xl font-black text-transparent bg-clip-text bg-gradient-to-br from-yellow-400 to-orange-500 mt-6 drop-shadow-[0_0_15px_rgba(245,158,11,0.4)] transition-all duration-300')
                ui.label('Watts (W)').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')
                
            # 2. Today's Total Energy
            with ui.card().classes('glass-card p-6 flex flex-col items-center justify-center relative overflow-hidden'):
                ui.label("TODAY'S ENERGY").classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('eco', size='sm', color='positive').classes('absolute top-4 right-4 opacity-30')
                total_kwh_label = ui.label('0.000').classes('text-5xl sm:text-6xl font-black text-transparent bg-clip-text bg-gradient-to-br from-green-400 to-emerald-500 mt-6 drop-shadow-[0_0_15px_rgba(16,185,129,0.4)] transition-all duration-300')
                ui.label('kWh').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')

            # 3. Total Cost
            with ui.card().classes('glass-card p-6 flex flex-col items-center justify-center relative overflow-hidden'):
                ui.label("TOTAL COST").classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('payments', size='sm', color='primary').classes('absolute top-4 right-4 opacity-30')
                cost_label = ui.label('0.00').classes('text-5xl sm:text-6xl font-black text-transparent bg-clip-text bg-gradient-to-br from-blue-400 to-indigo-500 mt-6 drop-shadow-[0_0_15px_rgba(59,130,246,0.4)] transition-all duration-300')
                ui.label('RM').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')

        with ui.row().classes('w-full gap-4 sm:gap-6 items-stretch flex-col lg:flex-row'):

            with ui.column().classes('flex flex-col gap-4 flex-1 justify-center w-full'):
                with ui.card().classes('glass-card p-4 w-full flex flex-row items-center justify-between'):
                    with ui.column():
                        ui.label('PEAK USAGE').classes('stat-label')
                        ui.label('Highest spike this session').classes('text-[10px] text-slate-500')
                    with ui.row().classes('items-baseline gap-1'):
                        peak_usage_label = ui.label('0.000').classes('stat-value text-warning')
                        ui.label('kW').classes('text-xs text-slate-400 font-bold')

                with ui.card().classes('glass-card p-4 w-full flex flex-row items-center justify-between'):
                    with ui.column():
                        ui.label('MONTH ACCUMULATE USAGE').classes('stat-label')
                        ui.label('Total energy this month').classes('text-[10px] text-slate-500')
                    with ui.row().classes('items-baseline gap-1'):
                        month_usage_label = ui.label('0.000').classes('stat-value text-secondary')
                        ui.label('kWh').classes('text-xs text-slate-400 font-bold')

            with ui.card().classes('glass-card p-4 sm:p-6 flex flex-col gap-4 w-full lg:w-[300px]'):
                ui.label('Controls').classes('text-sm font-bold text-slate-400 uppercase')

                def on_device_change(e):
                    if e.value == 'Server Plug':
                        selected_device['value'] = 'server'
                    elif e.value == 'Smart Plug':
                        selected_device['value'] = 'plug'
                    else:
                        selected_device['value'] = 'all'

                ui.select(
                    ['All Plugs (Total)', 'Smart Plug', 'Server Plug'], value='All Plugs (Total)',
                    label='Device Selector', on_change=on_device_change
                ).props('outlined rounded popup-content-class="glass-menu"').classes('w-full')

        # ── Power history chart ──────────────────────────────────────────────
        chart_filter = {'value': 'Live'}
        with ui.element('div').classes('split-card w-full mb-6'):
            with ui.column().classes('split-left flex flex-col justify-between gt-sm'):
                with ui.column():
                    ui.label('Analytics').classes('text-xs font-bold uppercase tracking-widest opacity-80 mb-2')
                    ui.label('Energy\nTrends').classes('text-3xl font-black mt-2 whitespace-pre-line leading-tight')
                    ui.label('Monitor power consumption over time to optimize usage.').classes('text-sm opacity-90 mt-4')
                ui.icon('monitoring', size='xl').classes('mt-8 opacity-40')
            with ui.column().classes('split-right'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    with ui.column().classes('gap-0'):
                        chart_title = ui.label('Power Usage — Live').classes('text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest')
                        chart_cost = ui.label('').classes('text-[10px] font-bold text-emerald-500 hidden')
                    
                    def on_filter_change(e):
                        chart_filter['value'] = e.value
                        chart_title.set_text(f'Power Usage — {e.value}')
                        if e.value == 'Live':
                            chart_cost.classes(add='hidden')
                        else:
                            chart_cost.classes(remove='hidden')
                        
                    ui.toggle(['Live', 'Day', 'Week', 'Month'], value='Live', on_change=on_filter_change).props('unelevated size=sm').classes('bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400')

                area_chart = ui.echart({
                    'tooltip': {
                        'trigger': 'axis',
                        'backgroundColor': 'rgba(15, 23, 42, 0.6)',
                        'borderColor': 'rgba(255, 255, 255, 0.2)',
                        'textStyle': {'color': '#f8fafc', 'fontFamily': 'Inter'}
                    },
                    'legend':  {'data': ['Power (W)'], 'textStyle': {'color': '#94a3b8'}, 'top': 0, 'right': 0},
                    'grid':    {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                    'xAxis':   [{'type': 'category', 'boundaryGap': False, 'data': [],
                                 'axisLabel': {'color': '#94a3b8', 'rotate': 45},
                                 'splitLine': {'show': True, 'lineStyle': {'color': 'rgba(255,255,255,0.05)'}} }],
                    'yAxis':   [{'type': 'value', 'name': 'Watts',
                                 'nameTextStyle': {'color': '#94a3b8'},
                                 'axisLabel': {'color': '#94a3b8'},
                                 'splitLine': {'show': True, 'lineStyle': {'color': 'rgba(255,255,255,0.05)'}} }],
                    'series':  [{'name': 'Power (W)', 'type': 'line', 'smooth': True,
                                 'lineStyle': {
                                     'color': '#8b5cf6',
                                     'width': 3,
                                     'shadowColor': 'rgba(139, 92, 246, 0.5)',
                                     'shadowBlur': 10
                                 },
                                 'areaStyle': {'color': {
                                     'type': 'linear', 'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                     'colorStops': [
                                         {'offset': 0, 'color': 'rgba(139, 92, 246, 0.4)'},
                                         {'offset': 1, 'color': 'rgba(139, 92, 246, 0.0)'},
                                     ],
                                 }},
                                 'itemStyle': {'color': '#8b5cf6', 'borderColor': '#fff', 'borderWidth': 2},
                                 'symbolSize': 6,
                                 'data': []}],
                }).classes('w-full h-[300px]')

        async def update_energy_stats():
            dk = selected_device['value']

            if dk == 'all':
                pwr_w, today_kwh, cost_rm, month_kwh = 0.0, 0.0, 0.0, 0.0
                with plug_lock:
                    for d_key in ["plug", "server"]:
                        s = plug_state[d_key]["status"]
                        if s: pwr_w += s["watts"]
                    h1 = list(plug_state["plug"]["history"])
                    h2 = list(plug_state["server"]["history"])

                # Read from cache — zero blocking
                with energy_cache_lock:
                    for d_key in ["plug", "server"]:
                        today_kwh += energy_cache[d_key]["total_kwh"]
                        cost_rm += energy_cache[d_key]["cost_rm"]
                        month_kwh += energy_cache[d_key]["total_kwh"] + (42.5 if d_key == "plug" else 150.2)
                
                pwr_kw = pwr_w / 1000.0
                min_len = min(len(h1), len(h2))
                labels = [h1[i]["t"] for i in range(min_len)] if min_len > 0 else []
                values = [round(h1[i]["w"] + h2[i]["w"], 1) for i in range(min_len)] if min_len > 0 else []

            else:
                with plug_lock:
                    s = plug_state[dk]["status"]
                    history = list(plug_state[dk]["history"])

                if not s: return

                pwr_w  = s["watts"]
                pwr_kw = pwr_w / 1000.0
                
                # Read from cache — zero blocking
                with energy_cache_lock:
                    today_kwh = energy_cache[dk]["total_kwh"]
                    cost_rm   = energy_cache[dk]["cost_rm"]
                    
                month_kwh = today_kwh + (42.5 if dk == "plug" else 150.2)
                labels = [p["t"] for p in history]
                values = [round(p["w"], 1) for p in history]

            live_power_label.set_text(f"{pwr_w:.1f}")
            total_kwh_label.set_text(f"{today_kwh:.3f}")
            cost_label.set_text(f"{cost_rm:.4f}")
            month_usage_label.set_text(f"{month_kwh:.3f}")

            if pwr_kw > peak_watt[0]:
                peak_watt[0] = pwr_kw
                peak_usage_label.set_text(f"{pwr_kw:.3f}")

            # Update chart with history or DB intervals (offloaded to thread pool)
            if chart_filter['value'] != 'Live':
                from datetime import datetime
                labels, values = [], []
                
                try:
                    if chart_filter['value'] == 'Day':
                        if dk == 'all':
                            pts1 = await run.io_bound(db.get_hourly_history, tuya_local.DEVICES["plug"]["id"], 24)
                            pts2 = await run.io_bound(db.get_hourly_history, tuya_local.DEVICES["server"]["id"], 24)
                            d1 = {p["hour_str"]: p["kwh"] for p in pts1}
                            d2 = {p["hour_str"]: p["kwh"] for p in pts2}
                            all_hours = sorted(list(set(d1.keys()) | set(d2.keys())))
                            pts = [{"hour_str": h, "kwh": d1.get(h, 0) + d2.get(h, 0)} for h in all_hours]
                        else:
                            pts = await run.io_bound(db.get_hourly_history, tuya_local.DEVICES[dk]["id"], 24)
                        labels = [datetime.strptime(p["hour_str"], "%Y-%m-%d %H:%M:%S").strftime("%H:00") for p in pts]
                        values = [round(p["kwh"], 3) for p in pts]
                        area_chart.options['yAxis'][0]['name'] = 'Energy (kWh)'
                        area_chart.options['series'][0]['name'] = 'Energy (kWh)'

                    elif chart_filter['value'] in ['Week', 'Month']:
                        days_limit = 7 if chart_filter['value'] == 'Week' else 30
                        if dk == 'all':
                            pts1 = await run.io_bound(db.get_daily_history, tuya_local.DEVICES["plug"]["id"], days_limit)
                            pts2 = await run.io_bound(db.get_daily_history, tuya_local.DEVICES["server"]["id"], days_limit)
                            d1 = {str(p["date_str"]): p["kwh"] for p in pts1}
                            d2 = {str(p["date_str"]): p["kwh"] for p in pts2}
                            all_days = sorted(list(set(d1.keys()) | set(d2.keys())))
                            pts = [{"date_str": d, "kwh": d1.get(d, 0) + d2.get(d, 0)} for d in all_days]
                        else:
                            pts = await run.io_bound(db.get_daily_history, tuya_local.DEVICES[dk]["id"], days_limit)
                        labels = [datetime.strptime(str(p["date_str"]), "%Y-%m-%d").strftime("%b %d") for p in pts]
                        values = [round(p["kwh"], 3) for p in pts]
                        area_chart.options['yAxis'][0]['name'] = 'Energy (kWh)'
                        area_chart.options['series'][0]['name'] = 'Energy (kWh)'
                        
                    total_kwh = sum(values)
                    chart_cost.set_text(f"EST. COST: RM {db.calculate_tnb_cost(total_kwh):.2f}")
                except Exception as e:
                    print(f"Chart error: {e}")
            else:
                area_chart.options['yAxis'][0]['name'] = 'Watts'
                area_chart.options['series'][0]['name'] = 'Power (W)'
                chart_cost.set_text("")

            area_chart.options['xAxis'][0]['data']  = labels
            area_chart.options['series'][0]['data'] = values
            area_chart.update()

        ui.timer(3.0, update_energy_stats)


# ─────────────────────────────────────────────────────────────────────────────
#  PLUG PAGE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _plug_chart_options(dev_key: str) -> dict:
    """Build ECharts options for a plug's power history."""
    with plug_lock:
        pts = list(plug_state[dev_key]["history"])
    labels = [p["t"] for p in pts]
    values = [round(p["w"], 1) for p in pts]
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "#1e293b", "borderColor": "#334155",
            "textStyle": {"color": "#f8fafc", "fontFamily": "Courier New", "fontSize": 11},
        },
        "grid": {"left": "9%", "right": "3%", "top": "10%", "bottom": "20%"},
        "xAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#94a3b8", "fontSize": 9, "rotate": 35},
            "axisLine": {"lineStyle": {"color": "#334155"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#94a3b8", "fontSize": 9},
            "splitLine": {"lineStyle": {"color": "#334155", "type": "dashed"}},
        },
        "series": [{
            "data": values, "type": "line", "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#10b981", "width": 2},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(16,185,129,.28)"},
                    {"offset": 1, "color": "rgba(16,185,129,.02)"},
                ],
            }},
        }],
    }


def _build_plug_panel(dev_key: str) -> dict:
    """Build one full device card for the /plugs page. Returns UI refs."""
    cfg       = tuya_local.DEVICES[dev_key]
    is_server = cfg["is_server"]
    dev_id    = cfg["id"]

    server_off_confirm = {"pending": False}

    card_cls = "plug-card server-card" if is_server else "plug-card"
    with plug_lock:
        s  = plug_state[dev_key]["status"]
        ok = plug_state[dev_key]["ok"]
    on = s["switch"] if s else False
    if on:
        card_cls += " plug-on"

    with ui.element("div").classes(card_cls).style("padding:22px") as card_el:

        # Header
        with ui.row().classes("items-center justify-between mb-3"):
            with ui.element("div"):
                ui.label(cfg["name"].upper()).classes("plug-section-title").style("margin-bottom:2px")
                if is_server:
                    ui.label("⚠ SERVER POWER — DOUBLE CONFIRM TO OFF").style(
                        "font-size:.6rem;color:#f87171;font-family:monospace;letter-spacing:.08em")
                else:
                    ui.label("PLACEHOLDER").style(
                        "font-size:.6rem;font-family:monospace;letter-spacing:.08em;opacity:0;user-select:none")
            conn_dot = ui.element("span").classes("dot-ok" if ok else "dot-err")

        # Status strip
        with ui.element("div").classes("plug-stat-strip"):
            ref_watts = ui.label("—").classes("plug-stat-num").style("color:#f59e0b")
            ui.label("W · POWER").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            ref_voltage = ui.label("—").classes("plug-stat-num").style("color:#a78bfa")
            ui.label("V · VOLTAGE").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            ref_current = ui.label("—").classes("plug-stat-num").style("color:#fb923c")
            ui.label("mA · CURRENT").classes("plug-stat-lbl")

        # Toggle button
        toggle_btn = ui.button(
            "● ON" if on else "○ OFF",
            on_click=lambda: handle_toggle()
        ).classes(f"plug-toggle {'plug-toggle-on' if on else 'plug-toggle-off'}").style("margin-top:14px")

        # Warning banner (server only)
        if is_server:
            warn_ref = ui.element("div").classes("plug-warn-banner")
            with warn_ref:
                ui.label("⚠ WARNING: This will cut power to the server. Click OFF again to confirm.")
        else:
            warn_ref = None

        async def handle_toggle():
            with plug_lock:
                st = plug_state[dev_key]["status"]
            current_on = st["switch"] if st else False

            if not current_on:
                ok_cmd = await run.io_bound(tuya_local.set_switch, dev_key, True)
                if ok_cmd:
                    await run.io_bound(db.insert_state_change, dev_id, cfg["name"], True)
                    server_off_confirm["pending"] = False
                    # Update button UI immediately
                    toggle_btn.classes(remove="plug-toggle-on plug-toggle-off plug-toggle-warn").classes("plug-toggle-on")
                    toggle_btn.set_text("● ON")
                    if warn_ref:
                        warn_ref.style("display:none")
                    card_el.classes(add="plug-on")
                    ui.notify("✅ Turned ON", type="positive")
                else:
                    ui.notify("⚠ Command failed", type="warning")
                return

            if is_server and not server_off_confirm["pending"]:
                server_off_confirm["pending"] = True
                toggle_btn.classes(remove="plug-toggle-on plug-toggle-off").classes("plug-toggle-warn")
                toggle_btn.set_text("⚠ CLICK AGAIN TO CONFIRM OFF")
                if warn_ref:
                    warn_ref.style("display:block")
                ui.notify("⚠ Server plug — click again to confirm OFF", type="warning")
                return

            ok_cmd = await run.io_bound(tuya_local.set_switch, dev_key, False)
            if ok_cmd:
                await run.io_bound(db.insert_state_change, dev_id, cfg["name"], False)
                server_off_confirm["pending"] = False
                # Update button UI immediately
                toggle_btn.classes(remove="plug-toggle-on plug-toggle-off plug-toggle-warn").classes("plug-toggle-off")
                toggle_btn.set_text("○ OFF")
                if warn_ref:
                    warn_ref.style("display:none")
                card_el.classes(remove="plug-on")
                ui.notify("🔴 Turned OFF", type="negative")
            else:
                ui.notify("⚠ Command failed", type="warning")
                server_off_confirm["pending"] = False

        # Energy strip
        with ui.element("div").classes("plug-energy-row").style("margin-top:14px"):
            with ui.element("div"):
                ref_today_kwh = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY kWh").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            with ui.element("div"):
                ref_today_rm = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY RM EST.").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            with ui.element("div"):
                ref_total_kwh = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#a5b4fc")
                ui.label("LIFETIME kWh").classes("plug-stat-lbl")

        # Chart
        with ui.element("div").classes("plug-inner-card"):
            ui.label("POWER HISTORY (W)").classes("plug-section-title")
            chart = ui.echart(_plug_chart_options(dev_key)).style("height:180px;width:100%")

        # Controls
        with ui.element("div").classes("plug-inner-card"):
            ui.label("CONTROLS").classes("plug-section-title")

            with ui.row().classes("gap-2 w-full"):
                ui.button("🔒 Lock ON",
                    on_click=lambda: _exec_cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, True), "Child Lock ON")
                ).classes("plug-ctrl-btn")
                ui.button("🔓 Lock OFF",
                    on_click=lambda: _exec_cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, False), "Child Lock OFF")
                ).classes("plug-ctrl-btn")

            with ui.row().classes("gap-2 items-end w-full").style("margin-top:10px"):
                countdown_inp = ui.number(
                    label="Countdown (seconds)", value=0, min=0, max=86400
                ).props("dense outlined").style("flex:1;font-size:.8rem")
                ui.button("Set",
                    on_click=lambda: _exec_cmd(dev_key,
                        lambda: tuya_local.set_countdown(dev_key, int(countdown_inp.value or 0)),
                        f"Timer {int(countdown_inp.value or 0)}s")
                ).props("dense").style("font-size:.72rem;padding:6px 14px")

        # LED control
        with ui.element("div").classes("plug-inner-card"):
            ui.label("INDICATOR LED").classes("plug-section-title")
            with ui.row().classes("gap-2 w-full"):
                for label, val in [("Follow Relay", "relay"), ("Always ON", "pos"), ("Always OFF", "none")]:
                    ui.button(label,
                        on_click=lambda v=val, l=label: _exec_cmd(dev_key,
                            lambda mode=v: tuya_local.set_led_mode(dev_key, mode),
                            f"LED → {l}")
                    ).classes("plug-led-btn")

    async def _exec_cmd(dk, fn, label):
        ok_cmd = await run.io_bound(fn)
        ui.notify(f"✅ {label}" if ok_cmd else f"⚠ {label} failed",
                  type="positive" if ok_cmd else "warning")

    return {
        "card_el":       card_el,
        "conn_dot":      conn_dot,
        "toggle_btn":    toggle_btn,
        "warn_ref":      warn_ref,
        "ref_watts":     ref_watts,
        "ref_voltage":   ref_voltage,
        "ref_current":   ref_current,
        "ref_today_kwh": ref_today_kwh,
        "ref_today_rm":  ref_today_rm,
        "ref_total_kwh": ref_total_kwh,
        "chart":         chart,
        "server_off_confirm": server_off_confirm,
        "dev_key":       dev_key,
        "dev_id":        dev_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — PLUGS
# ─────────────────────────────────────────────────────────────────────────────
def render_plugs_content():
    with ui.column().classes('w-full gap-4 sm:gap-6'):


        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('electrical_services', color='positive')
            ui.label('Device Control').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        with ui.grid().classes('w-full gap-6 grid-cols-1 lg:grid-cols-2'):
            plug_refs   = _build_plug_panel("plug")
            server_refs = _build_plug_panel("server")

    # ── Live update timer ────────────────────────────────────────────────
    def _update_panel(refs: dict):
        dk = refs["dev_key"]
        with plug_lock:
            s  = plug_state[dk]["status"]
            ok = plug_state[dk]["ok"]

        refs["conn_dot"].classes(remove="dot-ok dot-err").classes("dot-ok" if ok else "dot-err")

        if not s:
            return

        on = s["switch"]

        # Toggle button (skip if warn-pending)
        if not refs.get("server_off_confirm", {}).get("pending"):
            refs["toggle_btn"].classes(
                remove="plug-toggle-on plug-toggle-off plug-toggle-warn"
            ).classes("plug-toggle-on" if on else "plug-toggle-off")
            refs["toggle_btn"].set_text("● ON" if on else "○ OFF")

        # Card on/off glow
        if on:
            refs["card_el"].classes(add="plug-on")
        else:
            refs["card_el"].classes(remove="plug-on")

        # Live readings
        refs["ref_watts"].set_text(f"{s['watts']:.1f}")
        refs["ref_voltage"].set_text(f"{s['voltage']:.1f}")
        refs["ref_current"].set_text(f"{s['current_ma']}")
        refs["ref_total_kwh"].set_text(f"{s['add_ele_kwh']:.3f}")

        # Today's energy from cache — zero blocking
        with energy_cache_lock:
            today = energy_cache[dk].copy()
        refs["ref_today_kwh"].set_text(f"{today['total_kwh']:.4f}")
        refs["ref_today_rm"].set_text(f"RM {today['cost_rm']:.4f}")

        # Chart
        new_opts = _plug_chart_options(dk)
        refs["chart"].options.update(new_opts)
        refs["chart"].update()

    def _refresh_plugs():
        _update_panel(plug_refs)
        _update_panel(server_refs)

    ui.timer(4.0, _refresh_plugs)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN SPA PAGE  /
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/')
def index_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
              positive='#10b981', warning='#f59e0b')
    
    with ui.header().classes('glass-header items-center justify-between p-3 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto sm:flex-1 justify-center sm:justify-start relative'):
            ui.icon('dns', size='md', color='primary').classes('drop-shadow-md')
            ui.label('HOMELAB').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            # Mobile-only dark mode button placed on the right edge
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('lt-sm absolute right-2 text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')
        
        with ui.row().classes('items-center justify-center z-10 w-full sm:w-auto sm:flex-1 mt-3 sm:mt-0'):
            toggle = ui.toggle(
                ['Server', 'Energy', 'Plugs'], value='Server'
            ).props('unelevated rounded').classes('q-btn-group').style('border-radius: 20px; font-weight: 600;')

        with ui.row().classes('items-center justify-end gap-4 z-10 gt-xs sm:flex-1'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1 gt-sm'):
                ui.icon('schedule', size='xs', color='gray-400')
                ui.label().bind_text_from(globals(), 'last_update').classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto px-4 sm:px-6 pt-0 pb-4 sm:pb-6 mt-0 gap-4 sm:gap-8'):
        with ui.tab_panels(toggle, value='Server').classes('w-full bg-transparent p-0'):
            with ui.tab_panel('Server').classes('p-0'):
                render_server_content()
            with ui.tab_panel('Energy').classes('p-0'):
                render_energy_content()
            with ui.tab_panel('Plugs').classes('p-0'):
                render_plugs_content()

# ─────────────────────────────────────────────────────────────────────────────
#  ENERGY CACHE LOOP (runs in background thread, feeds UI timers)
# ─────────────────────────────────────────────────────────────────────────────
def energy_cache_loop():
    """Single background thread polls DB summaries every 10s, caches results.
    UI timers read from this cache instead of querying DB directly."""
    while True:
        for dev_key in ("plug", "server"):
            try:
                summary = db.get_today_summary(tuya_local.DEVICES[dev_key]["id"])
                with energy_cache_lock:
                    energy_cache[dev_key] = summary
            except Exception as e:
                print(f"[energy_cache] {dev_key}: {e}")
        time.sleep(10)


# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────────────────────
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))
threading.Thread(target=plug_polling_loop, daemon=True).start()
threading.Thread(target=energy_cache_loop, daemon=True).start()

@ui.page('/cloud')
async def cloud_page():
    add_common_styles()

    with ui.column().classes('w-full q-pa-md gap-6'):

        ui.label('☁️ Cloud Monitor — AWS DynamoDB').classes('text-h4 text-bold q-mb-sm')

        # ── Today's summary cards ──────────────────────────────────────────────
        ui.label("Today's Summary").classes('text-h6 text-grey-4')
        with ui.row().classes('w-full gap-4'):
            for dev_key, dev_name in [('plug', 'Smart Plug'), ('server', 'Server Plug')]:
                summary = cloud_db.get_today_summary(dev_key)
                with ui.card().classes('flex-1 q-pa-md'):
                    ui.label(dev_name).classes('text-subtitle1 text-bold q-mb-sm')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        for label, value in [
                            ('Readings',   str(summary['readings'])),
                            ('Total kWh',  f"{summary['total_kwh']:.5f}"),
                            ('Avg Watts',  f"{summary['avg_watts']} W"),
                            ('Peak Watts', f"{summary['peak_watts']} W"),
                        ]:
                            with ui.column().classes('gap-0'):
                                ui.label(label).classes('text-caption text-grey-5')
                                ui.label(value).classes('text-body1 text-bold')

        ui.separator()

        # ── Recent readings tables ─────────────────────────────────────────────
        COLUMNS = [
            {'name': 'ts', 'label': 'Timestamp',    'field': 'ts', 'align': 'left'},
            {'name': 'w',  'label': 'Watts',         'field': 'w',  'align': 'right'},
            {'name': 'v',  'label': 'Voltage (V)',   'field': 'v',  'align': 'right'},
            {'name': 'ma', 'label': 'Current (mA)',  'field': 'ma', 'align': 'right'},
            {'name': 'wh', 'label': 'Wh Δ',          'field': 'wh', 'align': 'right'},
            {'name': 'sw', 'label': 'Switch',        'field': 'sw', 'align': 'center'},
        ]

        for dev_key, dev_name in [('plug', 'Smart Plug'), ('server', 'Server Plug')]:
            ui.label(f'{dev_name} — Last 15 Readings').classes('text-h6 q-mt-sm')
            readings = cloud_db.get_recent_readings(dev_key, limit=15)

            if readings:
                rows = [{
                    'ts': r['timestamp'][:19].replace('T', ' '),
                    'w':  float(r.get('watts', 0)),
                    'v':  float(r.get('voltage', 0)),
                    'ma': int(float(r.get('current_ma', 0))),
                    'wh': round(float(r.get('wh_delta', 0)), 5),
                    'sw': '🟢 ON' if r.get('switch') else '🔴 OFF',
                } for r in readings]
                ui.table(columns=COLUMNS, rows=rows, row_key='ts').classes('w-full')
            else:
                ui.label('No data available').classes('text-grey')

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard', reload=False, favicon='🏠')
