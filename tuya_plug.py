"""
tuya_plug.py  (rewritten)
=========================
NiceGUI dashboard for two smart plugs via tinytuya local LAN.
- Smart Plug  (192.168.1.2)  : full control
- Server Plug (192.168.1.15) : full control + double-confirm OFF

Storage : MariaDB (homelab db)
Metrics : Prometheus on port 2000
Polling : every 10s via background thread
"""

import os
import threading
import time
from collections import deque
from datetime import datetime

from dotenv import load_dotenv
from nicegui import ui
from prometheus_client import Counter, Gauge, start_http_server

import db
import tuya_local

load_dotenv()

POLL_INTERVAL  = 10     # seconds
HISTORY_MAXLEN = 120    # chart data points

# ── Prometheus ─────────────────────────────────────────────────────────────
g_power   = Gauge("tuya_plug_power_watts",     "Power (W)",   ["device"])
g_voltage = Gauge("tuya_plug_voltage_volts",   "Voltage (V)", ["device"])
g_current = Gauge("tuya_plug_current_ma",      "Current (mA)",["device"])
g_energy  = Gauge("tuya_plug_energy_kwh",      "Energy (kWh)",["device"])
g_switch  = Gauge("tuya_plug_switch_state",    "Switch",      ["device"])
c_cmds    = Counter("tuya_commands_total",     "Commands",    ["device", "action"])

# ── Shared state ───────────────────────────────────────────────────────────
state: dict = {
    "plug":   {"status": None, "ok": False, "history": deque(maxlen=HISTORY_MAXLEN)},
    "server": {"status": None, "ok": False, "history": deque(maxlen=HISTORY_MAXLEN)},
}
state_lock       = threading.Lock()
last_poll_wh: dict = {"plug": None, "server": None}  # track prev wh for delta

# ── Polling thread ─────────────────────────────────────────────────────────

def polling_loop():
    global last_poll_wh
    last_poll_time = {"plug": None, "server": None}

    while True:
        for dev_key in ("plug", "server"):
            status = tuya_local.get_status(dev_key)
            now    = time.time()

            with state_lock:
                if status:
                    state[dev_key]["status"] = status
                    state[dev_key]["ok"]     = True
                    state[dev_key]["history"].append({
                        "t": datetime.now().strftime("%H:%M:%S"),
                        "w": status["watts"],
                    })

                    # Prometheus
                    n = status["device_name"]
                    g_power.labels(n).set(status["watts"])
                    g_voltage.labels(n).set(status["voltage"])
                    g_current.labels(n).set(status["current_ma"])
                    g_energy.labels(n).set(status["add_ele_kwh"])
                    g_switch.labels(n).set(1 if status["switch"] else 0)

                    # Wh delta calculation
                    wh_delta = 0.0
                    if last_poll_time[dev_key]:
                        elapsed_h = (now - last_poll_time[dev_key]) / 3600
                        wh_delta  = status["watts"] * elapsed_h

                    last_poll_time[dev_key] = now

                    # Store to MariaDB
                    try:
                        db.insert_energy(
                            device_id=tuya_local.DEVICES[dev_key]["id"],
                            device_name=status["device_name"],
                            watts=status["watts"],
                            wh_delta=wh_delta,
                            voltage=status["voltage"],
                            current_ma=status["current_ma"],
                        )
                        # Refresh daily aggregate every poll
                        db.aggregate_daily(tuya_local.DEVICES[dev_key]["id"])
                    except Exception as e:
                        print(f"[db] insert error ({dev_key}): {e}")
                else:
                    state[dev_key]["ok"] = False

        time.sleep(POLL_INTERVAL)

# ── CSS ────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Epilogue:wght@300;400;500;700&display=swap');

:root {
  --bg:    #08090d; --sur:  #0f1117; --sur2: #171b27;
  --bdr:   #232840; --acc:  #e8ff47; --acc2: #ff6b35;
  --ok:    #34d399; --err:  #f87171;
  --txt:   #dde3f0; --muted:#5a6282;
}
body.lm {
  --bg:#f4f5f0; --sur:#ffffff; --sur2:#eaedf3;
  --bdr:#d1d8e8; --txt:#1a1e30; --muted:#8896b0;
}
*,*::before,*::after { box-sizing:border-box; margin:0; }
body {
  background:var(--bg) !important; color:var(--txt) !important;
  font-family:'Epilogue',sans-serif !important; min-height:100vh;
  transition:background .35s,color .35s;
}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}

