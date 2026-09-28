"""
views/server_view.py
====================
Server tab — system performance cards, IoT environment, Smart Plug Fleet tiles, and AI analysis.
"""
from datetime import datetime
from nicegui import ui, run

import services.tuya_local as tuya_local
import services.db as db
import models.state as state
from controllers.server_controller import run_deepseek_analysis

# Convenience aliases
system_stats = state.system_stats
iot_devices  = state.iot_devices
plug_state   = state.plug_state
plug_lock    = state.plug_lock

def render_server_content(on_nav_to_plugs=None):
    with ui.column().classes('w-full gap-4 sm:gap-8'):

        # ── 1. System Performance Header & Cards ──────────────────────────────
        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        with ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4'):

            # CPU Card
            with ui.card().classes('glass-card p-5 flex flex-col items-center relative overflow-hidden'):
                ui.label('CPU Load').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('speed', size='sm', color='primary').classes('absolute top-4 right-4 opacity-50')
                with ui.circular_progress(min=0, max=100, show_value=True, size='110px', color='primary').props('thickness=0.1').classes('mt-4') as p:
                    p.bind_value_from(system_stats, 'cpu_percent')
                ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'{x}°C').classes('text-2xl font-bold text-slate-900 dark:text-white mt-4')
                ui.label('Core Temp').classes('text-xs text-slate-500')

            # Memory Card
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

            # NVMe Storage Card
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

            # Mass Storage Card (HDD)
            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MASS STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: str(x).upper()).classes('absolute top-4 right-5 text-lg font-bold text-slate-400 dark:text-slate-300')
                with ui.row().classes('items-end justify-between w-full'):
                    ui.label().bind_text_from(system_stats, 'hdd_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-positive')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'hdd_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=positive track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'hdd_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

        # ── 2. IoT Environment & Smart Plugs ─────────────────────────────────
        with ui.row().classes('items-center justify-between mt-8 mb-3 w-full flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('sensors', color='secondary').classes('text-xl')
                ui.label('IoT Environment & Smart Plugs').classes('text-lg font-bold text-slate-800 dark:text-gray-200')
            if on_nav_to_plugs:
                ui.button('Manage Plugs Fleet →', on_click=on_nav_to_plugs, icon='electrical_services').props('flat rounded dense').classes('text-xs font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 px-3 py-1')

        # Environmental Sensor Cards (ESP32 Multi-room)
        iot_container = ui.row().classes('w-full gap-4 sm:gap-6 grid grid-cols-1 md:grid-cols-3 items-stretch mb-4')

        # Smart Plug Fleet Quick-Control Hub
        with ui.card().classes('glass-card w-full p-4 sm:p-5 relative overflow-hidden'):
            with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('power', color='positive').classes('text-lg')
                    ui.label('Smart Plug Fleet Status').classes('text-sm font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide')
                with ui.row().classes('items-center gap-3 text-xs font-semibold'):
                    server_fleet_watts_label = ui.label('⚡ 0.0 W load').classes('text-amber-500 font-bold')
                    server_fleet_active_label = ui.label('🟢 0/3 Active').classes('text-emerald-500 font-bold')

            iot_plugs_grid = ui.grid().classes('w-full gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3')

        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if iot_devices:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes(
                            'glass-card p-4 hover:scale-[1.02] transition-transform h-full flex flex-col justify-between'
                        ):
                            with ui.row().classes('items-center justify-between w-full mb-2'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('wifi', size='xs').classes('text-slate-400 dark:text-slate-300')
                                    with ui.column().classes('gap-0'):
                                        ui.label(data.get('name', device_id.replace('esp32-', '').title())).classes(
                                            'text-sm font-bold text-slate-700 dark:text-slate-200'
                                        )
                                        ui.label(data.get('zone', 'Homelab')).classes('text-[10px] text-slate-400')
                                ui.badge(data.get('status', 'Optimal'), color='positive').props('dense rounded').classes('text-[9px] font-semibold')
                            ui.separator().classes('bg-slate-300/40 dark:bg-slate-700/40 mb-3')
                            with ui.row().classes('justify-around items-center gap-4 mt-auto'):
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('thermostat', size='xs', color='orange')
                                    ui.label(f"{data.get('temperature', 0)}°C").classes('text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('TEMP').classes('text-[9px] text-slate-400 font-bold')
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('water_drop', size='xs', color='blue')
                                    ui.label(f"{data.get('humidity', 0)}%").classes('text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('HUMIDITY').classes('text-[9px] text-slate-400 font-bold')
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('signal_cellular_alt', size='xs', color='positive')
                                    ui.label(f"{data.get('rssi', -60)}").classes('text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('RSSI dBm').classes('text-[9px] text-slate-400 font-bold')

            # Populate smart plug quick-tiles
            iot_plugs_grid.clear()
            total_w = 0.0
            active_cnt = 0
            with iot_plugs_grid:
                for dev_key, cfg in tuya_local.DEVICES.items():
                    with plug_lock:
                        st = plug_state.get(dev_key, {}).get("status")
                        ok = plug_state.get(dev_key, {}).get("ok", False)
                    is_on = st["switch"] if st else False
                    watts = st["watts"] if st else 0.0
                    if is_on:
                        active_cnt += 1
                        total_w += watts

                    is_crit = cfg.get("is_critical", False) or cfg.get("is_server", False)
                    tile_cls = f"iot-plug-tile {'tile-on' if is_on else ''} {'tile-critical' if is_crit else ''}"
                    with ui.card().classes(tile_cls):
                        with ui.row().classes('items-center justify-between w-full mb-1'):
                            with ui.row().classes('items-center gap-2 overflow-hidden'):
                                ui.icon(cfg.get('icon', 'power'), size='xs').classes(
                                    'text-emerald-500' if is_on else 'text-slate-400'
                                )
                                with ui.column().classes('gap-0 overflow-hidden'):
                                    ui.label(cfg["name"]).classes(
                                        'text-xs font-bold text-slate-800 dark:text-slate-200 truncate'
                                    )
                                    ui.label(cfg.get("zone", "Homelab")).classes('text-[9px] text-slate-400')
                            if is_crit:
                                ui.icon('lock', size='12px').classes('text-rose-500').tooltip('Protected Infrastructure')

                        with ui.row().classes('items-center justify-between w-full mt-2'):
                            ui.label(f"{watts:.1f} W" if is_on else "OFF").classes(
                                f"text-xs font-mono font-bold {'text-emerald-500 dark:text-emerald-400' if is_on else 'text-slate-400'}"
                            )

                            def make_toggle_handler(dk=dev_key, crit=is_crit):
                                async def _toggle():
                                    with plug_lock:
                                        cur_st = plug_state.get(dk, {}).get("status")
                                        cur_on = cur_st["switch"] if cur_st else False
                                    if crit and cur_on:
                                        ui.notify(f"⚠ Protected device ({tuya_local.DEVICES[dk]['name']})! Use Plugs tab for confirmed shutdown.", type='warning')
                                        return
                                    
                                    target_state = not cur_on
                                    ok_cmd = await run.io_bound(tuya_local.set_switch, dk, target_state)
                                    if ok_cmd:
                                        await run.io_bound(
                                            db.insert_state_change,
                                            tuya_local.DEVICES[dk]["id"],
                                            tuya_local.DEVICES[dk]["name"],
                                            target_state
                                        )
                                        with plug_lock:
                                            if plug_state.get(dk, {}).get("status"):
                                                plug_state[dk]["status"]["switch"] = target_state
                                        ui.notify(f"{'🔴 Turned OFF' if cur_on else '✅ Turned ON'} ({tuya_local.DEVICES[dk]['name']})", type='negative' if cur_on else 'positive')
                                        update_iot_display()
                                    else:
                                        ui.notify(f"❌ Failed to switch {tuya_local.DEVICES[dk]['name']}", type='negative')
                                return _toggle

                            ui.button(
                                'ON' if is_on else 'OFF',
                                on_click=make_toggle_handler(dev_key, is_crit)
                            ).props('dense unelevated rounded').classes(
                                f"text-[10px] font-bold px-2 py-0.5 {'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' if is_on else 'bg-slate-200 dark:bg-slate-800 text-slate-500'}"
                            )

            server_fleet_watts_label.set_text(f"⚡ {total_w:.1f} W load")
            server_fleet_active_label.set_text(f"🟢 {active_cnt}/{len(tuya_local.DEVICES)} Active")

        ui.timer(3.0, update_iot_display)

        # ── 3. AI Analysis Card ──────────────────────────────────────────────
        with ui.card().classes(
            'glass-card w-full p-4 sm:p-6 mt-2 sm:mt-4 bg-slate-200/50 dark:bg-slate-800/50 '
            'border-l-4 border-slate-300 dark:border-white'
        ):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    with ui.row().classes('items-center justify-between w-full mb-1'):
                        ui.label('DeepMind System Analysis').classes(
                            'text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest'
                        )
                        async def generate_analysis():
                            state.ai_insights = "⏳ Generating system analysis..."
                            result = await run.io_bound(run_deepseek_analysis)
                            state.ai_insights = f"🕒 {datetime.now().strftime('%H:%M')}\n\n{result}"
                        ui.button('⚡ Generate', on_click=generate_analysis).props('dense flat rounded').classes(
                            'text-xs text-blue-500 dark:text-blue-400 hover:bg-blue-500/10 px-2'
                        )
                    ui.label().bind_text_from(state, 'ai_insights').classes(
                        'text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed'
                    )
