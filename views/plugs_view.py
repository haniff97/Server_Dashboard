"""
views/plugs_view.py
===================
Plugs tab — Scalable Fleet Manager with KPIs, zone filters, safety dialogs, and detail controls.
"""
from datetime import datetime
from nicegui import ui, run

import services.tuya_local as tuya_local
import services.db as db
import models.state as state
from controllers.plug_controller import toggle_plug, exec_plug_cmd

plug_state        = state.plug_state
plug_lock         = state.plug_lock
energy_cache      = state.energy_cache
energy_cache_lock = state.energy_cache_lock


def _plug_chart_options(dev_key: str) -> dict:
    """Build ECharts options for a plug's 120s power history."""
    with plug_lock:
        pts = list(plug_state.get(dev_key, {}).get("history", []))
    labels = [p["t"] for p in pts]
    values = [round(p["w"], 1) for p in pts]
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(15, 23, 42, 0.8)",
            "borderColor": "rgba(255, 255, 255, 0.1)",
            "textStyle": {"color": "#f8fafc", "fontFamily": "Inter", "fontSize": 11},
        },
        "grid": {"left": "9%", "right": "3%", "top": "10%", "bottom": "20%"},
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": "#94a3b8", "fontSize": 9, "rotate": 35},
            "axisLine": {"lineStyle": {"color": "rgba(0,0,0,0.1)"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#94a3b8", "fontSize": 9},
            "splitLine": {"lineStyle": {"color": "rgba(0,0,0,0.05)", "type": "dashed"}},
        },
        "series": [{
            "data": values,
            "type": "line",
            "smooth": True,
            "symbol": "none",
            "lineStyle": {"color": "#10B981", "width": 2},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(16, 185, 129, 0.3)"},
                    {"offset": 1, "color": "rgba(16, 185, 129, 0.02)"},
                ],
            }},
        }],
    }


