"""
views/plugs_view.py
===================
Plugs tab — _plug_chart_options, _build_plug_panel, render_plugs_content.
"""
from nicegui import ui, run

import tuya_local
import db
import models.state as state

# Convenience aliases
plug_state        = state.plug_state
plug_lock         = state.plug_lock
energy_cache      = state.energy_cache
energy_cache_lock = state.energy_cache_lock

def _plug_chart_options(dev_key: str) -> dict:
    """Build ECharts options for a plug's power history."""
    with plug_lock:
        pts = list(plug_state[dev_key]["history"])
    labels = [p["t"] for p in pts]
    values = [round(p["w"], 1) for p in pts]
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(15, 23, 42, 0.8)", "borderColor": "rgba(255, 255, 255, 0.1)",
            "textStyle": {"color": "#f8fafc", "fontFamily": "Inter", "fontSize": 11},
        },
        "grid": {"left": "9%", "right": "3%", "top": "10%", "bottom": "20%"},
        "xAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#94a3b8", "fontSize": 9, "rotate": 35},
            "axisLine": {"lineStyle": {"color": "rgba(0,0,0,0.1)"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#94a3b8", "fontSize": 9},
            "splitLine": {"lineStyle": {"color": "rgba(0,0,0,0.05)", "type": "dashed"}},
        },
        "series": [{
            "data": values, "type": "line", "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#E11D48", "width": 2},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(225,29,72,.28)"},
                    {"offset": 1, "color": "rgba(225,29,72,.02)"},
                ],
            }},
        }],
    }


