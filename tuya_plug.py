"""
Tuya Smart Plug Dashboard  ·  Upgraded
=======================================
Preserves: HMAC-SHA256 signing, token refresh, Tuya Cloud REST API,
           Prometheus metrics, background polling thread.

Added:      • Refined dark / light mode toggle (CSS variable system)
            • Power history chart (ECharts, last 120 readings)
            • Real-time UI updates every 1 s from polled data
            • Extended controls: toggle, child-lock, countdown, LED mode, reboot
            • Mobile-friendly responsive layout
            • Toast notifications on commands
            • Connection-status indicator
            • Prometheus scrape-endpoint banner

Install:
    pip install requests prometheus_client nicegui
"""

import hashlib
import hmac
import json
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from nicegui import ui
from prometheus_client import Counter, Gauge, start_http_server

# ════════════════════════════════════════════════════════════════════════════
#  CREDENTIALS  — fill in your values
# ════════════════════════════════════════════════════════════════════════════
CLIENT_ID     = os.getenv("TUYA_CLIENT_ID")
CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET")
DEVICE_ID     = os.getenv("TUYA_DEVICE_ID")
REGION        = os.getenv("TUYA_REGION", "sg")
BASE_URL      = f"https://openapi-sg.iotbing.com/v2.0/cloud/thing/a3f2f187ed028f5920seoc/model"

POLL_INTERVAL   = 30     # seconds between cloud polls
HISTORY_MAXLEN  = 120    # data points kept for chart

# ════════════════════════════════════════════════════════════════════════════
#  PROMETHEUS
# ════════════════════════════════════════════════════════════════════════════
gauge_power_w    = Gauge("tuya_plug_power_watts",        "Current power consumption")
gauge_current_a  = Gauge("tuya_plug_current_amperes",    "Current draw")
gauge_voltage_v  = Gauge("tuya_plug_voltage_volts",      "Current voltage")
gauge_energy_kwh = Gauge("tuya_plug_energy_total_kwh",   "Cumulative energy")
gauge_switch     = Gauge("tuya_plug_switch_state",        "Switch state (1=on)")
counter_cmds     = Counter("tuya_commands_total",         "Commands sent", ["code"])

# ════════════════════════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════════════════════════
access_token: Optional[str] = None
token_expiry: float          = 0


