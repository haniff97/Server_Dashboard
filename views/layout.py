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
        primary='#226dbe', secondary='#6557b8', accent='#a66328',
        positive='#16805e', warning='#b77915', negative='#c23d58'
    )

    # ── Horizon App Topbar ────────────────────────────────────────────────────
    with ui.header().classes('app-topbar items-center justify-between'):
        with ui.row().classes('items-center gap-3'):
            with ui.element('div').classes('brand-symbol'):
                ui.icon('dns', size='21px')
            with ui.column().classes('gap-0'):
                ui.label('homelab').classes('brand-name')
                ui.label('CONTROL CENTER').classes('brand-caption')

        toggle = ui.toggle(
            ['Server', 'Energy', 'Plugs', 'Network'], value='Server'
        ).props('unelevated no-caps').classes('workspace-nav')

        with ui.row().classes('items-center gap-3'):
            ui.label().bind_text_from(
                state, 'last_update',
                backward=lambda x: f'Updated {x}' if x else 'Collecting data'
            ).classes('shell-update')
            ui.button(icon='light_mode', on_click=lambda: dark_mode.toggle()).props(
                'flat round aria-label="Toggle theme"'
            ).classes('theme-button').bind_icon_from(
                dark_mode, 'value', backward=lambda x: 'light_mode' if x else 'dark_mode'
            )

    # ── Page heading copy per tab ─────────────────────────────────────────────
    headings = {
        'Server':  ('Server overview',  'System resources, room conditions and connected devices.'),
        'Energy':  ('Energy monitor',   'Power consumption, daily usage and cost estimates.'),
        'Plugs':   ('Device fleet',     'Monitor and control your connected smart plugs.'),
        'Network': ('Network monitor',  'Latency, packet loss and route diagnostics.'),
    }

    # ── Main content shell ────────────────────────────────────────────────────
    with ui.column().classes('dashboard-main'):
        with ui.column().classes('page-heading gap-1'):
            ui.label('YOUR HOMELAB').bind_text_from(
                toggle, 'value', backward=lambda x: f'HOMELAB / {x.upper()}'
            ).classes('page-eyebrow')
            ui.label().bind_text_from(
                toggle, 'value', backward=lambda x: headings[x][0]
            ).classes('page-title')
            ui.label().bind_text_from(
                toggle, 'value', backward=lambda x: headings[x][1]
            ).classes('page-description')

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