.hdr {
  background:var(--sur); border-bottom:1px solid var(--bdr);
  padding:14px 28px; display:flex; align-items:center;
  justify-content:space-between; position:sticky; top:0; z-index:200;
}
.hdr-logo {
  font-family:'IBM Plex Mono',monospace !important;
  font-size:.85rem !important; font-weight:600 !important;
  letter-spacing:.12em; color:var(--acc) !important;
}
.hdr-sub {
  font-size:.62rem !important; color:var(--muted) !important;
  font-family:'IBM Plex Mono',monospace; letter-spacing:.1em; margin-top:2px;
}
.wrap { max-width:1280px; margin:0 auto; padding:28px 18px; }
.dev-grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
@media(max-width:860px){ .dev-grid{ grid-template-columns:1fr; } }

.dev-card {
  background:var(--sur); border:1px solid var(--bdr);
  border-radius:18px; padding:22px;
}
.dev-card.server-card { border-color:#f8714155; }

.card-title {
  font-family:'IBM Plex Mono',monospace;
  font-size:.68rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); margin-bottom:14px;
}
.card { background:var(--sur2); border:1px solid var(--bdr); border-radius:14px; padding:18px 20px; margin-top:14px; }

.status-strip {
  display:flex; flex-wrap:wrap; gap:16px; align-items:center;
  background:var(--sur2); border:1px solid var(--bdr);
  border-radius:12px; padding:16px 20px; margin-bottom:14px;
}
.s-num {
  font-family:'IBM Plex Mono',monospace;
  font-size:1.5rem; font-weight:600; line-height:1;
}
.s-lbl {
  font-size:.58rem; color:var(--muted);
  text-transform:uppercase; letter-spacing:.09em; margin-top:3px;
}
.sep { width:1px; height:38px; background:var(--bdr); }

.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chip {
  background:var(--sur); border:1px solid var(--bdr);
  border-radius:10px; padding:10px 14px; flex:1; min-width:80px;
}
.chip-val {
  font-family:'IBM Plex Mono',monospace;
  font-size:1rem; font-weight:600; line-height:1;
}
.chip-lbl {
  font-size:.58rem; color:var(--muted);
  text-transform:uppercase; letter-spacing:.09em; margin-top:4px;
}

.big-toggle {
  width:100%; padding:12px 0 !important; border-radius:10px !important;
  font-family:'IBM Plex Mono',monospace !important;
  font-size:.82rem !important; letter-spacing:.08em !important;
  transition:all .2s !important;
}
.toggle-on  { background:var(--ok)   !important; color:#04201a !important; }
.toggle-off { background:var(--sur2) !important; color:var(--muted) !important;
              border:1px solid var(--bdr) !important; }
.toggle-warn { background:#92400e !important; color:#fef3c7 !important; }

.ctrl-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:10px; }
.cbtn {
  background:var(--sur) !important; border:1px solid var(--bdr) !important;
  border-radius:9px !important; color:var(--txt) !important;
  font-family:'IBM Plex Mono',monospace !important;
  font-size:.7rem !important; letter-spacing:.05em !important;
  padding:9px 10px !important; transition:border-color .2s,color .2s !important;
}
.cbtn:hover { border-color:var(--acc) !important; color:var(--acc) !important; }
.cbtn-danger:hover { border-color:var(--err) !important; color:var(--err) !important; }

.led-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
.led-btn {
  flex:1; min-width:70px;
  background:var(--sur) !important; border:1px solid var(--bdr) !important;
  border-radius:8px !important; color:var(--muted) !important;
  font-size:.68rem !important; padding:8px 6px !important;
  transition:all .2s !important;
}
.led-btn:hover { border-color:var(--acc2) !important; color:var(--acc2) !important; }

.timer-row { display:flex; gap:8px; align-items:flex-end; margin-top:10px; }

.dot-ok  { width:8px;height:8px;border-radius:50%;background:var(--ok);
           display:inline-block;animation:blink 2.4s infinite; }
.dot-err { width:8px;height:8px;border-radius:50%;background:var(--err);
           display:inline-block; }
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}

