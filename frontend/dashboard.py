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

from nicegui import ui, app
from prometheus_api_client import PrometheusConnect

# ─────────────────────────────────────────────────────────────────────────────
#  Ensure project root is importable (tuya_local, db live in parent dir)
# ─────────────────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tuya_local
import db

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
async def update_metrics():
    while True:
        global system_stats, iot_devices, last_update
        try:
            cpu_q = prom.custom_query(
                query='100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
            system_stats['cpu_percent'] = round(float(cpu_q[0]['value'][1]), 1) if cpu_q else 0
            system_stats['cpu_temp']    = get_cpu_temp()

            mem_used  = prom.custom_query(query='node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
            mem_total = prom.custom_query(query='node_memory_MemTotal_bytes')
            if mem_used and mem_total:
                system_stats['memory_used_gb']  = round(float(mem_used[0]['value'][1]) / (1024**3), 2)
                system_stats['memory_total_gb'] = round(float(mem_total[0]['value'][1]) / (1024**3), 2)
                system_stats['memory_percent']  = round(
                    system_stats['memory_used_gb'] / system_stats['memory_total_gb'] * 100, 1)

            nvme_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"} - node_filesystem_avail_bytes{mountpoint="/mnt/nvme"}')
            nvme_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"}')
            if nvme_used and nvme_total:
                system_stats['nvme_used_gb']  = round(float(nvme_used[0]['value'][1]) / (1024**3), 1)
                system_stats['nvme_total_gb'] = round(float(nvme_total[0]['value'][1]) / (1024**3), 1)
                system_stats['nvme_percent']  = round(
                    system_stats['nvme_used_gb'] / system_stats['nvme_total_gb'] * 100, 1)
            system_stats['nvme_temp'] = get_nvme_temp()

            hdd_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"} - node_filesystem_avail_bytes{mountpoint="/mnt/hdd-public"}')
            hdd_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"}')
            if hdd_used and hdd_total:
                system_stats['hdd_used_gb']  = round(float(hdd_used[0]['value'][1]) / (1024**3), 1)
                system_stats['hdd_total_gb'] = round(float(hdd_total[0]['value'][1]) / (1024**3), 1)
                system_stats['hdd_percent']  = round(
                    system_stats['hdd_used_gb'] / system_stats['hdd_total_gb'] * 100, 1)
            system_stats['hdd_status'] = get_hdd_status()

            esp32_temps    = prom.custom_query(query='esp32_temperature_celsius')
            esp32_humidity = prom.custom_query(query='esp32_humidity_percent')
            for metric in esp32_temps:
                did = metric['metric']['device_id']
                iot_devices.setdefault(did, {})['temperature'] = round(float(metric['value'][1]), 1)
            for metric in esp32_humidity:
                did = metric['metric']['device_id']
                iot_devices.setdefault(did, {})['humidity'] = round(float(metric['value'][1]), 1)

            last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Metrics error: {e}")
        await asyncio.sleep(5)

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
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body { font-family:'Inter',sans-serif; background:#f8fafc; color:#1e293b; transition:background-color .3s,color .3s; }
            body.body--dark { background:#0f172a; color:#f8fafc; }
            .glass-card { background:rgba(255,255,255,.7); backdrop-filter:blur(12px); border:1px solid rgba(0,0,0,.05); border-radius:16px; box-shadow:0 4px 6px -1px rgba(0,0,0,.05); transition:background-color .3s; }
            body.body--dark .glass-card { background:rgba(30,41,59,.7); border:1px solid rgba(255,255,255,.1); }
            .glass-header { background:rgba(255,255,255,.8); backdrop-filter:blur(8px); border-bottom:1px solid rgba(0,0,0,.05); }
            body.body--dark .glass-header { background:rgba(15,23,42,.8); border-bottom:1px solid rgba(255,255,255,.05); }
            .stat-value { font-family:monospace; font-size:1.5rem; font-weight:700; color:#10b981; }
            .stat-label { font-size:.75rem; color:#94a3b8; text-transform:uppercase; font-weight:600; letter-spacing:.05em; }

            /* Plug page styles */
            .plug-card { background:rgba(30,41,59,.7); border:1px solid rgba(255,255,255,.1); border-radius:16px; overflow:hidden; transition:all .3s; }
            .plug-card.plug-on { border-color:rgba(16,185,129,.4); box-shadow:0 0 24px rgba(16,185,129,.1); }
            .plug-card.server-card { border-color:rgba(248,113,65,.25); }
            .plug-card::before { content:''; display:block; height:3px; background:linear-gradient(90deg,#10b981,#3b82f6); opacity:0; transition:opacity .3s; }
            .plug-card.plug-on::before { opacity:1; }

            .plug-stat-strip { display:flex; flex-wrap:wrap; gap:16px; align-items:center; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.06); border-radius:12px; padding:14px 18px; }
            .plug-stat-num { font-family:'Courier New',monospace; font-size:1.4rem; font-weight:700; line-height:1; }
            .plug-stat-lbl { font-size:.6rem; color:#94a3b8; text-transform:uppercase; letter-spacing:.08em; margin-top:3px; }
            .plug-sep { width:1px; height:36px; background:rgba(255,255,255,.1); }

            .plug-toggle { width:100%; padding:12px 0!important; border-radius:10px!important; font-family:'Courier New',monospace!important; font-size:.82rem!important; letter-spacing:.08em!important; transition:all .2s!important; }
            .plug-toggle-on  { background:#10b981!important; color:#04201a!important; }
            .plug-toggle-off { background:rgba(255,255,255,.06)!important; color:#94a3b8!important; border:1px solid rgba(255,255,255,.1)!important; }
            .plug-toggle-warn { background:#92400e!important; color:#fef3c7!important; }

            .plug-energy-row { display:flex; flex-wrap:wrap; gap:10px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.06); border-radius:12px; padding:14px 18px; }

            .plug-ctrl-btn { background:rgba(255,255,255,.04)!important; border:1px solid rgba(255,255,255,.1)!important; border-radius:9px!important; color:#dde3f0!important; font-family:'Courier New',monospace!important; font-size:.7rem!important; letter-spacing:.05em!important; padding:9px 10px!important; transition:all .2s!important; }
            .plug-ctrl-btn:hover { border-color:#10b981!important; color:#10b981!important; }

            .plug-led-btn { background:rgba(255,255,255,.04)!important; border:1px solid rgba(255,255,255,.1)!important; border-radius:8px!important; color:#94a3b8!important; font-size:.68rem!important; padding:8px 6px!important; transition:all .2s!important; flex:1; min-width:70px; }
            .plug-led-btn:hover { border-color:#f59e0b!important; color:#f59e0b!important; }

            .dot-ok  { width:8px;height:8px;border-radius:50%;background:#10b981;display:inline-block;animation:dotblink 2.4s infinite; }
            .dot-err { width:8px;height:8px;border-radius:50%;background:#ef4444;display:inline-block; }
            @keyframes dotblink { 0%,100%{opacity:1} 50%{opacity:.3} }

            .plug-warn-banner { background:#7c2d12; border:1px solid #f87171; border-radius:10px; padding:12px 16px; margin-top:10px; font-family:monospace; font-size:.72rem; color:#fca5a5; display:none; }
            .plug-warn-banner.visible { display:block; }

            .plug-section-title { font-family:'Courier New',monospace; font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:#94a3b8; margin-bottom:10px; }
            .plug-inner-card { background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.06); border-radius:14px; padding:16px 18px; margin-top:12px; }
        </style>
    ''')

# ─────────────────────────────────────────────────────────────────────────────
#  NAV TOGGLE HELPER
# ─────────────────────────────────────────────────────────────────────────────
def nav_toggle(current: str):
    """Render the 3-tab navigation toggle."""
    def on_change(e):
        if e.value == 'Server':
            ui.navigate.to('/')
        elif e.value == 'Energy':
            ui.navigate.to('/energy')
        elif e.value == 'Plugs':
            ui.navigate.to('/plugs')

    with ui.row().classes('w-full flex justify-center mt-2'):
        ui.toggle(
            ['Server', 'Energy', 'Plugs'], value=current,
            on_change=on_change
        ).props(
            'unelevated text-color=slate-700 dark:text-color=white'
        ).classes(
            'bg-slate-200 dark:bg-slate-800'
        ).style('border-radius: 10px; overflow: hidden;')


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 1 — SERVER  /
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/')
def main_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
              positive='#10b981', warning='#f59e0b')

    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto justify-center sm:justify-start mb-2 sm:mb-0'):
            ui.icon('dashboard', size='md', color='primary')
            ui.label('HOMELAB').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
        
        with ui.row().classes('items-center justify-center sm:justify-end gap-4 z-10 w-full sm:w-auto mb-2 sm:mb-0'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1'):
                ui.icon('schedule', size='xs', color='gray-400')
                ui.label().bind_text_from(globals(), 'last_update').classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 sm:p-6 mt-0 gap-4 sm:gap-8'):
        nav_toggle('Server')

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

        ui.timer(5.0, update_iot_display)

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
#  PAGE 2 — ENERGY  /energy
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/energy')
def energy_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
              positive='#10b981', warning='#f59e0b')

    peak_watt = [0.0]
    selected_device = {'value': 'all'}  # default device for energy view

    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto justify-center sm:justify-start mb-2 sm:mb-0'):
            ui.icon('bolt', size='md', color='warning')
            ui.label('Energy').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            
        with ui.row().classes('items-center justify-center sm:justify-end gap-4 z-10 w-full sm:w-auto mb-2 sm:mb-0'):
            ui.label('TNB Tariff Rate').classes('text-xs text-slate-500 bg-slate-800 px-3 py-1 rounded-full')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 sm:p-6 mt-0 gap-4 sm:gap-6'):
        nav_toggle('Energy')

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
                ).classes('w-full')

        # ── Power history chart ──────────────────────────────────────────────
        with ui.card().classes('glass-card p-4 sm:p-6 w-full'):
            ui.label('Power Usage — Live').classes(
                'text-sm font-bold text-slate-400 uppercase mb-4')
            area_chart = ui.echart({
                'tooltip': {'trigger': 'axis'},
                'legend':  {'data': ['Power (W)'], 'textStyle': {'color': '#94a3b8'}, 'top': 0, 'right': 0},
                'grid':    {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis':   [{'type': 'category', 'boundaryGap': False, 'data': [],
                             'axisLabel': {'color': '#94a3b8', 'rotate': 45}}],
                'yAxis':   [{'type': 'value', 'name': 'Watts',
                             'nameTextStyle': {'color': '#94a3b8'},
                             'axisLabel': {'color': '#94a3b8'}}],
                'series':  [{'name': 'Power (W)', 'type': 'line', 'smooth': True,
                             'areaStyle': {'color': {
                                 'type': 'linear', 'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                 'colorStops': [
                                     {'offset': 0, 'color': 'rgba(59,130,246,.4)'},
                                     {'offset': 1, 'color': 'rgba(59,130,246,.02)'},
                                 ],
                             }},
                             'itemStyle': {'color': '#3b82f6'}, 'data': []}],
            }).classes('w-full h-[300px]')

        def update_energy_stats():
            dk = selected_device['value']

            if dk == 'all':
                pwr_w, today_kwh, cost_rm, month_kwh = 0.0, 0.0, 0.0, 0.0
                with plug_lock:
                    for d_key in ["plug", "server"]:
                        s = plug_state[d_key]["status"]
                        if s: pwr_w += s["watts"]
                        try:
                            today = db.get_today_summary(tuya_local.DEVICES[d_key]["id"])
                            t_kwh = today["total_kwh"]
                            t_cost = today["cost_rm"]
                        except Exception:
                            t_kwh, t_cost = 0, 0
                            
                        today_kwh += t_kwh
                        cost_rm += t_cost
                        month_kwh += t_kwh + (42.5 if d_key == "plug" else 150.2)
                    
                    h1 = list(plug_state["plug"]["history"])
                    h2 = list(plug_state["server"]["history"])
                
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
                
                try:
                    today = db.get_today_summary(tuya_local.DEVICES[dk]["id"])
                    today_kwh = today["total_kwh"]
                    cost_rm   = today["cost_rm"]
                except Exception:
                    today_kwh = 0
                    cost_rm   = 0
                    
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

            # Update chart with history
            area_chart.options['xAxis'][0]['data']  = labels
            area_chart.options['series'][0]['data'] = values
            area_chart.update()

        ui.timer(2.0, update_energy_stats)


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

        def handle_toggle():
            with plug_lock:
                st = plug_state[dev_key]["status"]
            current_on = st["switch"] if st else False

            if not current_on:
                ok_cmd = tuya_local.set_switch(dev_key, True)
                if ok_cmd:
                    db.insert_state_change(dev_id, cfg["name"], True)
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

            ok_cmd = tuya_local.set_switch(dev_key, False)
            if ok_cmd:
                db.insert_state_change(dev_id, cfg["name"], False)
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

    def _exec_cmd(dk, fn, label):
        ok_cmd = fn()
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
#  PAGE 3 — PLUGS  /plugs
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/plugs')
def plugs_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
              positive='#10b981', warning='#f59e0b')

    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto justify-center sm:justify-start mb-2 sm:mb-0'):
            ui.icon('power', size='md', color='positive')
            ui.label('Smart Plugs').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')

        with ui.row().classes('items-center justify-center sm:justify-end gap-4 z-10 w-full sm:w-auto mb-2 sm:mb-0'):
            ui.label('LOCAL LAN · TINYTUYA').classes(
                'text-xs text-slate-500 bg-slate-800 px-3 py-1 rounded-full font-mono')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes(
                'text-slate-900 dark:text-white'
            ).bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 sm:p-6 mt-0 gap-4 sm:gap-6'):
        nav_toggle('Plugs')

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

        # Today's energy from DB
        try:
            today = db.get_today_summary(refs["dev_id"])
            refs["ref_today_kwh"].set_text(f"{today['total_kwh']:.4f}")
            refs["ref_today_rm"].set_text(f"RM {today['cost_rm']:.4f}")
        except Exception:
            pass

        # Chart
        new_opts = _plug_chart_options(dk)
        refs["chart"].options.update(new_opts)
        refs["chart"].update()

    def _refresh_plugs():
        _update_panel(plug_refs)
        _update_panel(server_refs)

    ui.timer(2.0, _refresh_plugs)


# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────────────────────
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))
threading.Thread(target=plug_polling_loop, daemon=True).start()

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard', reload=False, favicon='🏠')
