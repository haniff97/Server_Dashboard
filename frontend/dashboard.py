#!/usr/bin/env python3
"""
Homelab Dashboard
Built with NiceGUI + Prometheus + Tuya Smart Plug
Pages: / (Server) | /energy (Energy Monitor)
"""
import os
import asyncio
import hashlib
import hmac
import json
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

import requests
from nicegui import ui, app
from prometheus_api_client import PrometheusConnect
from prometheus_client import Gauge, start_http_server

# ─────────────────────────────────────────────────────────────────────────────
#  PROMETHEUS
# ─────────────────────────────────────────────────────────────────────────────
prom = PrometheusConnect(url="http://localhost:9090", disable_ssl=True)

# ─────────────────────────────────────────────────────────────────────────────
#  TUYA CREDENTIALS  — loaded from .env via PM2
# ─────────────────────────────────────────────────────────────────────────────

env_path = "/mnt/nvme/Projects/dashboard/.env" 
load_dotenv(env_path)

TUYA_CLIENT_ID     = os.getenv("TUYA_CLIENT_ID", "").strip().strip('"').strip("'")
TUYA_CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET", "").strip().strip('"').strip("'")
TUYA_DEVICE_ID     = os.getenv("TUYA_DEVICE_ID", "").strip().strip('"').strip("'")
TUYA_REGION        = os.getenv("TUYA_REGION", "sg").strip().strip('"').strip("'")
TUYA_BASE_URL      = f"https://openapi-{TUYA_REGION}.iotbing.com"
TUYA_POLL_INTERVAL = 30

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
#  GLOBAL STATE — Tuya plug
# ─────────────────────────────────────────────────────────────────────────────
tuya_status: Dict[str, Any] = {
    "switch_1":    False,
    "cur_power":   0,
    "cur_voltage": 0,
    "cur_current": 0,
    "add_ele":     0,
}
tuya_poll_ok: bool        = False
tuya_lock                 = threading.Lock()
tuya_token: Optional[str] = None
tuya_token_expiry: float  = 0
plug_data: deque          = deque([0.0] * 24, maxlen=24)

# ─────────────────────────────────────────────────────────────────────────────
#  PROMETHEUS EXPORTER — exposes plug metrics on :2000 for scraping
# ─────────────────────────────────────────────────────────────────────────────
prom_power   = Gauge('tuya_plug_power_watts',   'Smart plug power draw in watts')
prom_voltage = Gauge('tuya_plug_voltage_volts', 'Smart plug voltage in volts')
prom_current = Gauge('tuya_plug_current_amps',  'Smart plug current in amps')
prom_energy  = Gauge('tuya_plug_energy_kwh',    'Smart plug accumulated energy today in kWh')
prom_switch  = Gauge('tuya_plug_switch',        'Smart plug on/off state (1=on, 0=off)')
start_http_server(2000)

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
#  TUYA SIGNING  — proven working format
# ─────────────────────────────────────────────────────────────────────────────
def _tuya_sign(method: str, path: str,
               query: str = "",
               body: bytes = b"",
               use_token: bool = True) -> tuple:
    t         = str(int(time.time() * 1000))
    nonce     = ""
    body_hash = hashlib.sha256(body).hexdigest()
    full_path = path + ("?" + query if query else "")
    string_to_sign = method.upper() + "\n" + body_hash + "\n\n" + full_path
    token_part     = tuya_token if (use_token and tuya_token) else ""
    str_to_sign    = TUYA_CLIENT_ID + token_part + t + nonce + string_to_sign
    sign = hmac.new(
        TUYA_CLIENT_SECRET.encode(),
        str_to_sign.encode(),
        hashlib.sha256
    ).hexdigest().upper()
    return t, sign, nonce


def _tuya_refresh_token() -> bool:
    global tuya_token, tuya_token_expiry
    if not TUYA_CLIENT_ID or not TUYA_CLIENT_SECRET:
        print("⚠ Tuya credentials missing in .env — skipping token refresh")
        return False
    t, sign, nonce = _tuya_sign("GET", "/v1.0/token",
                                query="grant_type=1", use_token=False)
    headers = {
        "client_id":   TUYA_CLIENT_ID,
        "sign_method": "HMAC-SHA256",
        "t":           t,
        "nonce":       nonce,
        "sign":        sign,
    }
    try:
        r    = requests.get(f"{TUYA_BASE_URL}/v1.0/token?grant_type=1",
                            headers=headers, timeout=10)
        data = r.json()
        if data.get("success"):
            res               = data["result"]
            tuya_token        = res["access_token"]
            tuya_token_expiry = time.time() + res.get("expire_time", 7200) - 300
            print(f"[{datetime.now():%H:%M:%S}] Tuya token refreshed ✅")
            return True
        print(f"Token error: {data}")
    except Exception as e:
        print(f"Tuya token refresh failed: {e}")
    return False


