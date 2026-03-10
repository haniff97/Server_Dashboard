#!/usr/bin/env python3
"""
Custom Homelab Dashboard - DESIGN MODE
Built with NiceGUI + Mock Data (Simulating Prometheus + Tuya)
"""
import os
import asyncio
import threading
import time
import random
from collections import deque
from typing import Any, Dict, List, Optional
from datetime import datetime

from nicegui import ui, app

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — system
# ─────────────────────────────────────────────────────────────────────────────
system_stats = {
    'cpu_percent': 0, 'cpu_temp': 0,
    'memory_percent': 0, 'memory_used_gb': 0, 'memory_total_gb': 16.0,
    'nvme_percent': 0, 'nvme_used_gb': 0, 'nvme_total_gb': 1000.0, 'nvme_temp': 0,
    'hdd_percent': 0, 'hdd_used_gb': 0, 'hdd_total_gb': 4000.0, 'hdd_status': 'idle',
}
iot_devices: dict = {}
ai_insights = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update = ""

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — Tuya plug (MOCKED)
# ─────────────────────────────────────────────────────────────────────────────
tuya_status: Dict[str, Any] = {
    "switch_1": True,
    "cur_power": 1250,
    "cur_voltage": 2300,
    "cur_current": 543,
    "add_ele": 1450
}
tuya_poll_ok: bool = True
tuya_lock = threading.Lock()
plug_data: deque = deque([0.0] * 24, maxlen=24)

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM HELPERS (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
def get_cpu_temp():
    return round(random.uniform(40.0, 65.0), 1)

def get_nvme_temp():
    return round(random.uniform(30.0, 50.0), 1)

def get_hdd_status():
    return 'active' if random.random() > 0.7 else 'idle'

# ─────────────────────────────────────────────────────────────────────────────
#  TUYA POLLING THREAD (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
def tuya_polling_loop():
    global tuya_status, tuya_poll_ok
    while True:
        with tuya_lock:
            if tuya_status.get("switch_1", False):
                tuya_status["cur_power"] = int(random.uniform(115.0, 135.0) * 10)
                tuya_status["cur_current"] = int((tuya_status["cur_power"] / 10 / 230.0) * 1000)
                tuya_status["cur_voltage"] = int(random.uniform(228.0, 232.0) * 10)
                tuya_status["add_ele"] += 1
            else:
                tuya_status["cur_power"] = 0
                tuya_status["cur_current"] = 0
                tuya_status["cur_voltage"] = int(random.uniform(228.0, 232.0) * 10)
            
            tuya_poll_ok = random.random() > 0.05
            plug_data.append(round(tuya_status.get("cur_power", 0) / 10.0 / 1000.0, 3))
        time.sleep(2)

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM METRICS ASYNC LOOP (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
async def update_metrics():
    while True:
        global system_stats, iot_devices, last_update
        try:
            system_stats['cpu_percent'] = round(random.uniform(10.0, 80.0), 1)
            system_stats['cpu_temp']    = get_cpu_temp()

            system_stats['memory_used_gb']  = round(random.uniform(4.0, 12.0), 2)
            system_stats['memory_percent']  = round(system_stats['memory_used_gb'] / system_stats['memory_total_gb'] * 100, 1)

            system_stats['nvme_used_gb']  = round(random.uniform(200.0, 800.0), 1)
            system_stats['nvme_percent']  = round(system_stats['nvme_used_gb'] / system_stats['nvme_total_gb'] * 100, 1)
            system_stats['nvme_temp'] = get_nvme_temp()

            system_stats['hdd_used_gb']  = round(random.uniform(1000.0, 3500.0), 1)
            system_stats['hdd_percent']  = round(system_stats['hdd_used_gb'] / system_stats['hdd_total_gb'] * 100, 1)
            system_stats['hdd_status'] = get_hdd_status()

            # Mock ESP32 IoT device
            iot_devices['esp32-main-room'] = {
                'temperature': round(random.uniform(22.0, 26.0), 1),
                'humidity': round(random.uniform(45.0, 60.0), 1)
            }

            last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Metrics error: {e}")
        await asyncio.sleep(2)

# ─────────────────────────────────────────────────────────────────────────────
#  AI INSIGHTS ASYNC LOOP (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
async def update_ai_insights():
    global ai_insights
    while True:
        try:
            await asyncio.sleep(5)
            if random.random() > 0.7:
                ai_insights = "Concerns Detected (MOCK):\nHigh CPU usage detected\n\nRecommendation: Check active processes\nTuya plug power draw is normal."
            else:
                ai_insights = "All systems healthy (MOCK)\nPerformance: Optimal\nNo immediate concerns"
        except Exception as e:
            ai_insights = f"❌ AI Mock Error: {e}"
        await asyncio.sleep(15)

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

    # ── Main content ──────────────────────────────────────────────────────
    with ui.column().classes('w-full max-w-7xl mx-auto p-6 mt-0 gap-8'):
        with ui.row().classes('w-full flex justify-center mt-2'):
            ui.toggle(['Server', 'Energy'], value='Server', on_change=lambda e: ui.navigate.to('/energy') if e.value == 'Energy' else None).props('unelevated text-color=slate-700 dark:text-color=white').classes('bg-slate-200 dark:bg-slate-800').style('border-radius: 10px; overflow: hidden;')

        # System Performance title
        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        # Metrics grid
        with ui.grid().classes('w-full gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4 items-start'):

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
            'w-full gap-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 items-stretch')
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
                            tuya_status["switch_1"] = new_state
                        ui.notify(
                            f"{'✅ Plug ON' if new_state else '🔴 Plug OFF'} (Mock)",
                            type="positive" if new_state else "negative")

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
            'glass-card w-full p-6 mt-4 bg-slate-200/50 dark:bg-slate-800/50 '
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
    timeframe = {'value': 'Daily'}

    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto justify-center sm:justify-start mb-2 sm:mb-0'):
            ui.icon('bolt', size='md', color='warning')
            ui.label('Energy').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            
        with ui.row().classes('items-center justify-center sm:justify-end gap-4 z-10 w-full sm:w-auto mb-2 sm:mb-0'):
            ui.label('TNB Tariff Rate').classes('text-xs text-slate-500 bg-slate-800 px-3 py-1 rounded-full')
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

                ui.toggle(['Daily', 'Weekly', 'Monthly'], value='Daily',
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

        def _mock_query_prom_range(duration: str):
            """Mock Prometheus historical data for testing charts dynamically!"""
            if duration == 'Daily':
                return hours, list(plug_data)
            elif duration == 'Weekly':
                return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], [random.uniform(2.0,5.0) for _ in range(7)]
            else:  # Monthly
                return [f"Day {i+1}" for i in range(30)], [random.uniform(1.5,4.5) for _ in range(30)]

        def refresh_charts():
            tf = timeframe['value']
            labels, data = _mock_query_prom_range(tf)

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

# Tuya runs in a background thread
threading.Thread(target=tuya_polling_loop, daemon=True).start()

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard Design', reload=False, favicon='🏠')