def _build_plug_panel(dev_key: str) -> dict:
    """Build one full device card for the /plugs page. Returns UI refs."""
    cfg       = tuya_local.DEVICES[dev_key]
    is_server = cfg["is_server"]
    dev_id    = cfg["id"]

    server_off_confirm = {"pending": False}

    card_cls = "plug-card server-card" if is_server else "plug-card"
    with plug_lock:
        s  = plug_state[dev_key]["status"]
        ok = plug_state[dev_key]["ok"]
    on = s["switch"] if s else False
    if on:
        card_cls += " plug-on"

    with ui.element("div").classes(card_cls).style("padding:22px") as card_el:

        # Header
        with ui.row().classes("items-center justify-between mb-3"):
            with ui.element("div"):
                ui.label(cfg["name"].upper()).classes("plug-section-title").style("margin-bottom:2px")
                if is_server:
                    ui.label("⚠ SERVER POWER — DOUBLE CONFIRM TO OFF").style(
                        "font-size:.6rem;color:#f87171;font-family:monospace;letter-spacing:.08em")
                else:
                    ui.label("PLACEHOLDER").style(
                        "font-size:.6rem;font-family:monospace;letter-spacing:.08em;opacity:0;user-select:none")
            conn_dot = ui.element("span").classes("dot-ok" if ok else "dot-err")

        # Status strip
        with ui.element("div").classes("plug-stat-strip"):
            ref_watts = ui.label("—").classes("plug-stat-num").style("color:#f59e0b")
            ui.label("W · POWER").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            ref_voltage = ui.label("—").classes("plug-stat-num").style("color:#a78bfa")
            ui.label("V · VOLTAGE").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            ref_current = ui.label("—").classes("plug-stat-num").style("color:#fb923c")
            ui.label("mA · CURRENT").classes("plug-stat-lbl")

        # Toggle button
        toggle_btn = ui.button(
            "● ON" if on else "○ OFF",
            on_click=lambda: handle_toggle()
        ).classes(f"plug-toggle {'plug-toggle-on' if on else 'plug-toggle-off'}").style("margin-top:14px")

        # Warning banner (server only)
        if is_server:
            warn_ref = ui.element("div").classes("plug-warn-banner")
            with warn_ref:
                ui.label("⚠ WARNING: This will cut power to the server. Click OFF again to confirm.")
        else:
            warn_ref = None

        async def handle_toggle():
            with plug_lock:
                st = plug_state[dev_key]["status"]
            current_on = st["switch"] if st else False

            if not current_on:
                ok_cmd = await run.io_bound(tuya_local.set_switch, dev_key, True)
                if ok_cmd:
                    await run.io_bound(db.insert_state_change, dev_id, cfg["name"], True)
                    server_off_confirm["pending"] = False
                    # Update button UI immediately
                    toggle_btn.classes(remove="plug-toggle-on plug-toggle-off plug-toggle-warn").classes("plug-toggle-on")
                    toggle_btn.set_text("● ON")
                    if warn_ref:
                        warn_ref.style("display:none")
                    card_el.classes(add="plug-on")
                    ui.notify("✅ Turned ON", type="positive")
                else:
                    ui.notify("⚠ Command failed", type="warning")
                return

            if is_server and not server_off_confirm["pending"]:
                server_off_confirm["pending"] = True
                toggle_btn.classes(remove="plug-toggle-on plug-toggle-off").classes("plug-toggle-warn")
                toggle_btn.set_text("⚠ CLICK AGAIN TO CONFIRM OFF")
                if warn_ref:
                    warn_ref.style("display:block")
                ui.notify("⚠ Server plug — click again to confirm OFF", type="warning")
                return

            ok_cmd = await run.io_bound(tuya_local.set_switch, dev_key, False)
            if ok_cmd:
                await run.io_bound(db.insert_state_change, dev_id, cfg["name"], False)
                server_off_confirm["pending"] = False
                # Update button UI immediately
                toggle_btn.classes(remove="plug-toggle-on plug-toggle-off plug-toggle-warn").classes("plug-toggle-off")
                toggle_btn.set_text("○ OFF")
                if warn_ref:
                    warn_ref.style("display:none")
                card_el.classes(remove="plug-on")
                ui.notify("🔴 Turned OFF", type="negative")
            else:
                ui.notify("⚠ Command failed", type="warning")
                server_off_confirm["pending"] = False

        # Energy strip
        with ui.element("div").classes("plug-energy-row").style("margin-top:14px"):
            with ui.element("div"):
                ref_today_kwh = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY kWh").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            with ui.element("div"):
                ref_today_rm = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY RM EST.").classes("plug-stat-lbl")
            ui.element("div").classes("plug-sep")
            with ui.element("div"):
                ref_total_kwh = ui.label("—").style(
                    "font-family:monospace;font-size:1.1rem;font-weight:600;color:#a5b4fc")
                ui.label("LIFETIME kWh").classes("plug-stat-lbl")

        # Chart
        with ui.element("div").classes("plug-inner-card"):
            ui.label("POWER HISTORY (W)").classes("plug-section-title")
            chart = ui.echart(_plug_chart_options(dev_key)).style("height:180px;width:100%")

        # Controls
        with ui.element("div").classes("plug-inner-card"):
            ui.label("CONTROLS").classes("plug-section-title")

            with ui.row().classes("gap-2 w-full"):
                ui.button("🔒 Lock ON",
                    on_click=lambda: _exec_cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, True), "Child Lock ON")
                ).classes("plug-ctrl-btn")
                ui.button("🔓 Lock OFF",
                    on_click=lambda: _exec_cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, False), "Child Lock OFF")
                ).classes("plug-ctrl-btn")

            with ui.row().classes("gap-2 items-end w-full").style("margin-top:10px"):
                countdown_inp = ui.number(
                    label="Countdown (seconds)", value=0, min=0, max=86400
                ).props("dense outlined").style("flex:1;font-size:.8rem")
                ui.button("Set",
                    on_click=lambda: _exec_cmd(dev_key,
                        lambda: tuya_local.set_countdown(dev_key, int(countdown_inp.value or 0)),
                        f"Timer {int(countdown_inp.value or 0)}s")
                ).props("dense").style("font-size:.72rem;padding:6px 14px")

        # LED control
        with ui.element("div").classes("plug-inner-card"):
            ui.label("INDICATOR LED").classes("plug-section-title")
            with ui.row().classes("gap-2 w-full"):
                for label, val in [("Follow Relay", "relay"), ("Always ON", "pos"), ("Always OFF", "none")]:
                    ui.button(label,
                        on_click=lambda v=val, l=label: _exec_cmd(dev_key,
                            lambda mode=v: tuya_local.set_led_mode(dev_key, mode),
                            f"LED → {l}")
                    ).classes("plug-led-btn")

    async def _exec_cmd(dk, fn, label):
        ok_cmd = await run.io_bound(fn)
        ui.notify(f"✅ {label}" if ok_cmd else f"⚠ {label} failed",
                  type="positive" if ok_cmd else "warning")

    return {
        "card_el":       card_el,
        "conn_dot":      conn_dot,
        "toggle_btn":    toggle_btn,
        "warn_ref":      warn_ref,
        "ref_watts":     ref_watts,
        "ref_voltage":   ref_voltage,
        "ref_current":   ref_current,
        "ref_today_kwh": ref_today_kwh,
        "ref_today_rm":  ref_today_rm,
        "ref_total_kwh": ref_total_kwh,
        "chart":         chart,
        "server_off_confirm": server_off_confirm,
        "dev_key":       dev_key,
        "dev_id":        dev_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — PLUGS
# ─────────────────────────────────────────────────────────────────────────────
def render_plugs_content():

    with ui.column().classes('w-full gap-4 sm:gap-6'):

        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('electrical_services', color='positive')
            ui.label('Device Control').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        with ui.grid().classes('w-full gap-6 grid-cols-1 lg:grid-cols-3'):
            plug_refs      = _build_plug_panel("plug")
            server_refs    = _build_plug_panel("server")
            extension_refs = _build_plug_panel("extension")

    # ── Live update timer ────────────────────────────────────────────────
    def _update_panel(refs: dict):
        dk = refs["dev_key"]
        with plug_lock:
            s  = plug_state[dk]["status"]
            ok = plug_state[dk]["ok"]

        refs["conn_dot"].classes(remove="dot-ok dot-err").classes("dot-ok" if ok else "dot-err")

        if not s:
            return

        on = s["switch"]

        # Toggle button (skip if warn-pending)
        if not refs.get("server_off_confirm", {}).get("pending"):
            refs["toggle_btn"].classes(
                remove="plug-toggle-on plug-toggle-off plug-toggle-warn"
            ).classes("plug-toggle-on" if on else "plug-toggle-off")
            refs["toggle_btn"].set_text("● ON" if on else "○ OFF")

        # Card on/off glow
        if on:
            refs["card_el"].classes(add="plug-on")
        else:
            refs["card_el"].classes(remove="plug-on")

        # Live readings
        refs["ref_watts"].set_text(f"{s['watts']:.1f}")
        refs["ref_voltage"].set_text(f"{s['voltage']:.1f}")
        refs["ref_current"].set_text(f"{s['current_ma']}")
        refs["ref_total_kwh"].set_text(f"{s['add_ele_kwh']:.3f}")

        # Today energy from cache — zero blocking
        with energy_cache_lock:
            today = energy_cache.get(dk, {}).copy()
        refs["ref_today_kwh"].set_text(f"{today.get('total_kwh', 0):.4f}")
        refs["ref_today_rm"].set_text(f"RM {today.get('cost_rm', 0):.4f}")

        # Chart
        new_opts = _plug_chart_options(dk)
        refs["chart"].options.update(new_opts)
        refs["chart"].update()

    def _refresh_plugs():
        _update_panel(plug_refs)
        _update_panel(server_refs)
        _update_panel(extension_refs)

    ui.timer(4.0, _refresh_plugs)

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN SPA PAGE  /
# ─────────────────────────────────────────────────────────────────────────────