def _calculate_sign(method: str, path: str,
                    params: dict = None, body: dict = None) -> tuple[str, str]:
    t        = str(int(time.time() * 1000))
    sign_str = CLIENT_ID
    if access_token:
        sign_str += access_token
    sign_str += t + method.upper() + path

    if params:
        sign_str += "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    if body:
        sign_str += hashlib.sha256(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()

    sign = hmac.new(
        CLIENT_SECRET.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest().upper()
    return t, sign


def refresh_token() -> bool:
    global access_token, token_expiry
    path   = "/v1.0/token"
    t, sign = _calculate_sign("GET", path, {"grant_type": "1"})
    headers = {"client_id": CLIENT_ID, "sign_method": "HMAC-SHA256",
               "t": t, "sign": sign}
    try:
        r = requests.get(f"{BASE_URL}{path}?grant_type=1",
                         headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("success"):
            res            = data["result"]
            access_token   = res["access_token"]
            token_expiry   = time.time() + res.get("expire_time", 7200) - 300
            print(f"[{datetime.now():%H:%M:%S}] Token refreshed — "
                  f"expires {datetime.fromtimestamp(token_expiry):%H:%M:%S}")
            return True
    except Exception as e:
        print(f"Token refresh failed: {e}")
    return False


def ensure_token() -> bool:
    if not access_token or time.time() > token_expiry:
        return refresh_token()
    return True

# ════════════════════════════════════════════════════════════════════════════
#  API HELPERS
# ════════════════════════════════════════════════════════════════════════════

def tuya_request(method: str, path: str,
                 params: dict = None, json_body: dict = None) -> Optional[Any]:
    if not ensure_token():
        return None
    t, sign = _calculate_sign(method, path, params, json_body)
    headers = {
        "client_id":    CLIENT_ID,
        "access_token": access_token,
        "sign_method":  "HMAC-SHA256",
        "t": t, "sign": sign,
        "Content-Type": "application/json",
    }
    try:
        if method.upper() == "GET":
            r = requests.get(f"{BASE_URL}{path}",
                             headers=headers, params=params, timeout=10)
        else:
            r = requests.post(f"{BASE_URL}{path}",
                              headers=headers, json=json_body, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("success"):
            return data.get("result")
        print(f"API error on {path}: {data}")
    except Exception as e:
        print(f"Request failed {path}: {e}")
    return None


def get_device_status() -> Optional[Dict]:
    result = tuya_request("GET", f"/v1.0/iot-03/devices/{DEVICE_ID}/status")
    if result:
        return {item["code"]: item["value"] for item in result}
    return None


def send_command(commands: List[dict]) -> bool:
    result = tuya_request("POST",
                           f"/v1.0/iot-03/devices/{DEVICE_ID}/commands",
                           json_body={"commands": commands})
    if result is not None:
        for cmd in commands:
            counter_cmds.labels(code=cmd["code"]).inc()
        return True
    return False

# ════════════════════════════════════════════════════════════════════════════
#  SHARED STATE
# ════════════════════════════════════════════════════════════════════════════
last_status: Dict[str, Any] = {}
power_history: deque        = deque(maxlen=HISTORY_MAXLEN)
last_poll_ok: bool          = False
state_lock                  = threading.Lock()

# ════════════════════════════════════════════════════════════════════════════
#  POLLING THREAD
# ════════════════════════════════════════════════════════════════════════════

def polling_loop():
    global last_status, last_poll_ok
    while True:
        status = get_device_status()
        with state_lock:
            if status:
                last_status  = status
                last_poll_ok = True

                gauge_switch.set(1 if status.get("switch_1") else 0)
                gauge_power_w.set(status.get("cur_power",   0) / 10.0)
                gauge_current_a.set(status.get("cur_current", 0) / 1000.0)
                gauge_voltage_v.set(status.get("cur_voltage", 0) / 10.0)
                gauge_energy_kwh.set(status.get("add_ele",    0) / 1000.0)

                power_history.append({
                    "t": datetime.now().strftime("%H:%M:%S"),
                    "w": status.get("cur_power", 0) / 10.0,
                })
            else:
                last_poll_ok = False

        time.sleep(POLL_INTERVAL)

# ════════════════════════════════════════════════════════════════════════════
#  CSS
# ════════════════════════════════════════════════════════════════════════════
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Epilogue:wght@300;400;500;700&display=swap');

:root {
  --bg:       #08090d;
  --sur:      #0f1117;
  --sur2:     #171b27;
  --bdr:      #232840;
  --acc:      #e8ff47;
  --acc2:     #ff6b35;
  --ok:       #34d399;
  --err:      #f87171;
  --txt:      #dde3f0;
  --muted:    #5a6282;
  --glow-acc: rgba(232,255,71,0.12);
}
body.lm {
  --bg:    #f4f5f0;   --sur:  #ffffff;  --sur2: #eaedf3;
  --bdr:   #d1d8e8;   --txt:  #1a1e30; --muted:#8896b0;
  --glow-acc: rgba(232,255,71,0.08);
}
*, *::before, *::after { box-sizing: border-box; margin: 0; }
body {
  background: var(--bg) !important;
  color: var(--txt) !important;
  font-family: 'Epilogue', sans-serif !important;
  min-height: 100vh;
  transition: background .35s, color .35s;
}
::-webkit-scrollbar { width:5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--bdr); border-radius:3px; }

/* ── header ── */
.hdr {
  background: var(--sur);
  border-bottom: 1px solid var(--bdr);
  padding: 14px 28px;
  display: flex; align-items: center; justify-content: space-between;
  position: sticky; top: 0; z-index: 200;
}
.hdr-logo {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: .85rem !important; font-weight: 600 !important;
  letter-spacing: .12em; color: var(--acc) !important;
}
.hdr-sub {
  font-size: .62rem !important; color: var(--muted) !important;
  font-family: 'IBM Plex Mono', monospace; letter-spacing: .1em;
  margin-top: 2px;
}

/* ── body wrapper ── */
.wrap { max-width: 1180px; margin: 0 auto; padding: 28px 18px; }

/* ── status strip ── */
.status-strip {
  background: var(--sur);
  border: 1px solid var(--bdr);
  border-radius: 14px;
  padding: 20px 26px;
  display: flex; flex-wrap: wrap; gap: 20px; align-items: center;
  margin-bottom: 22px;
}
.s-num {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.75rem; font-weight: 600; line-height: 1;
  color: var(--acc);
}
.s-lbl {
  font-size: .62rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: .09em; margin-top: 3px;
}
.sep { width:1px; height:44px; background: var(--bdr); }

/* ── two-column layout ── */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
@media(max-width:740px){ .two-col { grid-template-columns: 1fr; } }

/* ── card ── */
.card {
  background: var(--sur);
  border: 1px solid var(--bdr);
  border-radius: 16px;
  padding: 20px 22px;
}
.card-title {
  font-family: 'IBM Plex Mono', monospace;
  font-size: .68rem; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted);
  margin-bottom: 16px;
}
.card.span2 { grid-column: 1 / -1; }

/* ── stat chips ── */
.chips { display: flex; flex-wrap: wrap; gap: 10px; }
.chip {
  background: var(--sur2);
  border: 1px solid var(--bdr);
  border-radius: 10px;
  padding: 11px 16px;
  flex: 1; min-width: 90px;
}
.chip-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.1rem; font-weight: 600; line-height: 1;
}
.chip-lbl {
  font-size: .6rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: .09em; margin-top: 4px;
}

/* ── big toggle ── */
.big-toggle {
  width: 100%; padding: 14px 0 !important;
  border-radius: 10px !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: .85rem !important; letter-spacing: .08em !important;
  transition: all .2s !important;
}
.toggle-on  { background: var(--ok)  !important; color: #04201a !important; }
.toggle-off { background: var(--sur2) !important; color: var(--muted) !important;
              border: 1px solid var(--bdr) !important; }

/* ── control buttons ── */
.ctrl-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px;
}
@media(max-width:400px){ .ctrl-grid { grid-template-columns: 1fr; } }
.cbtn {
  background: var(--sur2) !important;
  border: 1px solid var(--bdr) !important;
  border-radius: 9px !important;
  color: var(--txt) !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: .72rem !important; letter-spacing: .05em !important;
  padding: 10px 12px !important;
  transition: border-color .2s, color .2s !important;
}
.cbtn:hover { border-color: var(--acc) !important; color: var(--acc) !important; }
.cbtn-danger:hover { border-color: var(--err) !important; color: var(--err) !important; }

/* ── LED group ── */
.led-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.led-btn {
  flex: 1; min-width: 80px;
  background: var(--sur2) !important; border: 1px solid var(--bdr) !important;
  border-radius: 8px !important; color: var(--muted) !important;
  font-size: .7rem !important; padding: 8px 6px !important;
  transition: all .2s !important;
}
.led-btn:hover { border-color: var(--acc2) !important; color: var(--acc2) !important; }

/* ── mode toggle ── */
.mode-btn { background: var(--sur2) !important; border: 1px solid var(--bdr) !important;
            border-radius: 8px !important; }

/* ── connection dot ── */
.dot-ok  { width:8px;height:8px;border-radius:50%;background:var(--ok);
           display:inline-block;animation:blink 2.4s infinite; }
.dot-err { width:8px;height:8px;border-radius:50%;background:var(--err);
           display:inline-block; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.35} }

