"""
views/server_view.py
====================
Server tab — system performance cards, IoT environment, AI analysis.
"""
from datetime import datetime
from nicegui import ui, run

import tuya_local
import models.state as state
from controllers.server_controller import run_deepseek_analysis

# Convenience aliases so existing code that references these bare names still works
system_stats = state.system_stats
iot_devices  = state.iot_devices
plug_state   = state.plug_state
plug_lock    = state.plug_lock

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
                for dev_key in ("plug", "server", "extension"):
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
            'glass-card w-full p-4 sm:p-6 mt-2 sm:mt-4'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    with ui.row().classes('items-center justify-between w-full mb-1'):
                        ui.label('AI Analysis').classes(
                            'text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest')
                        async def generate_analysis():
                            state.ai_insights = "⏳ Generating analysis..."
                            result = await run.io_bound(run_deepseek_analysis)
                            ai_insights = f"🕒 {datetime.now().strftime('%H:%M')}\n\n{result}"
                        ui.button('⚡ Generate', on_click=generate_analysis).props('dense flat').classes(
                            'text-xs text-blue-500 dark:text-blue-400')
                    ui.label().bind_text_from(state, 'ai_insights').classes(
                        'text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed')

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — ENERGY
# ─────────────────────────────────────────────────────────────────────────────