def _tuya_ensure_token() -> bool:
    if not tuya_token or time.time() > tuya_token_expiry:
        return _tuya_refresh_token()
    return True


def _tuya_request(method: str, path: str,
                  query: str = "",
                  json_body: dict = None) -> Optional[Any]:
    if not _tuya_ensure_token():
        return None
    body_bytes = b""
    if json_body:
        body_bytes = json.dumps(json_body, separators=(",", ":"),
                                sort_keys=True).encode()
    t, sign, nonce = _tuya_sign(method, path, query=query,
                                body=body_bytes, use_token=True)
    headers = {
        "client_id":    TUYA_CLIENT_ID,
        "access_token": tuya_token,
        "sign_method":  "HMAC-SHA256",
        "t":            t,
        "nonce":        nonce,
        "sign":         sign,
        "Content-Type": "application/json",
    }
    url = f"{TUYA_BASE_URL}{path}" + (("?" + query) if query else "")
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        else:
            r = requests.post(url, headers=headers,
                              data=body_bytes, timeout=10)
        data = r.json()
        if data.get("success"):
            return data.get("result")
        print(f"Tuya API error {path}: {data}")
    except Exception as e:
        print(f"Tuya request failed {path}: {e}")
    return None


def tuya_get_status() -> Optional[Dict]:
    result = _tuya_request("GET",
                           f"/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status")
    if result:
        return {item["code"]: item["value"] for item in result}
    return None


def tuya_send_command(commands: List[dict]) -> bool:
    body = {"commands": commands}
    result = _tuya_request("POST",
                           f"/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/commands",
                           json_body=body)
    return result is not None