/* ── chart wrap ── */
.chart-wrap {
  background: var(--sur2);
  border: 1px solid var(--bdr);
  border-radius: 12px;
  padding: 14px 16px;
}
.chart-hdr { font-family:'IBM Plex Mono',monospace; font-size:.62rem;
             color:var(--muted); letter-spacing:.1em; text-transform:uppercase;
             margin-bottom:8px; }

/* ── countdown row ── */
.timer-row { display:flex; gap:10px; align-items:flex-end; margin-top:10px; }

/* ── prometheus bar ── */
.prom-bar {
  background: var(--sur2);
  border: 1px solid var(--bdr);
  border-radius: 10px;
  padding: 12px 18px;
  margin-top: 22px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: .7rem; color: var(--muted);
  display: flex; align-items: center; gap: 10px;
}
.prom-bar span { color: var(--acc); }
"""

# ════════════════════════════════════════════════════════════════════════════
#  CHART OPTIONS BUILDER
# ════════════════════════════════════════════════════════════════════════════

def _chart_options() -> dict:
    with state_lock:
        pts = list(power_history)
    labels = [p["t"] for p in pts]
    values = [round(p["w"], 1) for p in pts]
    return {
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis",
                    "backgroundColor": "#0f1117", "borderColor": "#232840",
                    "textStyle": {"color": "#dde3f0", "fontFamily": "IBM Plex Mono", "fontSize": 11}},
        "grid": {"left": "9%", "right": "3%", "top": "10%", "bottom": "20%"},
        "xAxis": {"type": "category", "data": labels,
                  "axisLabel": {"color": "#5a6282", "fontSize": 9, "rotate": 35},
                  "axisLine": {"lineStyle": {"color": "#232840"}}},
        "yAxis": {"type": "value",
                  "axisLabel": {"color": "#5a6282", "fontSize": 9},
                  "splitLine": {"lineStyle": {"color": "#232840", "type": "dashed"}}},
        "series": [{
            "data": values, "type": "line", "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#e8ff47", "width": 2},
            "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                    "colorStops": [{"offset": 0,   "color": "rgba(232,255,71,.28)"},
                                                   {"offset": 1,   "color": "rgba(232,255,71,.02)"}]}},
        }],
    }

# ════════════════════════════════════════════════════════════════════════════
#  PAGE
# ════════════════════════════════════════════════════════════════════════════

@ui.page("/")
def dashboard():
    ui.add_head_html(f"<style>{CUSTOM_CSS}</style>")
    dark = ui.dark_mode()
    dark.enable()

    # ── HEADER ────────────────────────────────────────────────────────────
    with ui.element("div").classes("hdr"):
        with ui.element("div"):
            ui.label("⚡ TUYA SMART PLUG").classes("hdr-logo")
            ui.label("CLOUD DASHBOARD  ·  LIVE MONITOR").classes("hdr-sub")

        with ui.row().classes("items-center gap-3"):
            conn_dot  = ui.element("span").classes("dot-ok")
            conn_text = ui.label("CONNECTED").style(
                "font-family:'IBM Plex Mono',monospace;font-size:.62rem;"
                "color:#34d399;letter-spacing:.1em")

            def _toggle_dark():
                if dark.value:
                    dark.disable()
                    ui.run_javascript("document.body.classList.add('lm')")
                else:
                    dark.enable()
                    ui.run_javascript("document.body.classList.remove('lm')")

            ui.button(icon="contrast", on_click=_toggle_dark).classes("mode-btn").props("flat dense")

    # ── BODY ──────────────────────────────────────────────────────────────
    with ui.element("div").classes("wrap"):

        # ── Summary strip ────────────────────────────────────────────────
        with ui.element("div").classes("status-strip"):
            refs: dict = {}
            for key, label, unit, color in [
                ("power",   "Power",   "W",   "#e8ff47"),
                ("voltage", "Voltage", "V",   "#a5b4fc"),
                ("current", "Current", "A",   "#fb923c"),
                ("energy",  "Energy",  "kWh", "#34d399"),
            ]:
                with ui.element("div"):
                    refs[key] = ui.label("—").style(
                        f"font-family:'IBM Plex Mono',monospace;font-size:1.75rem;"
                        f"font-weight:600;line-height:1;color:{color}")
                    ui.label(f"{label}  ·  {unit}").style(
                        "font-size:.6rem;color:#5a6282;text-transform:uppercase;"
                        "letter-spacing:.09em;margin-top:3px")
                if key != "energy":
                    ui.element("div").classes("sep")

        # ── Two-column grid ───────────────────────────────────────────────
        with ui.element("div").classes("two-col"):

            # ── LEFT: Status card ─────────────────────────────────────────
            with ui.element("div").classes("card"):
                ui.label("DEVICE STATUS").classes("card-title")

                # Power toggle
                toggle_btn = ui.button("● DEVICE ON", on_click=lambda: _do_toggle()).classes(
                    "big-toggle toggle-on")

                def _do_toggle():
                    with state_lock:
                        current = last_status.get("switch_1", False)
                    new_state = not current
                    ok = send_command([{"code": "switch_1", "value": new_state}])
                    if ok:
                        with state_lock:
                            last_status["switch_1"] = new_state
                        ui.notify(f"{'✅ Turned ON' if new_state else '🔴 Turned OFF'}",
                                  type="positive" if new_state else "negative")
                    else:
                        ui.notify("⚠ Command failed", type="warning")

                ui.element("div").style("height:14px")

                # Stat chips
                with ui.element("div").classes("chips"):
                    chip_refs: dict = {}
                    for ck, cl, col in [
                        ("power",   "Watts",    "#e8ff47"),
                        ("voltage", "Voltage V","#a5b4fc"),
                        ("current", "Amps A",   "#fb923c"),
                        ("energy",  "kWh Total","#34d399"),
                    ]:
                        with ui.element("div").classes("chip"):
                            chip_refs[ck] = ui.label("—").style(
                                f"font-family:'IBM Plex Mono',monospace;"
                                f"font-size:1.1rem;font-weight:600;line-height:1;color:{col}")
                            ui.label(cl).style(
                                "font-size:.59rem;color:#5a6282;text-transform:uppercase;"
                                "letter-spacing:.09em;margin-top:4px")

            # ── RIGHT: Chart card ─────────────────────────────────────────
            with ui.element("div").classes("card"):
                ui.label("POWER HISTORY  (W)").classes("card-title")
                with ui.element("div").classes("chart-wrap"):
                    chart = ui.echart(_chart_options()).style("height:210px;width:100%")

            # ── LEFT-BOTTOM: Controls card ────────────────────────────────
            with ui.element("div").classes("card"):
                ui.label("CONTROLS").classes("card-title")

                # Child lock row
                with ui.element("div").classes("ctrl-grid"):
                    ui.button(
                        "🔒 Lock ON",
                        on_click=lambda: _cmd([{"code": "child_lock", "value": True}], "Child Lock ON")
                    ).classes("cbtn")
                    ui.button(
                        "🔓 Lock OFF",
                        on_click=lambda: _cmd([{"code": "child_lock", "value": False}], "Child Lock OFF")
                    ).classes("cbtn")

                # Countdown
                with ui.element("div").classes("timer-row"):
                    countdown_inp = ui.number(
                        label="Countdown (seconds)", value=0, min=0, max=86400
                    ).props("dense outlined").style("flex:1;font-size:.8rem")
                    ui.button(
                        "Set",
                        on_click=lambda: _cmd(
                            [{"code": "countdown_1", "value": int(countdown_inp.value or 0)}],
                            f"Timer {int(countdown_inp.value or 0)}s"
                        )
                    ).props("dense").style("font-size:.72rem;padding:6px 14px")

                # Reboot
                ui.element("div").style("height:10px")
                ui.button(
                    "⚡ Reboot Device",
                    on_click=lambda: _cmd([{"code": "reset_factory", "value": False}], "Reboot")
                ).classes("cbtn cbtn-danger").style("width:100%")

            # ── RIGHT-BOTTOM: LED card ────────────────────────────────────
            with ui.element("div").classes("card"):
                ui.label("INDICATOR LED").classes("card-title")
                ui.label("Controls the ring LED behaviour on the plug.").style(
                    "font-size:.72rem;color:#5a6282;margin-bottom:4px")
                with ui.element("div").classes("led-row"):
                    for label, value in [("Follow Relay", "relay"), ("Always ON", "pos"), ("Always OFF", "none")]:
                        ui.button(
                            label,
                            on_click=lambda v=value, l=label: _cmd(
                                [{"code": "light_mode", "value": v}], f"LED → {l}")
                        ).classes("led-btn")

                ui.element("div").style("height:14px")
                ui.label("LAST POLL").style(
                    "font-family:'IBM Plex Mono',monospace;font-size:.6rem;"
                    "color:#5a6282;letter-spacing:.09em;text-transform:uppercase")
                poll_time_lbl = ui.label("—").style(
                    "font-family:'IBM Plex Mono',monospace;font-size:.82rem;color:#dde3f0")

        # ── Prometheus bar ────────────────────────────────────────────────
        with ui.element("div").classes("prom-bar"):
            ui.html("📊 Prometheus metrics available at "
                    "<span>http://&lt;host&gt;:8000/metrics</span>  ·  "
                    f"Polling every <span>{POLL_INTERVAL}s</span>")

    # ── COMMAND HELPER ─────────────────────────────────────────────────────
    def _cmd(commands: list, label: str):
        ok = send_command(commands)
        ui.notify(
            f"✅ {label}" if ok else f"⚠ {label} failed",
            type="positive" if ok else "warning"
        )

    # ── REAL-TIME UI REFRESH ───────────────────────────────────────────────
    def _update_ui():
        with state_lock:
            s    = dict(last_status)
            ok   = last_poll_ok
            hist = list(power_history)

        on = s.get("switch_1", False)

        # connection indicator
        conn_dot.classes(remove="dot-ok dot-err").classes("dot-ok" if ok else "dot-err")
        conn_text.set_text("CONNECTED" if ok else "OFFLINE")
        conn_text.style(f"font-family:'IBM Plex Mono',monospace;font-size:.62rem;"
                        f"letter-spacing:.1em;color:{'#34d399' if ok else '#f87171'}")

        # toggle button
        toggle_btn.classes(remove="toggle-on toggle-off").classes(
            "toggle-on" if on else "toggle-off")
        toggle_btn.set_text("● DEVICE ON" if on else "○ DEVICE OFF")

        # derived values
        pw  = s.get("cur_power",   0) / 10.0
        vv  = s.get("cur_voltage", 0) / 10.0
        ca  = s.get("cur_current", 0) / 1000.0
        en  = s.get("add_ele",     0) / 1000.0

        for key, val, fmt in [
            ("power",   pw,  ".1f"),
            ("voltage", vv,  ".1f"),
            ("current", ca,  ".3f"),
            ("energy",  en,  ".3f"),
        ]:
            refs[key].set_text(f"{val:{fmt}}")
            chip_refs[key].set_text(f"{val:{fmt}}")

        # chart
        if hist:
            chart.options = _chart_options()
            chart.update()

        # last poll time
        if hist:
            poll_time_lbl.set_text(hist[-1]["t"])

    ui.timer(1.0, _update_ui)


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    start_http_server(2000)
    print("Prometheus metrics → http://localhost:2000/metrics")

    refresh_token()
    threading.Thread(target=polling_loop, daemon=True).start()

    ui.run(title="Tuya Plug Dashboard", host="0.0.0.0", port=8080,
           favicon="⚡", dark=True, reload=False)
