"""
views/network_view.py
=====================
Network tab — latency charts, route log, AI insights card.
"""
from nicegui import ui, run

import models.state as state
from controllers.network_controller import call_gemini_network

# Convenience aliases
network_state = state.network_state
network_lock  = state.network_lock
NETWORK_TARGETS       = state.NETWORK_TARGETS
NETWORK_TARGET_LABELS = state.NETWORK_TARGET_LABELS

def render_network_content():
    with ui.column().classes('w-full gap-4 sm:gap-6'):
        with ui.row().classes('items-center gap-2 mb-2 w-full'):
            ui.icon('router', color='primary').classes('text-2xl')
            ui.label('Network Monitor').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')
            health_badge = ui.badge('GOOD', color='positive').classes(
                'ml-auto font-bold px-3 py-1 text-sm rounded-full shadow-sm')

        with ui.grid().classes('w-full gap-6 grid-cols-1 lg:grid-cols-3'):

            # ── Left: Chart + Target Cards ────────────────────────────────────
            with ui.column().classes('col-span-1 lg:col-span-2 gap-4'):

                with ui.card().classes('glass-card w-full p-4'):
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label('Live Latency (ms)').classes(
                            'font-semibold text-slate-700 dark:text-gray-300')
                        ui.icon('timeline', color='gray-400')

                    with network_lock:
                        init_series = [
                            {
                                'name': NETWORK_TARGET_LABELS.get(target, target),
                                'type': 'line', 'smooth': True, 'showSymbol': False,
                                'data': list(network_state['targets'][target]['history'])
                            }
                            for target in NETWORK_TARGETS
                        ]

                    chart = ui.echart({
                        'tooltip': {'trigger': 'axis'},
                        'legend': {
                            'data': [NETWORK_TARGET_LABELS.get(t, t) for t in NETWORK_TARGETS],
                            'textStyle': {'color': '#94a3b8'},
                            'bottom': 0
                        },
                        'grid': {
                            'left': '3%', 'right': '4%',
                            'bottom': '15%', 'top': '5%',
                            'containLabel': True
                        },
                        'xAxis': {
                            'type': 'category', 'boundaryGap': False,
                            'show': False, 'data': list(range(60))
                        },
                        'yAxis': {
                            'type': 'value',
                            'splitLine': {'lineStyle': {'color': '#334155'}}
                        },
                        'series': init_series,
                        'color': ['#3b82f6', '#10b981', '#f59e0b']
                    }).classes('w-full h-64')

                # Per-target status cards
                target_cards: dict = {}
                with ui.grid().classes('w-full gap-4 grid-cols-1 sm:grid-cols-3'):
                    for target in NETWORK_TARGETS:
                        with ui.card().classes(
                            'glass-card items-center text-center p-4 transition-all'
                        ) as c:
                            ui.label(NETWORK_TARGET_LABELS.get(target, target)).classes(
                                'text-sm font-medium text-slate-500 dark:text-gray-400 mb-1')
                            lat_label  = ui.label('— ms').classes(
                                'text-2xl font-bold text-slate-800 dark:text-white')
                            loss_label = ui.label('0.0% loss').classes(
                                'text-xs text-positive font-semibold mt-1 '
                                'bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded')
                            target_cards[target] = {'lat': lat_label, 'loss': loss_label, 'card': c}

            # ── Right: AI + Actions + Route Log ──────────────────────────────
            with ui.column().classes('col-span-1 gap-4'):

                # AI Insights card
                with ui.card().classes(
                    'glass-card w-full relative overflow-hidden p-4'
                ):
                    ui.html(
                        '<div class="absolute inset-0 bg-gradient-to-br '
                        'from-purple-500/10 to-blue-500/5 z-0 pointer-events-none"></div>'
                    )
                    with ui.row().classes(
                        'w-full justify-between items-center mb-3 z-10'
                    ):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('auto_awesome', color='purple-400').classes('animate-pulse')
                            ui.label('AI Insights').classes(
                                'font-bold text-purple-700 dark:text-purple-400')

                    with network_lock:
                        init_ai = network_state['ai_insights']
                    ai_label = ui.label(init_ai).classes(
                        'text-sm text-slate-600 dark:text-gray-300 z-10 '
                        'whitespace-pre-line leading-relaxed')

                # Action buttons
                with ui.card().classes('glass-card w-full p-4'):
                    ui.label('Actions').classes(
                        'font-semibold text-slate-700 dark:text-gray-300 mb-3')

                    async def _gen_isp_report():
                        """Force an immediate AI report regardless of interval."""
                        with network_lock:
                            lines = []
                            for t, td in network_state['targets'].items():
                                lines.append(
                                    f"{t}: latency={td['latency']:.1f}ms, "
                                    f"jitter={td['jitter']:.1f}ms, "
                                    f"packet_loss={td['packet_loss']:.1f}%"
                                )
                            events = "\n".join(network_state['route_log'][:5])
                            summary = "\n".join(lines)
                            if events:
                                summary += f"\n\nRecent events:\n{events}"
                        result = await run.io_bound(call_gemini_network, summary)
                        with network_lock:
                            network_state['ai_insights'] = result
                            network_state['last_ai_run'] = time.time()

                    async def _manual_traceroute():
                        """Run traceroute on all targets immediately."""
                        ts_str = datetime.now().strftime("%H:%M:%S")
                        for target in NETWORK_TARGETS:
                            hops = await run.io_bound(_run_traceroute, target)
                            with network_lock:
                                prev = network_state['last_traceroute'].get(target, [])
                                change = "changed" if (prev and hops != prev) else "stable"
                                msg = f"{ts_str} - Manual trace {target}: {len(hops)} hops ({change})"
                                network_state['route_log'].insert(0, msg)
                                network_state['route_log'] = network_state['route_log'][:15]
                                if hops:
                                    network_state['last_traceroute'][target] = hops

                    ui.button(
                        'Generate ISP Report', icon='description', color='primary',
                        on_click=_gen_isp_report
                    ).props('unelevated rounded').classes('w-full mb-2 shadow-sm')

                    ui.button(
                        'Run Manual Traceroute', icon='route', color='secondary',
                        on_click=_manual_traceroute
                    ).props('unelevated rounded').classes('w-full shadow-sm')

                # Route Event Log
                with ui.card().classes('glass-card w-full flex-grow p-4'):
                    with ui.row().classes('w-full items-center gap-2 mb-3'):
                        ui.icon('list_alt', color='gray-400')
                        ui.label('Route Events').classes(
                            'font-semibold text-slate-700 dark:text-gray-300')
                    log_container = ui.column().classes(
                        'w-full text-xs font-mono text-slate-600 dark:text-gray-400 gap-2')
                    with network_lock:
                        for log in network_state['route_log']:
                            with log_container:
                                ui.label(log)

    # ── UI refresh timer — reads from global state, never blocks ─────────────
    def _refresh_network_ui():
        with network_lock:
            health     = network_state['health']
            ai_text    = network_state['ai_insights']
            route_log  = list(network_state['route_log'])
            targets_snapshot = {
                t: {
                    'latency':     td['latency'],
                    'packet_loss': td['packet_loss'],
                    'history':     list(td['history']),
                    'status':      td['status'],
                }
                for t, td in network_state['targets'].items()
            }

        # Health badge
        health_badge.set_text(health)
        health_badge.props(
            f'color={"positive" if health == "GOOD" else "warning" if health == "WARNING" else "negative"}'
        )

        # Chart series
        for i, target in enumerate(NETWORK_TARGETS):
            chart.options['series'][i]['data'] = targets_snapshot[target]['history']
        chart.update()

        # Target cards
        for target, elems in target_cards.items():
            td = targets_snapshot[target]
            elems['lat'].set_text(
                f"{td['latency']:.1f} ms" if td['latency'] > 0 else "— ms")
            elems['loss'].set_text(f"{td['packet_loss']:.1f}% loss")

            if td['packet_loss'] >= NETWORK_PACKET_LOSS_THRESHOLD:
                elems['loss'].classes(
                    replace='text-xs text-negative font-semibold mt-1 '
                            'bg-red-100 dark:bg-red-900/30 px-2 py-0.5 rounded animate-pulse'
                )
                elems['card'].classes(add='border-2 border-red-500/50')
            else:
                elems['loss'].classes(
                    replace='text-xs text-positive font-semibold mt-1 '
                            'bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded'
                )
                elems['card'].classes(remove='border-2 border-red-500/50')

        # AI insights
        ai_label.set_text(ai_text)

        # Route log
        log_container.clear()
        for log in route_log:
            with log_container:
                ui.label(log)

    ui.timer(3.0, _refresh_network_ui)

# ─────────────────────────────────────────────────────────────────────────────
#  ENERGY CACHE LOOP (runs in background thread, feeds UI timers)
# ─────────────────────────────────────────────────────────────────────────────
