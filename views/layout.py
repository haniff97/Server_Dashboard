"""
views/layout.py
===============
Main SPA layout — index_page (/) and cloud_page (/cloud).
Wires together all view modules with responsive glass header and tab panels.
"""
import os
import sys
from nicegui import ui

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import services.db as db
import services.tuya_local as tuya_local
import services.cloud_db as cloud_db
import models.state as state
from views.styles import add_common_styles
from views.server_view import render_server_content
from views.energy_view import render_energy_content
from views.plugs_view import render_plugs_content
from views.network_view import render_network_content
from controllers.network_controller import trigger_network_ai


@ui.page('/')
def index_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(
        primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
        positive='#10b981', warning='#f59e0b', negative='#ef4444'
    )
    
    with ui.header().classes('glass-header items-center justify-between p-3 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto sm:flex-1 justify-center sm:justify-start relative'):
            ui.icon('dns', size='md', color='primary').classes('drop-shadow-md')
            ui.label('HOMELAB').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            # Mobile-only dark mode button placed on the right edge
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes(
                'lt-sm absolute right-2 text-slate-900 dark:text-white'
            ).bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')
        
        with ui.row().classes('items-center justify-center z-10 w-full sm:w-auto sm:flex-1 mt-3 sm:mt-0'):
            toggle = ui.toggle(
                ['Server', 'Energy', 'Plugs', 'Network'], value='Server'
            ).props('unelevated rounded').classes('q-btn-group').style('border-radius: 20px; font-weight: 600;')

        with ui.row().classes('items-center justify-end gap-4 z-10 gt-xs sm:flex-1'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1 gt-sm'):
                ui.icon('schedule', size='xs', color='gray-400')
                ui.label().bind_text_from(state, 'last_update').classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes(
                'text-slate-900 dark:text-white'
            ).bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto px-4 sm:px-6 pt-0 pb-4 sm:pb-6 mt-0 gap-4 sm:gap-8'):
        async def on_tab_change(e):
            if e.value == 'Network':
                await trigger_network_ai()

        toggle.on_value_change(on_tab_change)

        with ui.tab_panels(toggle, value='Server').classes('w-full bg-transparent p-0'):
            with ui.tab_panel('Server').classes('p-0'):
                render_server_content(on_nav_to_plugs=lambda: toggle.set_value('Plugs'))
            with ui.tab_panel('Energy').classes('p-0'):
                render_energy_content()
            with ui.tab_panel('Plugs').classes('p-0'):
                render_plugs_content()
            with ui.tab_panel('Network').classes('p-0'):
                render_network_content()


@ui.page('/cloud')
async def cloud_page():
    add_common_styles()

    with ui.column().classes('w-full q-pa-md gap-6 max-w-7xl mx-auto'):

        ui.label('☁️ Cloud Monitor — AWS DynamoDB').classes('text-h4 text-bold q-mb-sm')

        # ── Today's summary cards ──────────────────────────────────────────────
        ui.label("Today's Summary").classes('text-h6 text-grey-4')
        with ui.row().classes('w-full gap-4'):
            for dev_key, cfg in tuya_local.DEVICES.items():
                summary = cloud_db.get_today_summary(dev_key)
                with ui.card().classes('flex-1 q-pa-md glass-card'):
                    ui.label(cfg['name']).classes('text-subtitle1 text-bold q-mb-sm')
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

        for dev_key, cfg in tuya_local.DEVICES.items():
            ui.label(f"{cfg['name']} — Last 15 Readings").classes('text-h6 q-mt-sm')
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
                ui.table(columns=COLUMNS, rows=rows, row_key='ts').classes('w-full glass-card')
            else:
                ui.label('No data available').classes('text-grey')
