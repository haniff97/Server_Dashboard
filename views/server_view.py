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
    with ui.column().classes('w-full gap-4 sm:gap-6'):

        # ── 1. System Resource Grid ────────────────────────────────────────────
        with ui.grid().classes('glass-card resource-grid w-full'):
            for key, name, icon in [
                ('cpu',    'Processor',    'memory'),
                ('memory', 'Memory',       'developer_board'),
                ('nvme',   'NVMe storage', 'storage'),
                ('hdd',    'Mass storage', 'dns'),
            ]:
                extra_cls = 'resource-cpu' if key == 'cpu' else ''
                with ui.column().classes(f'resource-cell {extra_cls}'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label(name).classes('metric-heading')
                        ui.icon(icon, size='18px').classes('metric-icon')

                    if key == 'cpu':
                        with ui.element('div').classes('cpu-dial'):
                            ui.circular_progress(
                                min=0, max=100, show_value=False, size='112px', color='primary'
                            ).bind_value_from(system_stats, 'cpu_percent').props('thickness=0.09')
                            ui.label().bind_text_from(
                                system_stats, 'cpu_percent', backward=lambda x: f'{x:.1f}%'
                            ).classes('dial-value')
                        ui.label().bind_text_from(
                            system_stats, 'cpu_temp',
                            backward=lambda x: f'Core temperature  ·  {x:.1f}°C'
                        ).classes('metric-caption')
                    else:
                        with ui.column().classes('gap-1 metric-reading'):
                            ui.label().bind_text_from(
                                system_stats, f'{key}_percent',
                                backward=lambda x: f'{x:.1f}%'
                            ).classes('metric-number')
                            ui.label('Capacity used').classes('metric-caption')
                        ui.linear_progress(show_value=False).bind_value_from(
                            system_stats, f'{key}_percent', backward=lambda x: x / 100
                        ).props('color=primary').classes('metric-bar')
                        with ui.row().classes('w-full justify-between items-center gap-1'):
                            ui.label().bind_text_from(
                                system_stats, f'{key}_used_gb', backward=lambda x: f'{x:.1f} GB'
                            ).classes('metric-caption')
                            ui.label().bind_text_from(
                                system_stats, f'{key}_total_gb', backward=lambda x: f'of {x:g} GB'
                            ).classes('metric-caption')
                        if key == 'nvme':
                            ui.label().bind_text_from(
                                system_stats, 'nvme_temp',
                                backward=lambda x: f'Drive temperature  ·  {x:.1f}°C'
                            ).classes('metric-footnote')
                        elif key == 'hdd':
                            ui.label().bind_text_from(
                                system_stats, 'hdd_status',
                                backward=lambda x: f'Drive state  ·  {x.title()}'
                            ).classes('metric-footnote')
                        else:
                            ui.label('System memory').classes('metric-footnote')

        # ── 2. IoT Environment & Smart Plugs ──────────────────────────────────
        with ui.row().classes('items-center justify-between mt-2 mb-1 w-full flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('sensors', color='secondary').classes('text-xl')
                ui.label('Environment').classes('text-lg font-bold text-slate-800 dark:text-gray-200')
            if on_nav_to_plugs:
                ui.button('Manage Plugs Fleet →', on_click=on_nav_to_plugs, icon='electrical_services').props(
                    'flat rounded dense'
                ).classes('text-xs font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 px-3 py-1')

        # Environmental Sensor Cards (ESP32 Multi-room)
        iot_container = ui.row().classes('sensor-grid w-full gap-4 grid grid-cols-1 md:grid-cols-3 items-stretch')

        # Smart Plug Fleet Quick-Control Hub
        with ui.card().classes('glass-card fleet-overview w-full relative overflow-hidden'):
            with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('power', color='positive').classes('text-lg')
                    ui.label('Connected devices').classes('text-sm font-semibold text-slate-700 dark:text-slate-300')
                with ui.row().classes('items-center gap-3 text-xs font-semibold'):
                    server_fleet_watts_label = ui.label('0.0 W total').classes('text-amber-500 font-bold')
                    server_fleet_active_label = ui.label('0/3 powered on').classes('text-emerald-500 font-bold')

            iot_plugs_grid = ui.grid().classes('quick-device-grid w-full')

        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if iot_devices:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes('glass-card sensor-card flex flex-col justify-between'):
                            with ui.row().classes('items-center justify-between w-full'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('wifi', size='xs').classes('text-slate-400 dark:text-slate-300')
                                    with ui.column().classes('gap-0'):
                                        ui.label(
                                            data.get('name', device_id.replace('esp32-', '').title())
                                        ).classes('text-sm font-bold text-slate-700 dark:text-slate-200')
                                        ui.label(data.get('zone', 'Homelab')).classes('text-[10px] text-slate-400')
                                ui.badge(data.get('status', 'Optimal'), color='positive').props('dense rounded').classes('text-[9px] font-semibold')
                            with ui.row().classes('room-readings w-full justify-between items-end'):
                                with ui.column().classes('gap-1'):
                                    ui.label(f"{data.get('temperature', 0):.1f}°").classes('room-temperature')
                                    ui.label('TEMPERATURE · °C').classes('room-caption')
                                with ui.column().classes('room-secondary gap-2'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('water_drop', size='15px')
                                        ui.label(f"{data.get('humidity', 0):.1f}%").classes('room-detail')
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('wifi', size='15px')
                                        ui.label(f"{data.get('rssi', -60)} dBm").classes('room-detail')

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
                    tile_cls = f"iot-plug-tile {'tile-on' if is_on else ''} {'tile-critical' if is_crit else ''} aspect-square flex flex-col justify-between p-4"
                    with ui.card().classes(tile_cls):
                        with ui.row().classes('items-start justify-between w-full'):
                            with ui.column().classes('gap-1'):
                                ui.icon(cfg.get('icon', 'power'), size='sm').classes(
                                    'text-emerald-500' if is_on else 'text-slate-400'
                                )
                                with ui.column().classes('gap-0 mt-1'):
                                    ui.label(cfg["name"]).classes(
                                        'text-sm font-bold text-slate-800 dark:text-slate-200 leading-tight'
                                    )
                                    ui.label(cfg.get("zone", "Homelab")).classes('text-[10px] text-slate-400')
                            if is_crit:
                                ui.icon('lock', size='14px').classes('text-rose-500').tooltip('Protected Infrastructure')

                        with ui.row().classes('items-end justify-between w-full mt-auto'):
                            ui.label(f"{watts:.1f} W" if is_on else "OFF").classes(
                                f"text-xs font-bold uppercase tracking-wider {'text-emerald-500 dark:text-emerald-400' if is_on else 'text-slate-400'}"
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
                            ).props('unelevated rounded').classes(
                                f"text-[11px] font-bold px-3 py-1 transition-colors {'bg-emerald-500 text-white hover:bg-emerald-600' if is_on else 'bg-blue-500 text-white hover:bg-blue-600'}"
                            )

            server_fleet_watts_label.set_text(f"{total_w:.1f} W total")
            server_fleet_active_label.set_text(f"{active_cnt}/{len(tuya_local.DEVICES)} powered on")

        ui.timer(3.0, update_iot_display)

        # ── 3. AI Analysis Card ──────────────────────────────────────────────
        with ui.card().classes('glass-card analysis-panel w-full'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    with ui.row().classes('items-center justify-between w-full mb-1'):
                        ui.label('DeepMind analysis').classes(
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