# ─────────────────────────────────────────────────────────────────────────────
#  TUYA POLLING THREAD
# ─────────────────────────────────────────────────────────────────────────────
def tuya_polling_loop():
    global tuya_status, tuya_poll_ok
    _tuya_refresh_token()
    while True:
        status = tuya_get_status()
        with tuya_lock:
            if status:
                tuya_status  = status
                tuya_poll_ok = True
                pwr_kw = round(status.get("cur_power", 0) / 10.0 / 1000.0, 3)
                plug_data.append(pwr_kw)
                # Push to Prometheus
                prom_power.set(status.get("cur_power",   0) / 10.0)
                prom_voltage.set(status.get("cur_voltage", 0) / 10.0)
                prom_current.set(status.get("cur_current", 0) / 1000.0)
                prom_energy.set(status.get("add_ele",      0) / 1000.0)
                prom_switch.set(1 if status.get("switch_1", False) else 0)
            else:
                tuya_poll_ok = False
        time.sleep(TUYA_POLL_INTERVAL)

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
            .tuya-card { position:relative; overflow:hidden; }
            .tuya-card.plug-on { border-color:rgba(16,185,129,.5)!important; box-shadow:0 0 24px rgba(16,185,129,.12); }
            .tuya-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,#10b981,#3b82f6); opacity:0; transition:opacity .3s; }
            .tuya-card.plug-on::before { opacity:1; }
            .plug-stat { background:rgba(0,0,0,.04); border-radius:8px; padding:6px 8px; text-align:center; flex:1; }
            body.body--dark .plug-stat { background:rgba(255,255,255,.06); }
            .plug-toggle-on  { background:#10b981!important; color:white!important; border-radius:8px!important; font-size:.75rem!important; }
            .plug-toggle-off { background:rgba(0,0,0,.06)!important; color:#94a3b8!important; border-radius:8px!important; font-size:.75rem!important; }
            body.body--dark .plug-toggle-off { background:rgba(255,255,255,.08)!important; }
            .conn-dot-ok  { width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block;animation:blink 2s infinite; }
            .conn-dot-err { width:7px;height:7px;border-radius:50%;background:#ef4444;display:inline-block; }
            @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
            .stat-value { font-family:monospace; font-size:1.5rem; font-weight:700; color:#10b981; }
            .stat-label { font-size:.75rem; color:#94a3b8; text-transform:uppercase; font-weight:600; letter-spacing:.05em; }
        </style>
    ''')

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
        with ui.row().classes('w-full flex justify-center mt-2'):
            ui.toggle(['Server', 'Energy'], value='Server', on_change=lambda e: ui.navigate.to('/energy') if e.value == 'Energy' else None).props('unelevated text-color=slate-700 dark:text-color=white').classes('bg-slate-200 dark:bg-slate-800').style('border-radius: 10px; overflow: hidden;')

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
        tuya_refs: dict = {}

        def update_iot_display():
            iot_container.clear()
            tuya_refs.clear()
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

                with tuya_lock:
                    s  = dict(tuya_status)
                    ok = tuya_poll_ok
                on = s.get("switch_1", False)

                with ui.element("div").classes(
                    f"tuya-card glass-card p-4 min-w-[200px] h-full flex flex-col "
                    f"justify-between hover:scale-105 transition-transform {'plug-on' if on else ''}"
                ) as card:
                    tuya_refs["card"] = card
                    with ui.row().classes("items-center justify-between mb-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("power", size="xs", color="positive" if on else "grey")
                            with ui.column().classes("gap-0"):
                                ui.label("Smart Plug").classes(
                                    "text-sm font-bold text-slate-700 dark:text-slate-200")
                                tuya_refs["status_lbl"] = ui.label("ON" if on else "OFF").classes(
                                    f"text-[10px] uppercase tracking-wide font-semibold "
                                    f"{'text-positive' if on else 'text-slate-400'}")
                        tuya_refs["dot"] = ui.element("span").classes(
                            "conn-dot-ok" if ok else "conn-dot-err")

                    ui.separator().classes("bg-slate-300/50 dark:bg-slate-700/50 mb-3")

                    with ui.row().classes("gap-2 mb-3"):
                        for ref_key, label, color, val_key, scale, fmt in [
                            ("power",   "W", "#f59e0b", "cur_power",   10.0,   ".1f"),
                            ("voltage", "V", "#8b5cf6", "cur_voltage", 10.0,   ".1f"),
                            ("current", "A", "#3b82f6", "cur_current", 1000.0, ".3f"),
                        ]:
                            val = s.get(val_key, 0) / scale
                            with ui.element("div").classes("plug-stat"):
                                tuya_refs[ref_key] = ui.label(f"{val:{fmt}}").style(
                                    f"font-size:.9rem;font-weight:700;color:{color};"
                                    f"font-family:monospace;line-height:1")
                                ui.label(label).style(
                                    "font-size:.6rem;color:#94a3b8;"
                                    "text-transform:uppercase;margin-top:2px")

                    en = s.get("add_ele", 0) / 1000.0
                    with ui.element("div").classes("plug-stat mb-3"):
                        tuya_refs["energy"] = ui.label(f"{en:.3f}").style(
                            "font-size:.85rem;font-weight:700;color:#10b981;"
                            "font-family:monospace;line-height:1")
                        ui.label("kWh Today").style(
                            "font-size:.6rem;color:#94a3b8;"
                            "text-transform:uppercase;margin-top:2px")

                    def _do_toggle():
                        with tuya_lock:
                            current = tuya_status.get("switch_1", False)
                        new_state = not current
                        ok_cmd = tuya_send_command([{"code": "switch_1", "value": new_state}])
                        if ok_cmd:
                            with tuya_lock:
                                tuya_status["switch_1"] = new_state
                            ui.notify(
                                f"{'✅ Plug ON' if new_state else '🔴 Plug OFF'}",
                                type="positive" if new_state else "negative")
                        else:
                            ui.notify("⚠ Command failed — check logs", type="warning")

                    tuya_refs["toggle"] = ui.button(
                        "● ON" if on else "○ OFF", on_click=_do_toggle
                    ).classes(f"{'plug-toggle-on' if on else 'plug-toggle-off'} w-full").props("dense")

        ui.timer(2.0, update_iot_display)

        def _update_tuya_labels():
            if not tuya_refs:
                return
            with tuya_lock:
                s  = dict(tuya_status)
                ok = tuya_poll_ok
            on = s.get("switch_1", False)
            try:
                tuya_refs["power"].set_text(f"{s.get('cur_power',0)/10:.1f}")
                tuya_refs["voltage"].set_text(f"{s.get('cur_voltage',0)/10:.1f}")
                tuya_refs["current"].set_text(f"{s.get('cur_current',0)/1000:.3f}")
                tuya_refs["energy"].set_text(f"{s.get('add_ele',0)/1000:.3f}")
                tuya_refs["status_lbl"].set_text("ON" if on else "OFF")
                tuya_refs["toggle"].set_text("● ON" if on else "○ OFF")
                tuya_refs["toggle"].classes(
                    remove="plug-toggle-on plug-toggle-off"
                ).classes("plug-toggle-on" if on else "plug-toggle-off")
                tuya_refs["dot"].classes(
                    remove="conn-dot-ok conn-dot-err"
                ).classes("conn-dot-ok" if ok else "conn-dot-err")
            except Exception:
                pass

        ui.timer(1.0, _update_tuya_labels)

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

    hours     = [f"{str(i).zfill(2)}:00" for i in range(24)]
    peak_watt = [0.0]
    timeframe = {'value': 'Live'}

    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto justify-center sm:justify-start mb-2 sm:mb-0'):
            ui.icon('bolt', size='md', color='warning')
            ui.label('Energy').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            
        with ui.row().classes('items-center justify-center sm:justify-end gap-4 z-10 w-full sm:w-auto mb-2 sm:mb-0'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1'):
                ui.icon('schedule', size='xs', color='gray-400')
                rt_clock = ui.label().classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
                ui.timer(1.0, lambda: rt_clock.set_text(datetime.now().strftime("%H:%M:%S")))
            ui.label('TNB Tariff Rate').classes('text-xs text-slate-500 bg-slate-800 px-3 py-1 rounded-full text-white')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 sm:p-6 mt-0 gap-4 sm:gap-6'):
        with ui.row().classes('w-full flex justify-center mt-2 mb-2'):
            ui.toggle(['Server', 'Energy'], value='Energy', on_change=lambda e: ui.navigate.to('/') if e.value == 'Server' else None).props('unelevated text-color=slate-700 dark:text-color=white').classes('bg-slate-200 dark:bg-slate-800').style('border-radius: 5px; overflow: hidden;')

        with ui.row().classes('w-full gap-4 sm:gap-6 items-stretch flex-col lg:flex-row'):

            with ui.card().classes('glass-card p-4 sm:p-6 flex flex-col items-center justify-center flex-1 w-full'):
                ui.label('Current Power Draw').classes('text-sm font-bold text-slate-400 mb-2 uppercase')
                gauge = ui.echart({
                    'series': [{
                        'type': 'gauge', 'startAngle': 180, 'endAngle': 0,
                        'min': 0, 'max': 5, 'splitNumber': 5,
                        'radius': '100%', 'center': ['50%', '80%'],
                        'axisLine': {'lineStyle': {'width': 20, 'color': [[1, 'rgba(255,255,255,0.1)']]}},
                        'progress': {'show': True, 'width': 20, 'itemStyle': {'color': 'auto'}},
                        'pointer':   {'show': False},
                        'axisTick':  {'show': False},
                        'splitLine': {'show': False},
                        'axisLabel': {'show': False},
                        'title':     {'show': False},
                        'detail': {
                            'valueAnimation': True,
                            'formatter': '{value} kW',
                            'color': 'white', 'fontSize': 32, 'fontWeight': 'bold',
                            'offsetCenter': [0, '-20%'],
                        },
                        'data': [{'value': 0}],
                    }]
                }).classes('w-full h-[200px]')

            with ui.column().classes('flex flex-col gap-4 flex-1 justify-center w-full'):

                with ui.card().classes('glass-card p-4 w-full flex flex-row items-center justify-between'):
                    with ui.column():
                        ui.label('TOTAL KWH TODAY').classes('stat-label')
                        ui.label('Accumulated energy since midnight').classes('text-[10px] text-slate-500')
                    with ui.row().classes('items-baseline gap-1'):
                        total_kwh_label = ui.label('0.000').classes('stat-value')
                        ui.label('kWh').classes('text-xs text-slate-400 font-bold')

                with ui.card().classes('glass-card p-4 w-full flex flex-row items-center justify-between'):
                    with ui.column():
                        ui.label('PEAK USAGE').classes('stat-label')
                        ui.label('Highest spike this session').classes('text-[10px] text-slate-500')
                    with ui.row().classes('items-baseline gap-1'):
                        peak_usage_label = ui.label('0.000').classes('stat-value text-warning')
                        ui.label('kW').classes('text-xs text-slate-400 font-bold')

                with ui.card().classes('glass-card p-4 w-full flex flex-row items-center justify-between'):
                    with ui.column():
                        ui.label('EST. TODAY COST').classes('stat-label')
                        ui.label('July 2025 TNB Tariff (est. share)').classes('text-[10px] text-slate-500')
                    with ui.row().classes('items-baseline gap-1'):
                        ui.label('RM').classes('text-xs text-slate-400 font-bold')
                        cost_label = ui.label('0.0000').classes('stat-value text-accent')

            with ui.card().classes('glass-card p-4 sm:p-6 flex flex-col gap-4 w-full lg:w-[300px]'):
                ui.label('Controls').classes('text-sm font-bold text-slate-400 uppercase')

                ui.select(['All Devices', 'Smart Plug'], value='All Devices',
                          label='Device Selector').classes('w-full')

                def change_timeframe(e):
                    timeframe['value'] = e.value
                    refresh_charts()

                ui.toggle(['Live', 'Daily', 'Weekly', 'Monthly'], value='Live',
                          on_change=change_timeframe).classes('w-full')

        with ui.card().classes('glass-card p-4 sm:p-6 w-full'):
            ui.label('Power Usage — Smart Plug').classes(
                'text-sm font-bold text-slate-400 uppercase mb-4')
            area_chart = ui.echart({
                'tooltip': {'trigger': 'axis'},
                'legend':  {'data': ['Smart Plug'], 'textStyle': {'color': '#94a3b8'}, 'top': 0, 'right': 0},
                'grid':    {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis':   [{'type': 'category', 'boundaryGap': False, 'data': hours,
                             'axisLabel': {'color': '#94a3b8', 'rotate': 45}}],
                'yAxis':   [{'type': 'value', 'name': 'Power (kW)',
                             'nameTextStyle': {'color': '#94a3b8'},
                             'axisLabel': {'color': '#94a3b8'}}],
                'series':  [{'name': 'Smart Plug', 'type': 'line', 'stack': 'Total',
                             'areaStyle': {}, 'emphasis': {'focus': 'series'},
                             'itemStyle': {'color': '#3b82f6'}, 'data': list(plug_data)}],
            }).classes('w-full h-[300px]')

        with ui.card().classes('glass-card p-4 sm:p-6 w-full'):
            ui.label('Power Draw Trends').classes(
                'text-sm font-bold text-slate-400 uppercase mb-4')
            line_chart = ui.echart({
                'tooltip': {'trigger': 'axis'},
                'legend':  {'data': ['Smart Plug'], 'textStyle': {'color': '#94a3b8'}, 'top': 0, 'right': 0},
                'grid':    {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis':   {'type': 'category', 'boundaryGap': False, 'data': hours,
                            'axisLabel': {'color': '#94a3b8', 'rotate': 45}},
                'yAxis':   {'type': 'value', 'name': 'Power (kW)',
                            'nameTextStyle': {'color': '#94a3b8'},
                            'axisLabel': {'color': '#94a3b8'}},
                'series':  [{'name': 'Smart Plug', 'type': 'line', 'smooth': True,
                             'itemStyle': {'color': '#3b82f6'}, 'data': list(plug_data)}],
            }).classes('w-full h-[350px]')

        def _query_prom_range(duration: str):
            """Query Prometheus for historical tuya_plug_power_watts data.
               Returns (labels, values) lists ready for the charts."""
            try:
                end = int(time.time())
                if duration == 'Daily':
                    start  = end - 86400
                    step_s = 1800          # 30-min buckets → up to 48 points
                elif duration == 'Weekly':
                    start  = end - 7 * 86400
                    step_s = 3600 * 3      # 3-hour buckets → up to 56 points
                else:  # Monthly
                    start  = end - 30 * 86400
                    step_s = 86400         # daily buckets → up to 30 points

                result = prom.custom_query_range(
                    query='tuya_plug_power_watts',
                    start_time=datetime.fromtimestamp(start),
                    end_time=datetime.fromtimestamp(end),
                    step=str(step_s),
                )
                if not result:
                    return [], []
                values = result[0]['values']
                if duration == 'Daily':
                    labels = [datetime.fromtimestamp(float(v[0])).strftime('%H:%M') for v in values]
                elif duration == 'Weekly':
                    labels = [datetime.fromtimestamp(float(v[0])).strftime('%a %H:%M') for v in values]
                else:
                    labels = [datetime.fromtimestamp(float(v[0])).strftime('%b %d') for v in values]
                data = [round(float(v[1]), 3) for v in values]
                return labels, data
            except Exception as e:
                print(f"Prometheus range query failed: {e}")
                return [], []

        def refresh_charts():
            tf = timeframe['value']
            if tf == 'Live':
                now = datetime.now()
                labels = [(now - timedelta(seconds=(23 - i) * 30)).strftime('%H:%M:%S') for i in range(24)]
                data = list(plug_data)
            else:
                labels, data = _query_prom_range(tf)
                if not data:
                    # Fallback to live deque while history is still building up
                    if tf == 'Daily':
                        labels, data = hours, list(plug_data)
                    elif tf == 'Weekly':
                        labels, data = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], [0.0] * 7
                    else:
                        labels, data = [f"Day {i+1}" for i in range(30)], [0.0] * 30

            area_chart.options['xAxis'][0]['data']  = labels
            area_chart.options['series'][0]['data'] = data
            area_chart.update()
            line_chart.options['xAxis']['data']     = labels
            line_chart.options['series'][0]['data'] = data
            line_chart.update()

        def calculate_tnb_bill(cumulative_monthly_kwh):
            if cumulative_monthly_kwh <= 0:
                return 0.0
            if cumulative_monthly_kwh <= 1500:
                base_cost = cumulative_monthly_kwh * 0.4443
            else:
                base_cost = (1500 * 0.4443) + ((cumulative_monthly_kwh - 1500) * 0.5443)
            rebate_tiers = [
                (200, 0.250), (250, 0.245), (300, 0.225), (350, 0.210),
                (400, 0.170), (450, 0.145), (500, 0.120), (550, 0.105),
                (600, 0.090), (650, 0.075), (700, 0.055), (750, 0.045),
                (800, 0.040), (850, 0.025), (900, 0.010), (1000, 0.005)
            ]
            total_rebate      = 0.0
            kwh_accounted_for = 0
            for tier_max, rebate_rate in rebate_tiers:
                if cumulative_monthly_kwh > kwh_accounted_for:
                    kwh_in_this_tier  = min(cumulative_monthly_kwh, tier_max) - kwh_accounted_for
                    total_rebate     += kwh_in_this_tier * rebate_rate
                    kwh_accounted_for = tier_max
                else:
                    break
            retail_charge = 10.00 if cumulative_monthly_kwh > 600 else 0.0
            return base_cost - total_rebate + retail_charge

        def update_energy_stats():
            with tuya_lock:
                pwr_raw   = tuya_status.get('cur_power', 0)
                today_raw = tuya_status.get('add_ele',   0)

            pwr_kw    = pwr_raw   / 10.0 / 1000.0
            today_kwh = today_raw / 1000.0

            total_month_kwh  = today_kwh * 30.0
            total_month_cost = calculate_tnb_bill(total_month_kwh)
            cost_before      = calculate_tnb_bill(max(0, total_month_kwh - today_kwh))
            cost             = total_month_cost - cost_before

            try:
                gauge.options['series'][0]['progress']['itemStyle']['color'] = (
                    '#3b82f6' if pwr_kw < 1.5 else '#10b981' if pwr_kw < 3.5 else '#ef4444')
                gauge.options['series'][0]['detail']['color'] = 'white' if dark_mode.value else '#0f172a'
                gauge.options['series'][0]['axisLine']['lineStyle']['color'] = [
                    [1, 'rgba(255,255,255,0.1)' if dark_mode.value else 'rgba(0,0,0,0.1)']]
            except (KeyError, TypeError):
                pass
            gauge.options['series'][0]['data'][0]['value'] = round(pwr_kw, 3)
            gauge.update()
            total_kwh_label.set_text(f"{today_kwh:.3f}")
            cost_label.set_text(f"{cost:.4f}")

            if pwr_kw > peak_watt[0]:
                peak_watt[0] = pwr_kw
                peak_usage_label.set_text(f"{pwr_kw:.3f}")

            refresh_charts()

        ui.timer(2.0, update_energy_stats)

# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────────────────────
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))
threading.Thread(target=tuya_polling_loop, daemon=True).start()

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard', reload=False, favicon='🏠')