.energy-row {
  display:flex; gap:10px; flex-wrap:wrap;
  background:var(--sur2); border:1px solid var(--bdr);
  border-radius:12px; padding:14px 18px; margin-top:14px;
}
.prom-bar {
  background:var(--sur2); border:1px solid var(--bdr);
  border-radius:10px; padding:12px 18px; margin-top:22px;
  font-family:'IBM Plex Mono',monospace;
  font-size:.7rem; color:var(--muted); display:flex; align-items:center; gap:10px;
}
.prom-bar span { color:var(--acc); }
.mode-btn { background:var(--sur2) !important; border:1px solid var(--bdr) !important; border-radius:8px !important; }

.warn-banner {
  background:#7c2d12; border:1px solid #f87171;
  border-radius:10px; padding:12px 16px; margin-top:10px;
  font-family:'IBM Plex Mono',monospace; font-size:.72rem; color:#fca5a5;
  display:none;
}
.warn-banner.visible { display:block; }
"""


# ── Chart builder ──────────────────────────────────────────────────────────

def chart_options(dev_key: str) -> dict:
    with state_lock:
        pts = list(state[dev_key]["history"])
    labels = [p["t"] for p in pts]
    values = [round(p["w"], 1) for p in pts]
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "#0f1117", "borderColor": "#232840",
            "textStyle": {"color": "#dde3f0", "fontFamily": "IBM Plex Mono", "fontSize": 11},
        },
        "grid": {"left": "9%", "right": "3%", "top": "10%", "bottom": "20%"},
        "xAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#5a6282", "fontSize": 9, "rotate": 35},
            "axisLine": {"lineStyle": {"color": "#232840"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#5a6282", "fontSize": 9},
            "splitLine": {"lineStyle": {"color": "#232840", "type": "dashed"}},
        },
        "series": [{
            "data": values, "type": "line", "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#e8ff47", "width": 2},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(232,255,71,.28)"},
                    {"offset": 1, "color": "rgba(232,255,71,.02)"},
                ],
            }},
        }],
    }


# ── Device panel builder ───────────────────────────────────────────────────

def build_device_panel(dev_key: str):
    """Build one full device card and return UI refs for live updates."""
    cfg       = tuya_local.DEVICES[dev_key]
    is_server = cfg["is_server"]
    dev_id    = cfg["id"]

    # Track server OFF confirmation state
    server_off_confirm = {"pending": False}

    card_classes = "dev-card server-card" if is_server else "dev-card"

    with ui.element("div").classes(card_classes):

        # ── Header ──────────────────────────────────────────────────────
        with ui.row().classes("items-center justify-between mb-2"):
            with ui.element("div"):
                ui.label(cfg["name"].upper()).classes("card-title").style("margin-bottom:2px")
                if is_server:
                    ui.label("⚠ SERVER POWER — DOUBLE CONFIRM TO OFF").style(
                        "font-size:.6rem;color:#f87171;font-family:'IBM Plex Mono',monospace;"
                        "letter-spacing:.08em")
            conn_dot  = ui.element("span").classes("dot-ok")

        # ── Status strip ─────────────────────────────────────────────────
        with ui.element("div").classes("status-strip"):
            ref_watts   = ui.label("—").style("font-family:'IBM Plex Mono',monospace;font-size:1.5rem;font-weight:600;color:#e8ff47")
            ui.label("W · POWER").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px;margin-left:2px")
            ui.element("div").classes("sep")
            ref_voltage = ui.label("—").style("font-family:'IBM Plex Mono',monospace;font-size:1.5rem;font-weight:600;color:#a5b4fc")
            ui.label("V · VOLTAGE").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px;margin-left:2px")
            ui.element("div").classes("sep")
            ref_current = ui.label("—").style("font-family:'IBM Plex Mono',monospace;font-size:1.5rem;font-weight:600;color:#fb923c")
            ui.label("mA · CURRENT").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px;margin-left:2px")

        # ── Toggle button ─────────────────────────────────────────────────
        toggle_btn = ui.button("● ON", on_click=lambda: handle_toggle()).classes("big-toggle toggle-on")

        # Warning banner (server only)
        if is_server:
            warn_ref = ui.element("div").classes("warn-banner")
            with warn_ref:
                ui.label("⚠ WARNING: This will cut power to the server. Click OFF again to confirm.")
        else:
            warn_ref = None

        def handle_toggle():
            with state_lock:
                s = state[dev_key]["status"]
            current_on = s["switch"] if s else False

            # Turning ON — no confirmation needed
            if not current_on:
                ok = tuya_local.set_switch(dev_key, True)
                if ok:
                    db.insert_state_change(dev_id, cfg["name"], True)
                    c_cmds.labels(cfg["name"], "on").inc()
                    ui.notify("✅ Turned ON", type="positive")
                    server_off_confirm["pending"] = False
                else:
                    ui.notify("⚠ Command failed", type="warning")
                return

            # Turning OFF
            if is_server and not server_off_confirm["pending"]:
                # First click — show warning
                server_off_confirm["pending"] = True
                toggle_btn.classes(remove="toggle-on toggle-off").classes("toggle-warn")
                toggle_btn.set_text("⚠ CLICK AGAIN TO CONFIRM OFF")
                if warn_ref:
                    warn_ref.style("display:block")
                ui.notify("⚠ Server plug — click again to confirm OFF", type="warning")
                return

            # Second click (or non-server) — actually turn off
            ok = tuya_local.set_switch(dev_key, False)
            if ok:
                db.insert_state_change(dev_id, cfg["name"], False)
                c_cmds.labels(cfg["name"], "off").inc()
                server_off_confirm["pending"] = False
                if warn_ref:
                    warn_ref.style("display:none")
                ui.notify("🔴 Turned OFF", type="negative")
            else:
                ui.notify("⚠ Command failed", type="warning")
                server_off_confirm["pending"] = False

        # ── Energy strip ──────────────────────────────────────────────────
        with ui.element("div").classes("energy-row"):
            with ui.element("div"):
                ref_today_kwh = ui.label("—").style(
                    "font-family:'IBM Plex Mono',monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY kWh").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px")
            ui.element("div").classes("sep")
            with ui.element("div"):
                ref_today_rm = ui.label("—").style(
                    "font-family:'IBM Plex Mono',monospace;font-size:1.1rem;font-weight:600;color:#34d399")
                ui.label("TODAY RM EST.").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px")
            ui.element("div").classes("sep")
            with ui.element("div"):
                ref_total_kwh = ui.label("—").style(
                    "font-family:'IBM Plex Mono',monospace;font-size:1.1rem;font-weight:600;color:#a5b4fc")
                ui.label("LIFETIME kWh").style("font-size:.58rem;color:#5a6282;text-transform:uppercase;letter-spacing:.09em;margin-top:3px")

        # ── Chart ─────────────────────────────────────────────────────────
        with ui.element("div").classes("card"):
            ui.label("POWER HISTORY (W)").classes("card-title")
            chart = ui.echart(chart_options(dev_key)).style("height:180px;width:100%")

        # ── Controls ──────────────────────────────────────────────────────
        with ui.element("div").classes("card"):
            ui.label("CONTROLS").classes("card-title")

            with ui.element("div").classes("ctrl-grid"):
                ui.button("🔒 Lock ON",
                    on_click=lambda: _cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, True), "Child Lock ON")
                ).classes("cbtn")
                ui.button("🔓 Lock OFF",
                    on_click=lambda: _cmd(dev_key, lambda: tuya_local.set_child_lock(dev_key, False), "Child Lock OFF")
                ).classes("cbtn")

            with ui.element("div").classes("timer-row"):
                countdown_inp = ui.number(
                    label="Countdown (seconds)", value=0, min=0, max=86400
                ).props("dense outlined").style("flex:1;font-size:.8rem")
                ui.button("Set",
                    on_click=lambda: _cmd(dev_key,
                        lambda: tuya_local.set_countdown(dev_key, int(countdown_inp.value or 0)),
                        f"Timer {int(countdown_inp.value or 0)}s")
                ).props("dense").style("font-size:.72rem;padding:6px 14px")

        # ── LED ───────────────────────────────────────────────────────────
        with ui.element("div").classes("card"):
            ui.label("INDICATOR LED").classes("card-title")
            with ui.element("div").classes("led-row"):
                for label, val in [("Follow Relay", "relay"), ("Always ON", "pos"), ("Always OFF", "none")]:
                    ui.button(label,
                        on_click=lambda v=val, l=label: _cmd(dev_key,
                            lambda mode=v: tuya_local.set_led_mode(dev_key, mode),
                            f"LED → {l}")
                    ).classes("led-btn")

    def _cmd(dk, fn, label):
        ok = fn()
        c_cmds.labels(cfg["name"], label).inc()
        ui.notify(f"✅ {label}" if ok else f"⚠ {label} failed",
                  type="positive" if ok else "warning")

    # Return refs for UI update timer
    return {
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


# ── Page ───────────────────────────────────────────────────────────────────

@ui.page("/")
def dashboard():
    ui.add_head_html(f"<style>{CUSTOM_CSS}</style>")
    dark = ui.dark_mode()
    dark.enable()

    # Header
    with ui.element("div").classes("hdr"):
        with ui.element("div"):
            ui.label("⚡ SMART PLUG MONITOR").classes("hdr-logo")
            ui.label("LOCAL LAN · TINYTUYA · LIVE").classes("hdr-sub")
        with ui.row().classes("items-center gap-3"):
            def _toggle_dark():
                if dark.value:
                    dark.disable()
                    ui.run_javascript("document.body.classList.add('lm')")
                else:
                    dark.enable()
                    ui.run_javascript("document.body.classList.remove('lm')")
            ui.button(icon="contrast", on_click=_toggle_dark).classes("mode-btn").props("flat dense")

    with ui.element("div").classes("wrap"):
        with ui.element("div").classes("dev-grid"):
            plug_refs   = build_device_panel("plug")
            server_refs = build_device_panel("server")

        with ui.element("div").classes("prom-bar"):
            ui.html(f"📊 Prometheus → <span>http://&lt;host&gt;:2000/metrics</span> · Polling every <span>{POLL_INTERVAL}s</span>")

    # ── Live update timer ──────────────────────────────────────────────────
    def update_panel(refs: dict):
        dk = refs["dev_key"]
        with state_lock:
            s  = state[dk]["status"]
            ok = state[dk]["ok"]

        # Connection dot
        refs["conn_dot"].classes(remove="dot-ok dot-err").classes("dot-ok" if ok else "dot-err")

        if not s:
            return

        # Toggle button (only update if not in warn-pending state)
        if not refs.get("server_off_confirm", {}).get("pending"):
            refs["toggle_btn"].classes(remove="toggle-on toggle-off toggle-warn").classes(
                "toggle-on" if s["switch"] else "toggle-off")
            refs["toggle_btn"].set_text("● ON" if s["switch"] else "○ OFF")

        # Live readings
        refs["ref_watts"].set_text(f"{s['watts']:.1f}")
        refs["ref_voltage"].set_text(f"{s['voltage']:.1f}")
        refs["ref_current"].set_text(f"{s['current_ma']}")
        refs["ref_total_kwh"].set_text(f"{s['add_ele_kwh']:.3f}")

        # Today's energy from DB
        try:
            today = db.get_today_summary(refs["dev_id"])
            refs["ref_today_kwh"].set_text(f"{today['total_kwh']:.4f}")
            refs["ref_today_rm"].set_text(f"RM {today['cost_rm']:.4f}")
        except Exception:
            pass

        # Chart
        refs["chart"].options = chart_options(dk)
        refs["chart"].update()

    def _refresh():
        update_panel(plug_refs)
        update_panel(server_refs)

    ui.timer(2.0, _refresh)


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_http_server(2000)
    print("Prometheus metrics → http://localhost:2000/metrics")

    threading.Thread(target=polling_loop, daemon=True).start()
    print(f"Polling both plugs every {POLL_INTERVAL}s...")

    ui.run(title="Smart Plug Monitor", host="0.0.0.0", port=3003,
           favicon="⚡", dark=True, reload=False)