def render_plugs_content():
    cards_data = {}
    active_zone = {'val': 'All'}
    active_status = {'val': 'All'}
    search_query = {'val': ''}
    pending_off_dev = {'key': None}
    detail_modal_dev = {'key': 'server'}

    with ui.column().classes('w-full gap-4 sm:gap-6'):

        # ── Safety Confirmation Modal for Critical Devices ───────────────────
        with ui.dialog() as confirm_dialog, ui.card().classes('glass-card p-6 max-w-md w-full border-2 border-rose-500/40'):
            with ui.row().classes('items-center gap-3 text-rose-500 mb-2'):
                ui.icon('warning', size='md')
                ui.label('Critical Infrastructure Protection').classes('text-lg font-bold text-slate-800 dark:text-white')
            confirm_desc = ui.label('').classes('text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-4')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel (Keep Running)', on_click=confirm_dialog.close).props('outline rounded text-color=grey')
                async def _do_confirmed_off():
                    dk = pending_off_dev['key']
                    if dk and dk in tuya_local.DEVICES:
                        ok_cmd = await toggle_plug(dk, False)
                        if ok_cmd:
                            with plug_lock:
                                if plug_state.get(dk, {}).get("status"):
                                    plug_state[dk]["status"]["switch"] = False
                            ui.notify(f"🔴 Power cut confirmed for {tuya_local.DEVICES[dk]['name']}", type='negative')
                        else:
                            ui.notify(f"❌ Failed to cut power for {tuya_local.DEVICES[dk]['name']}", type='negative')
                    confirm_dialog.close()
                    _refresh_plugs()
                ui.button('Confirm Turn OFF', color='negative', on_click=_do_confirmed_off).props('unelevated rounded')

        # ── Device Detail & Controls Dialog ──────────────────────────────────
        with ui.dialog().props('backdrop-filter="blur(8px)"') as detail_dialog, ui.card().classes('glass-card p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto'):
            with ui.row().classes('w-full items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-4'):
                with ui.row().classes('items-center gap-3'):
                    modal_icon = ui.icon('dns', size='md', color='primary').classes('p-2 bg-blue-500/10 rounded-2xl')
                    with ui.column().classes('gap-0'):
                        modal_title = ui.label('Device Details').classes('text-xl font-black text-slate-800 dark:text-white')
                        modal_subtitle = ui.label('').classes('text-xs text-slate-400')
                ui.button(icon='close', on_click=detail_dialog.close).props('flat round dense').classes('text-slate-400 hover:text-white')

            # Modal Power History Chart
            with ui.card().classes('w-full p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl mb-4'):
                with ui.row().classes('w-full items-center justify-between mb-2'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('show_chart', size='xs', color='positive')
                        ui.label('LIVE POWER DRAW (120s History)').classes('text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400')
                    modal_live_watts = ui.label('0.0 W').classes('text-sm font-mono font-bold text-emerald-500')
                modal_chart = ui.echart(_plug_chart_options('plug')).style('height:200px;width:100%')

            # Controls & Timers
            with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-4 mb-4'):
                # Child Lock & Safety
                with ui.card().classes('p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800'):
                    ui.label('CHILD LOCK & SAFETY').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                    with ui.row().classes('w-full gap-2'):
                        async def set_lock(state_val: bool):
                            dk = detail_modal_dev['key']
                            ok, msg = await exec_plug_cmd(lambda: tuya_local.set_child_lock(dk, state_val), "Child lock updated")
                            ui.notify(msg, type='positive' if ok else 'warning')
                        ui.button('🔒 Lock ON', on_click=lambda: set_lock(True)).props('unelevated rounded outline size=sm').classes('flex-1 text-xs')
                        ui.button('🔓 Lock OFF', on_click=lambda: set_lock(False)).props('unelevated rounded outline size=sm').classes('flex-1 text-xs')

                # LED Indicator Mode
                with ui.card().classes('p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800'):
                    ui.label('HARDWARE LED INDICATOR').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                    with ui.row().classes('w-full gap-2'):
                        async def set_led(mode_val: str, label_name: str):
                            dk = detail_modal_dev['key']
                            ok, msg = await exec_plug_cmd(lambda: tuya_local.set_led_mode(dk, mode_val), f"LED mode set to {label_name}")
                            ui.notify(msg, type='positive' if ok else 'warning')

                        ui.button('Relay', on_click=lambda: set_led('relay', 'Follow Relay')).props('unelevated rounded outline size=sm').classes('flex-1 text-[11px]')
                        ui.button('Always ON', on_click=lambda: set_led('pos', 'Always ON')).props('unelevated rounded outline size=sm').classes('flex-1 text-[11px]')
                        ui.button('Always OFF', on_click=lambda: set_led('none', 'Always OFF')).props('unelevated rounded outline size=sm').classes('flex-1 text-[11px]')

            # Countdown Timer
            with ui.card().classes('w-full p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 mb-4'):
                ui.label('AUTOMATED TIMER & COUNTDOWN').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                with ui.row().classes('w-full items-center gap-2 flex-wrap sm:flex-nowrap'):
                    async def set_timer(sec: int, lbl: str):
                        dk = detail_modal_dev['key']
                        ok, msg = await exec_plug_cmd(lambda: tuya_local.set_countdown(dk, sec), f"Timer set for {lbl}")
                        ui.notify(msg, type='positive' if ok else 'warning')

                    for t_min in [15, 30, 60, 120]:
                        ui.button(f"{t_min}m", on_click=lambda m=t_min: set_timer(m * 60, f"{m}m")).props('unelevated rounded outline size=sm').classes('text-xs')
                    countdown_inp = ui.number(label='Custom seconds', value=0, min=0, max=86400).props('dense outlined rounded').classes('flex-1 text-xs')
                    ui.button('Set Timer', on_click=lambda: set_timer(int(countdown_inp.value or 0), f"{int(countdown_inp.value or 0)}s")).props('unelevated rounded size=sm color=primary').classes('text-xs font-bold')

            # Hardware Info Footer
            with ui.row().classes('w-full items-center justify-between p-3 rounded-2xl bg-slate-100 dark:bg-slate-800/40 text-xs font-mono text-slate-500 dark:text-slate-400'):
                modal_ip_label = ui.label('IP: —')
                modal_id_label = ui.label('ID: —')
                modal_latency_label = ui.label('LAN Status: Connected')

        def open_detail_modal(dk: str):
            detail_modal_dev['key'] = dk
            cfg = tuya_local.DEVICES.get(dk, {})
            with plug_lock:
                s = plug_state.get(dk, {}).get("status")
            modal_title.set_text(cfg.get("name", dk))
            modal_subtitle.set_text(f"{cfg.get('zone', 'Homelab')} • ID: {cfg.get('id', '—')}")
            modal_icon.props(f"name={cfg.get('icon', 'power')}")
            modal_ip_label.set_text(f"IP: {cfg.get('ip', '—')}")
            modal_id_label.set_text(f"ID: {cfg.get('id', '—')}")
            modal_live_watts.set_text(f"{s['watts']:.1f} W" if s else "0.0 W")
            modal_chart.options.update(_plug_chart_options(dk))
            modal_chart.update()
            detail_dialog.open()

        # ── 1. Fleet KPI Summary Header ──────────────────────────────────────
        with ui.card().classes('glass-card w-full p-4 sm:p-6 relative overflow-hidden'):
            ui.html('<div class="absolute inset-0 bg-gradient-to-r from-emerald-500/10 via-blue-500/5 to-purple-500/10 pointer-events-none"></div>')
            with ui.row().classes('w-full items-center justify-between flex-wrap gap-4 z-10 relative'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('power', size='md', color='positive').classes('p-2 bg-green-500/10 rounded-2xl')
                    with ui.column().classes('gap-0'):
                        ui.label('Smart Plug Fleet').classes('text-2xl font-black tracking-tight text-slate-800 dark:text-white')
                        ui.label(f'Monitoring {len(tuya_local.DEVICES)} smart plugs across homelab zones').classes('text-xs text-slate-500 dark:text-slate-400')

                async def handle_turn_all_on():
                    for dk in tuya_local.DEVICES:
                        await toggle_plug(dk, True)
                    ui.notify("✅ All smart plugs turned ON", type='positive')
                    _refresh_plugs()

                async def handle_turn_non_critical_off():
                    count = 0
                    for dk, cfg in tuya_local.DEVICES.items():
                        is_crit = cfg.get("is_critical", False) or cfg.get("is_server", False)
                        if not is_crit:
                            await toggle_plug(dk, False)
                            count += 1
                    ui.notify(f"🔴 Turned OFF {count} non-critical plugs (Server & Critical protected)", type='info')
                    _refresh_plugs()

                with ui.row().classes('items-center gap-2'):
                    ui.button('Turn All On', icon='bolt', on_click=handle_turn_all_on).props('unelevated rounded outline').classes('text-xs font-bold text-emerald-600 dark:text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10')
                    ui.button('Turn Non-Critical Off', icon='power_off', on_click=handle_turn_non_critical_off).props('unelevated rounded outline').classes('text-xs font-bold text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-700 hover:bg-red-500/10')

            ui.separator().classes('my-4 bg-slate-200/50 dark:bg-slate-800/50')

            with ui.grid().classes('w-full grid-cols-2 lg:grid-cols-4 gap-4'):
                # 1. Total Fleet Power
                with ui.column().classes('p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/60'):
                    ui.label('FLEET LIVE LOAD').classes('text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider')
                    with ui.row().classes('items-baseline gap-1 mt-1'):
                        fleet_watts_label = ui.label('0.0').classes('text-2xl sm:text-3xl font-black text-amber-500')
                        ui.label('W').classes('text-xs font-bold text-slate-400')
                    fleet_kw_label = ui.label('0.000 kW combined').classes('text-[10px] text-slate-400')

                # 2. Active Devices
                with ui.column().classes('p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/60'):
                    ui.label('ACTIVE DEVICES').classes('text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider')
                    with ui.row().classes('items-baseline gap-1 mt-1'):
                        fleet_active_label = ui.label(f'0 / {len(tuya_local.DEVICES)}').classes('text-2xl sm:text-3xl font-black text-emerald-500')
                        ui.label('ONLINE').classes('text-[10px] font-bold text-slate-400')
                    fleet_active_bar = ui.linear_progress(value=0.0).props('color=positive track-color=grey-8 rounded').classes('h-1.5 mt-1')

                # 3. Today's Energy & Cost
                with ui.column().classes('p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/60'):
                    ui.label('TODAY ACCUMULATED').classes('text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider')
                    with ui.row().classes('items-baseline gap-2 mt-1'):
                        fleet_today_kwh_label = ui.label('0.00 kWh').classes('text-xl sm:text-2xl font-black text-blue-500')
                        fleet_today_cost_label = ui.label('RM 0.00').classes('text-xs font-bold text-slate-600 dark:text-slate-300')
                    ui.label('TNB Tariff Rate calculation').classes('text-[10px] text-slate-400')

                # 4. Top Consumer
                with ui.column().classes('p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/60'):
                    ui.label('TOP CONSUMER').classes('text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider')
                    top_device_name_label = ui.label('—').classes('text-sm sm:text-base font-bold text-slate-800 dark:text-white truncate mt-1')
                    top_device_watt_label = ui.label('— W draw').classes('text-[11px] font-bold text-orange-500')

        # ── 2. Filter & Search Toolbar ───────────────────────────────────────
        with ui.card().classes('glass-card w-full p-3 sm:p-4'):
            with ui.row().classes('w-full items-center justify-between flex-wrap gap-3'):
                with ui.row().classes('items-center gap-1.5 flex-wrap'):
                    ui.label('Zone:').classes('text-xs font-bold text-slate-400 uppercase mr-1')
                    distinct_zones = ['All'] + sorted(list(set(cfg.get('zone', 'Homelab') for cfg in tuya_local.DEVICES.values())))
                    zone_btns = {}
                    for z in distinct_zones:
                        def make_zone_click(selected_z=z):
                            def _click():
                                active_zone['val'] = selected_z
                                for name, b in zone_btns.items():
                                    if name == selected_z:
                                        b.props('color=primary unelevated')
                                    else:
                                        b.props('color=grey flat')
                                _apply_filters()
                            return _click
                        btn = ui.button(z, on_click=make_zone_click(z)).props(
                            f"{'color=primary unelevated' if z == 'All' else 'color=grey flat'} rounded size=sm"
                        ).classes('filter-chip-btn')
                        zone_btns[z] = btn

                with ui.row().classes('items-center gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto'):
                    status_toggle = ui.toggle(
                        ['All', 'Active ON', 'Idle / OFF', 'Protected Critical'],
                        value='All',
                        on_change=lambda e: (active_status.update({'val': e.value}), _apply_filters())
                    ).props('unelevated size=sm rounded').classes('bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400')

                    def on_search_change(e):
                        search_query['val'] = (e.value or '').strip().lower()
                        _apply_filters()

                    ui.input(placeholder='Search plug...', on_change=on_search_change).props('dense outlined rounded clearable').classes('w-full sm:w-44 text-xs')

        # ── 3. Scalable Responsive Plug Grid ─────────────────────────────────
        cards_grid = ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3')

        with cards_grid:
            for dev_key, cfg in tuya_local.DEVICES.items():
                is_crit = cfg.get("is_critical", False) or cfg.get("is_server", False)
                with plug_lock:
                    s = plug_state.get(dev_key, {}).get("status")
                    ok = plug_state.get(dev_key, {}).get("ok", False)
                is_on = s["switch"] if s else False

                with ui.element('div').classes('w-full') as card_wrapper:
                    card_cls = f"plug-card-modern p-4 sm:p-5 flex flex-col justify-between h-full {'plug-active' if is_on else ''} {'plug-critical' if is_crit else ''}"
                    with ui.card().classes(card_cls) as card_el:

                        # Header: Icon + Name + Zone + Critical Badge + Pulse Dot
                        with ui.row().classes('items-center justify-between w-full mb-3'):
                            with ui.row().classes('items-center gap-2.5 overflow-hidden'):
                                with ui.element('div').classes('p-2 rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center'):
                                    icon_el = ui.icon(cfg.get('icon', 'power'), size='sm').classes('text-primary')
                                with ui.column().classes('gap-0 overflow-hidden'):
                                    ui.label(cfg["name"]).classes('text-sm font-bold text-slate-800 dark:text-white truncate')
                                    with ui.row().classes('items-center gap-1.5'):
                                        ui.label(cfg.get('zone', 'Homelab')).classes('text-[10px] text-slate-400 font-medium')
                                        ui.label(f"• {cfg.get('ip', '—')}").classes('text-[10px] text-slate-400 font-mono')

                            with ui.row().classes('items-center gap-2 flex-shrink-0'):
                                if is_crit:
                                    ui.badge('🔒 Protected', color='negative').props('dense rounded').classes('text-[9px] font-bold')
                                dot_el = ui.element('span').classes('pulse-dot-online' if ok else 'pulse-dot-offline')

                        # Center: Big Wattage + Switch Button
                        with ui.row().classes('items-center justify-between w-full my-2'):
                            with ui.column().classes('gap-0'):
                                with ui.row().classes('items-baseline gap-1'):
                                    watts_val_label = ui.label('0.0').classes('text-2xl font-black text-slate-800 dark:text-white font-mono')
                                    ui.label('W').classes('text-xs font-bold text-slate-400')

                            # Power Switch Button
                            def make_toggle(dk=dev_key, crit=is_crit):
                                async def _toggle_fn():
                                    with plug_lock:
                                        cur_s = plug_state.get(dk, {}).get("status")
                                        cur_on = cur_s["switch"] if cur_s else False

                                    if cur_on and crit:
                                        pending_off_dev['key'] = dk
                                        confirm_desc.set_text(
                                            f"You are about to cut power to {tuya_local.DEVICES[dk]['name']} ({tuya_local.DEVICES[dk].get('zone', 'Homelab')}). "
                                            f"This device is marked as critical infrastructure. Are you sure?"
                                        )
                                        confirm_dialog.open()
                                        return

                                    target_state = not cur_on
                                    ok_cmd = await toggle_plug(dk, target_state)
                                    if ok_cmd:
                                        with plug_lock:
                                            if plug_state.get(dk, {}).get("status"):
                                                plug_state[dk]["status"]["switch"] = target_state
                                        ui.notify(f"{'🔴 Turned OFF' if cur_on else '✅ Turned ON'}: {tuya_local.DEVICES[dk]['name']}", type='negative' if cur_on else 'positive')
                                        _refresh_plugs()
                                    else:
                                        ui.notify(f"❌ Failed to toggle {tuya_local.DEVICES[dk]['name']}", type='negative')
                                return _toggle_fn

                            switch_btn = ui.button(
                                "● ON" if is_on else "○ OFF",
                                on_click=make_toggle(dev_key, is_crit)
                            ).classes(f"plug-switch-btn {'plug-switch-on' if is_on else 'plug-switch-off'}")

                        ui.separator().classes('my-2 bg-slate-200/40 dark:bg-slate-800/40')

                        # Metrics Strip: Volts, Amps, Today kWh, Today RM
                        with ui.grid().classes('w-full grid-cols-4 gap-1 text-center my-1'):
                            with ui.column().classes('gap-0 items-center'):
                                v_label = ui.label('—').classes('text-xs font-bold font-mono text-slate-700 dark:text-slate-200')
                                ui.label('VOLTS').classes('text-[9px] text-slate-400 font-bold')
                            with ui.column().classes('gap-0 items-center'):
                                ma_label = ui.label('—').classes('text-xs font-bold font-mono text-slate-700 dark:text-slate-200')
                                ui.label('AMPS').classes('text-[9px] text-slate-400 font-bold')
                            with ui.column().classes('gap-0 items-center'):
                                kwh_label = ui.label('0.00').classes('text-xs font-bold font-mono text-emerald-600 dark:text-emerald-400')
                                ui.label('TODAY').classes('text-[9px] text-slate-400 font-bold')
                            with ui.column().classes('gap-0 items-center'):
                                rm_label = ui.label('RM 0.00').classes('text-xs font-bold font-mono text-blue-600 dark:text-blue-400')
                                ui.label('COST').classes('text-[9px] text-slate-400 font-bold')

                        # Sparkline / Details modal trigger
                        with ui.row().classes('w-full justify-end items-center mt-2'):
                            ui.button('Details & Timers →', on_click=lambda dk=dev_key: open_detail_modal(dk)).props('flat rounded dense').classes('text-[10px] font-bold text-slate-400 hover:text-primary px-2')

                    cards_data[dev_key] = {
                        'wrapper': card_wrapper,
                        'card_el': card_el,
                        'switch_btn': switch_btn,
                        'watts_label': watts_val_label,
                        'v_label': v_label,
                        'ma_label': ma_label,
                        'kwh_label': kwh_label,
                        'rm_label': rm_label,
                        'dot_el': dot_el,
                        'zone': cfg.get('zone', 'Homelab'),
                        'name': cfg['name'],
                        'is_crit': is_crit,
                    }

    def _apply_filters():
        q = search_query['val']
        z = active_zone['val']
        s_filter = active_status['val']

        for dk, data in cards_data.items():
            visible = True
            if q and (q not in data['name'].lower() and q not in data['zone'].lower()):
                visible = False
            if z != 'All' and data['zone'] != z:
                visible = False
            
            with plug_lock:
                st = plug_state.get(dk, {}).get("status")
            cur_on = st["switch"] if st else False

            if s_filter == 'Active ON' and not cur_on:
                visible = False
            elif s_filter == 'Idle / OFF' and cur_on:
                visible = False
            elif s_filter == 'Protected Critical' and not data['is_crit']:
                visible = False

            data['wrapper'].set_visibility(visible)

    def _refresh_plugs():
        total_w = 0.0
        active_cnt = 0
        total_kwh_sum = 0.0
        total_cost_sum = 0.0
        top_dev_name = 'None'
        max_dev_w = -1.0

        for dk, data in cards_data.items():
            with plug_lock:
                s = plug_state.get(dk, {}).get("status")
                ok = plug_state.get(dk, {}).get("ok", False)

            with energy_cache_lock:
                cache_entry = energy_cache.get(dk, {})
                dev_kwh = cache_entry.get("total_kwh", 0.0)
                dev_rm  = cache_entry.get("cost_rm", 0.0)

            total_kwh_sum += dev_kwh
            total_cost_sum += dev_rm

            data['dot_el'].classes(replace='pulse-dot-online' if ok else 'pulse-dot-offline')

            if s:
                on = s.get("switch", False)
                w = s.get("watts", 0.0)
                v = s.get("voltage", 0.0)
                ma = s.get("current_ma", 0)

                if on:
                    active_cnt += 1
                    total_w += w
                    if w > max_dev_w:
                        max_dev_w = w
                        top_dev_name = data['name']

                data['watts_label'].set_text(f"{w:.1f}")
                data['v_label'].set_text(f"{v:.0f}V")
                data['ma_label'].set_text(f"{ma}mA")
                data['kwh_label'].set_text(f"{dev_kwh:.3f}")
                data['rm_label'].set_text(f"RM{dev_rm:.2f}")

                data['switch_btn'].set_text("● ON" if on else "○ OFF")
                data['switch_btn'].classes(
                    replace=f"plug-switch-btn {'plug-switch-on' if on else 'plug-switch-off'}"
                )
                if on:
                    data['card_el'].classes(add='plug-active')
                else:
                    data['card_el'].classes(remove='plug-active')

        fleet_watts_label.set_text(f"{total_w:.1f}")
        fleet_kw_label.set_text(f"{total_w/1000.0:.3f} kW combined")
        fleet_active_label.set_text(f"{active_cnt} / {len(tuya_local.DEVICES)}")
        fleet_active_bar.set_value(active_cnt / max(len(tuya_local.DEVICES), 1))
        fleet_today_kwh_label.set_text(f"{total_kwh_sum:.2f} kWh")
        fleet_today_cost_label.set_text(f"RM {total_cost_sum:.2f}")
        top_device_name_label.set_text(top_dev_name)
        top_device_watt_label.set_text(f"{max_dev_w:.1f} W draw" if max_dev_w >= 0 else "0.0 W draw")

    ui.timer(3.0, _refresh_plugs)
