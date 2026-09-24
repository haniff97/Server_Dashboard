"""
views/energy_view.py
====================
Energy tab — live power, kWh history, cost tracking, charts.
"""
from nicegui import ui, run

import tuya_local
import db
import models.state as state

plug_state        = state.plug_state
plug_lock         = state.plug_lock
energy_cache      = state.energy_cache
energy_cache_lock = state.energy_cache_lock

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
            with ui.column().classes('split-left flex flex-col justify-between hidden md:flex'):
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
                            d1 = {p["hour_str"]: (p["kwh"] or 0) for p in pts1}
                            d2 = {p["hour_str"]: (p["kwh"] or 0) for p in pts2}
                            all_hours = sorted(list(set(d1.keys()) | set(d2.keys())))
                            pts = [{"hour_str": h, "kwh": d1.get(h, 0) + d2.get(h, 0)} for h in all_hours]
                        else:
                            pts = await run.io_bound(db.get_hourly_history, tuya_local.DEVICES[dk]["id"], 24)
                        labels = [datetime.strptime(p["hour_str"], "%Y-%m-%d %H:%M:%S").strftime("%H:00") for p in pts]
                        values = [round((p["kwh"] or 0), 3) for p in pts]
                        area_chart.options['yAxis'][0]['name'] = 'Energy (kWh)'
                        area_chart.options['series'][0]['name'] = 'Energy (kWh)'

                    elif chart_filter['value'] in ['Week', 'Month']:
                        days_limit = 7 if chart_filter['value'] == 'Week' else 30
                        if dk == 'all':
                            pts1 = await run.io_bound(db.get_daily_history, tuya_local.DEVICES["plug"]["id"], days_limit)
                            pts2 = await run.io_bound(db.get_daily_history, tuya_local.DEVICES["server"]["id"], days_limit)
                            d1 = {str(p["date_str"]): (p["kwh"] or 0) for p in pts1}
                            d2 = {str(p["date_str"]): (p["kwh"] or 0) for p in pts2}
                            all_days = sorted(list(set(d1.keys()) | set(d2.keys())))
                            pts = [{"date_str": d, "kwh": d1.get(d, 0) + d2.get(d, 0)} for d in all_days]
                        else:
                            pts = await run.io_bound(db.get_daily_history, tuya_local.DEVICES[dk]["id"], days_limit)
                        labels = [datetime.strptime(str(p["date_str"]), "%Y-%m-%d").strftime("%b %d") for p in pts]
                        values = [round((p["kwh"] or 0), 3) for p in pts]
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
