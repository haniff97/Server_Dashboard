#!/usr/bin/env python3
"""
Custom Homelab Dashboard - DESIGN MODE
Built with NiceGUI + Mock Data (Simulating tinytuya local LAN + MariaDB)
Pages: / (Server) | /energy (Energy Monitor) | /plugs (Smart Plugs)
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.tnb_tariff import calculate_tnb_cost, allocate_tnb_cost
import asyncio
import threading
import time
import random
from collections import deque
from typing import Any, Dict, Optional
from datetime import datetime

from nicegui import ui, app

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — system
# ─────────────────────────────────────────────────────────────────────────────
system_stats = {
    'cpu_percent': 0, 'cpu_temp': 0,
    'memory_percent': 0, 'memory_used_gb': 0, 'memory_total_gb': 16.0,
    'nvme_percent': 0, 'nvme_used_gb': 0, 'nvme_total_gb': 1000.0, 'nvme_temp': 0,
    'hdd_percent': 0, 'hdd_used_gb': 0, 'hdd_total_gb': 4000.0, 'hdd_status': 'idle',
}
iot_devices: dict = {}
ai_insights = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update = ""

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — Network (MOCKED)
# ─────────────────────────────────────────────────────────────────────────────
network_state = {
    "health": "GOOD",
    "targets": {
        "Google": {"latency": 15.2, "packet_loss": 0.0, "status": "ok", "history": deque([15.0]*60, maxlen=60)},
        "fast.com": {"latency": 12.4, "packet_loss": 0.0, "status": "ok", "history": deque([12.0]*60, maxlen=60)},
        "youtube.com": {"latency": 18.5, "packet_loss": 0.0, "status": "ok", "history": deque([18.0]*60, maxlen=60)}
    },
    "route_log": [
        f"{datetime.now().strftime('%H:%M:%S')} - Initial routes established.",
        f"{datetime.now().strftime('%H:%M:%S')} - No anomalies detected."
    ],
    "ai_insights": "🤖 Network AI Active...\n💡 All routes stable. Latency is optimal."
}

def update_network_mock_data():
    """Simulate network metrics"""
    for target, data in network_state["targets"].items():
        data["latency"] = max(5.0, min(150.0, data["latency"] + random.uniform(-2, 2)))
        data["history"].append(data["latency"])

        if random.random() > 0.98:
            data["packet_loss"] = round(random.uniform(1.0, 5.0), 1)
            data["status"] = "warn"
            network_state["health"] = "WARNING"
            network_state["route_log"].insert(0, f"{datetime.now().strftime('%H:%M:%S')} - Packet loss ({data['packet_loss']}%) detected on {target}")
            network_state["ai_insights"] = f"⚠️ Anomaly Detected!\nPacket loss on {target} suggests ISP congestion or hop failure. Traceroute triggered."
        else:
            data["packet_loss"] = 0.0
            data["status"] = "ok"

    if all(d["status"] == "ok" for d in network_state["targets"].values()):
        network_state["health"] = "GOOD"
        network_state["ai_insights"] = "🤖 Network AI Active...\n💡 All routes stable. Latency is optimal."

    if len(network_state["route_log"]) > 10:
        network_state["route_log"].pop()

# ─────────────────────────────────────────────────────────────────────────────
#  MOCK DEVICE CONFIG (Homelab & Smart Home Fleet)
# ─────────────────────────────────────────────────────────────────────────────
MOCK_DEVICES = {
    "server": {
        "name":        "Homelab Server",
        "id":          "mock_server_001",
        "ip":          "192.168.1.15",
        "zone":        "Server Rack",
        "icon":        "dns",
        "is_server":   True,
        "is_critical": True,
        "watt_min":    85.0,
        "watt_max":    165.0,
        "base_kwh":    2.850,
        "base_month_kwh": 88.0,
    },
    "nas_backup": {
        "name":        "Synology NAS",
        "id":          "mock_nas_002",
        "ip":          "192.168.1.18",
        "zone":        "Server Rack",
        "icon":        "storage",
        "is_server":   False,
        "is_critical": True,
        "watt_min":    32.0,
        "watt_max":    58.0,
        "base_kwh":    0.920,
        "base_month_kwh": 28.5,
    },
    "net_rack": {
        "name":        "POE Switch & AP",
        "id":          "mock_net_003",
        "ip":          "192.168.1.10",
        "zone":        "Networking",
        "icon":        "router",
        "is_server":   False,
        "is_critical": True,
        "watt_min":    28.0,
        "watt_max":    46.0,
        "base_kwh":    0.740,
        "base_month_kwh": 22.8,
    },
    "workstation": {
        "name":        "Developer Workstation",
        "id":          "mock_pc_004",
        "ip":          "192.168.1.25",
        "zone":        "Office / Lab",
        "icon":        "desktop_windows",
        "is_server":   False,
        "is_critical": False,
        "watt_min":    65.0,
        "watt_max":    220.0,
        "base_kwh":    1.850,
        "base_month_kwh": 54.0,
    },
    "desk_lights": {
        "name":        "Monitors & Lighting",
        "id":          "mock_mon_005",
        "ip":          "192.168.1.26",
        "zone":        "Office / Lab",
        "icon":        "tungsten",
        "is_server":   False,
        "is_critical": False,
        "watt_min":    25.0,
        "watt_max":    65.0,
        "base_kwh":    0.580,
        "base_month_kwh": 18.2,
    },
    "plug": {
        "name":        "Workbench Test Bench",
        "id":          "mock_plug_006",
        "ip":          "192.168.1.2",
        "zone":        "Office / Lab",
        "icon":        "handyman",
        "is_server":   False,
        "is_critical": False,
        "watt_min":    8.0,
        "watt_max":    38.0,
        "base_kwh":    0.320,
        "base_month_kwh": 9.5,
    },
    "printer3d": {
        "name":        "Bambu 3D Printer",
        "id":          "mock_print_007",
        "ip":          "192.168.1.35",
        "zone":        "Workshop",
        "icon":        "precision_manufacturing",
        "is_server":   False,
        "is_critical": False,
        "watt_min":    95.0,
        "watt_max":    280.0,
        "base_kwh":    1.620,
        "base_month_kwh": 42.0,
    },
    "living_tv": {
        "name":        "Entertainment Center",
        "id":          "mock_tv_008",
        "ip":          "192.168.1.42",
        "zone":        "Living Room",
        "icon":        "tv",
        "is_server":   False,
        "is_critical": False,
        "watt_min":    45.0,
        "watt_max":    135.0,
        "base_kwh":    0.980,
        "base_month_kwh": 31.0,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL STATE — Smart Plugs (MOCKED tinytuya)
# ─────────────────────────────────────────────────────────────────────────────
PLUG_POLL_INTERVAL = 2  # faster for design preview

plug_state: Dict[str, Dict[str, Any]] = {
    dev_key: {"status": None, "ok": True, "history": deque(maxlen=120)}
    for dev_key in MOCK_DEVICES
}
plug_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM HELPERS (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
def get_cpu_temp():
    return round(random.uniform(40.0, 65.0), 1)

def get_nvme_temp():
    return round(random.uniform(30.0, 50.0), 1)

def get_hdd_status():
    return 'active' if random.random() > 0.7 else 'idle'

# ─────────────────────────────────────────────────────────────────────────────
#  PLUG POLLING THREAD (MOCK — simulates tinytuya local LAN across all devices)
# ─────────────────────────────────────────────────────────────────────────────
def plug_polling_loop():
    """Mock polling loop that generates realistic plug data for all devices."""
    while True:
        for dev_key, cfg in MOCK_DEVICES.items():
            with plug_lock:
                prev = plug_state[dev_key]["status"]
                is_on = prev["switch"] if prev else True

                if is_on:
                    w_min = cfg.get("watt_min", 10.0)
                    w_max = cfg.get("watt_max", 100.0)
                    watts = round(random.uniform(w_min, w_max), 1)
                else:
                    watts = 0.0

                voltage = round(random.uniform(228.0, 232.0), 1)
                current_ma = int(watts / voltage * 1000) if voltage > 0 else 0
                add_ele_kwh = (prev["add_ele_kwh"] + (watts * (PLUG_POLL_INTERVAL / 3600.0) / 1000.0)) if prev else cfg.get("base_kwh", 1.450)

                status = {
                    "device_key":  dev_key,
                    "device_name": cfg["name"],
                    "switch":      is_on,
                    "watts":       watts,
                    "voltage":     voltage,
                    "current_ma":  current_ma,
                    "add_ele_kwh": round(add_ele_kwh, 4),
                    "fault":       0,
                }

                plug_state[dev_key]["status"] = status
                plug_state[dev_key]["ok"]     = random.random() > 0.02
                plug_state[dev_key]["history"].append({
                    "t": datetime.now().strftime("%H:%M:%S"),
                    "w": watts,
                })

        time.sleep(PLUG_POLL_INTERVAL)

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM METRICS ASYNC LOOP (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
async def update_metrics():
    while True:
        global system_stats, iot_devices, last_update
        try:
            system_stats['cpu_percent'] = round(random.uniform(10.0, 80.0), 1)
            system_stats['cpu_temp']    = get_cpu_temp()

            system_stats['memory_used_gb']  = round(random.uniform(4.0, 12.0), 2)
            system_stats['memory_percent']  = round(system_stats['memory_used_gb'] / system_stats['memory_total_gb'] * 100, 1)

            system_stats['nvme_used_gb']  = round(random.uniform(200.0, 800.0), 1)
            system_stats['nvme_percent']  = round(system_stats['nvme_used_gb'] / system_stats['nvme_total_gb'] * 100, 1)
            system_stats['nvme_temp'] = get_nvme_temp()

            system_stats['hdd_used_gb']  = round(random.uniform(1000.0, 3500.0), 1)
            system_stats['hdd_percent']  = round(system_stats['hdd_used_gb'] / system_stats['hdd_total_gb'] * 100, 1)
            system_stats['hdd_status'] = get_hdd_status()

            # Mock multi-room ESP32 IoT devices
            iot_devices['esp32-server-closet'] = {
                'name': 'Server Closet',
                'zone': 'Server Rack',
                'temperature': round(random.uniform(25.0, 28.5), 1),
                'humidity': round(random.uniform(41.0, 47.0), 1),
                'rssi': -52,
                'status': 'Optimal'
            }
            iot_devices['esp32-office-lab'] = {
                'name': 'Office & Lab',
                'zone': 'Office / Lab',
                'temperature': round(random.uniform(22.0, 24.5), 1),
                'humidity': round(random.uniform(46.0, 54.0), 1),
                'rssi': -61,
                'status': 'Good'
            }
            iot_devices['esp32-workshop'] = {
                'name': 'Workshop Area',
                'zone': 'Workshop',
                'temperature': round(random.uniform(23.5, 27.0), 1),
                'humidity': round(random.uniform(50.0, 60.0), 1),
                'rssi': -67,
                'status': 'Good'
            }

            last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Metrics error: {e}")
        await asyncio.sleep(2)

# ─────────────────────────────────────────────────────────────────────────────
#  AI INSIGHTS ASYNC LOOP (MOCK)
# ─────────────────────────────────────────────────────────────────────────────
async def update_ai_insights():
    global ai_insights
    while True:
        try:
            await asyncio.sleep(5)
            if random.random() > 0.7:
                ai_insights = "Concerns Detected (MOCK):\nHigh CPU usage detected\n\nRecommendation: Check active processes\nPlug power draw is within normal range."
            else:
                ai_insights = "All systems healthy (MOCK)\nPerformance: Optimal\nNo immediate concerns"
        except Exception as e:
            ai_insights = f"❌ AI Mock Error: {e}"
        await asyncio.sleep(15)

# ─────────────────────────────────────────────────────────────────────────────
#  MOCK DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
DEVICE_DAILY_BASE_KWH = {
    "mock_server_001": 2.45,
    "mock_nas_002":    0.85,
    "mock_net_003":    0.68,
    "mock_pc_004":     1.92,
    "mock_mon_005":    0.54,
    "mock_plug_006":   0.22,
    "mock_print_007":  1.35,
    "mock_tv_008":     0.95,
}

def mock_calculate_tnb_cost(kwh: float) -> float:
    """Allocate cost using the mock fleet's shared calendar-month total."""
    monthly = sum(DEVICE_DAILY_BASE_KWH.get(cfg['id'], .5) + cfg.get('base_month_kwh', 25)
                  for cfg in MOCK_DEVICES.values())
    return allocate_tnb_cost(kwh, max(monthly, kwh))

def mock_get_today_summary(dev_id: str) -> dict:
    """Simulate db.get_today_summary() with consistent TNB cost calculation."""
    base_kwh = DEVICE_DAILY_BASE_KWH.get(dev_id, 0.50)
    cost = mock_calculate_tnb_cost(base_kwh)
    return {
        "total_wh":  round(base_kwh * 1000, 2),
        "total_kwh": round(base_kwh, 4),
        "cost_rm":   round(cost, 4),
    }

# ─────────────────────────────────────────────────────────────────────────────
#  SHARED STYLES
# ─────────────────────────────────────────────────────────────────────────────
def add_common_styles():
    ui.add_head_html(r'''
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        :root {
            --canvas:#f3f5f8; --surface:#ffffff; --inset:#f7f9fc;
            --stroke:#e2e8f0; --hover-stroke:#c1cedc;
            --ink:#172437; --muted:#607087; --subtle:#687991;
            --brand:#087f8c; --brand-soft:#e7f5f6; --brand-ink:#076773;
            --shadow:0 3px 6px rgba(26,45,72,.025),0 12px 32px rgba(26,45,72,.035);
            --q-primary:#087f8c; --q-secondary:#6557b8; --q-accent:#a66328;
            --q-positive:#16805e; --q-warning:#b77915; --q-negative:#c23d58;
        }
        body.body--dark {
            --canvas:#101720; --surface:#192330; --inset:#202d3d;
            --stroke:#2b3a4e; --hover-stroke:#405671;
            --ink:#edf3fa; --muted:#a6b5c9; --subtle:#99aac0;
            --brand:#6dd5de; --brand-soft:#203d48; --brand-ink:#9ce7ed;
            --shadow:0 10px 30px rgba(0,0,0,.12);
            --q-primary:#6dd5de!important; --q-secondary:#b5a7f4!important; --q-accent:#e5b180!important;
            --q-positive:#65d5ae!important; --q-warning:#edc478!important; --q-negative:#f18ca2!important;
            color-scheme:dark;
        }
        body { font-family:'Inter',system-ui,sans-serif; background:var(--canvas); color:var(--ink);
            min-height:100vh; -webkit-font-smoothing:antialiased; }
        .glass-card, .plug-card, .plug-card-modern, .split-card, .iot-plug-tile {
            background:var(--surface); border:1px solid var(--stroke);
            border-radius:20px; box-shadow:var(--shadow); transition:border-color .18s ease;
        }
        .glass-card:hover, .plug-card-modern:hover, .iot-plug-tile:hover {
            border-color:var(--hover-stroke); transform:none;
        }
        .plug-card, .plug-card-modern, .split-card { overflow:hidden; }
        .iot-plug-tile { border-radius:16px; padding:14px; background:var(--inset); box-shadow:none; }
        .glass-header { background:color-mix(in srgb,var(--canvas) 92%,transparent);
            backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
            border-bottom:1px solid var(--stroke); color:var(--ink); }
        .dark-highlight-card { background:linear-gradient(125deg,#0c5361,#153349);
            color:#f0fdfa; border:1px solid #285266; border-radius:20px; box-shadow:var(--shadow); }
        .split-card { display:flex; }
        .split-left { background:var(--brand-soft); color:var(--brand-ink); padding:24px; flex:1; }
        .split-right { background:var(--surface); padding:24px; flex:2; }
        .plug-stat-strip, .plug-energy-row { display:flex; flex-wrap:wrap; gap:16px;
            background:var(--inset); padding:16px 18px; border-radius:14px; }
        .plug-stat-strip { align-items:center; }
        .plug-inner-card { background:var(--inset); border:1px solid var(--stroke);
            border-radius:14px; padding:16px 18px; margin-top:12px; }
        .plug-stat-num, .stat-value { font-size:1.5rem; font-weight:700; line-height:1.2; color:var(--ink); }
        .stat-value { color:var(--brand); }
        .plug-stat-lbl, .stat-label, .plug-section-title { font-size:11px; font-weight:600;
            color:var(--muted); letter-spacing:.06em; text-transform:uppercase; }
        .plug-section-title { margin-bottom:10px; }
        .plug-sep { width:1px; height:36px; background:var(--stroke); }
        .plug-card-modern.plug-active, .plug-card.plug-on { border-color:color-mix(in srgb,var(--brand) 35%,var(--stroke)); }
        .plug-card-modern.plug-critical { border-left:3px solid var(--q-warning); }
        .plug-switch-btn, .plug-toggle, .plug-ctrl-btn, .plug-led-btn, .filter-chip-btn {
            font-family:inherit!important; border-radius:10px!important; font-weight:600!important;
            box-shadow:none!important; letter-spacing:0!important;
        }
        .plug-switch-btn { padding:7px 16px!important; font-size:12px!important; }
        .plug-switch-on, .plug-toggle-on { background:var(--brand-soft)!important;
            color:var(--brand-ink)!important; border:1px solid color-mix(in srgb,var(--brand) 25%,transparent)!important; }
        .plug-switch-off, .plug-toggle-off { background:var(--inset)!important; color:var(--muted)!important;
            border:1px solid var(--stroke)!important; }
        .plug-switch-warn, .plug-toggle-warn { background:var(--q-negative)!important; color:var(--canvas)!important; }
        .plug-toggle { width:100%; padding:14px 0!important; }
        .plug-ctrl-btn, .plug-led-btn { background:var(--inset)!important; color:var(--ink)!important;
            border:1px solid var(--stroke)!important; padding:9px 14px!important; font-size:12px!important; }
        .plug-led-btn { flex:1; min-width:70px; }
        .plug-ctrl-btn:hover, .plug-led-btn:hover { border-color:var(--brand)!important; }
        .filter-chip-btn { padding:4px 12px!important; font-size:12px!important; }
        .pulse-dot-online, .pulse-dot-offline, .dot-ok, .dot-err {
            display:inline-block; width:8px; height:8px; border-radius:50%; box-shadow:none; }
        .pulse-dot-online, .dot-ok { background:var(--q-positive); }
        .pulse-dot-offline, .dot-err { background:var(--q-negative); }
        .plug-warn-banner { display:none; background:var(--brand-soft); color:var(--ink);
            border:1px solid var(--q-warning); border-radius:12px; padding:12px 16px; margin-top:10px; font-size:12px; }
        .plug-warn-banner.visible { display:block; }
        .q-btn-group { background:var(--inset)!important; padding:4px; border:1px solid var(--stroke)!important;
            border-radius:14px!important; box-shadow:none!important; }
        body .q-btn-group .q-btn { color:var(--muted)!important; border-radius:10px!important;
            font-weight:600!important; font-size:12px; letter-spacing:0; }
        body .q-btn-group .q-btn.bg-primary { background:var(--surface)!important;
            color:var(--brand-ink)!important; box-shadow:0 2px 5px rgba(0,0,0,.07)!important; }
        .q-btn { font-variant-numeric:tabular-nums; }
        .glass-card .q-linear-progress__model { opacity:.28; }
        .glass-card .q-linear-progress__track { opacity:.08; }
        .glass-card .q-separator { background:var(--stroke)!important; }
        .q-btn:focus-visible { outline:2px solid var(--brand); outline-offset:3px; }
        .q-field--outlined .q-field__control { border-radius:12px!important; background:var(--inset); }
        .q-field--outlined .q-field__control:before { border-color:var(--stroke)!important; background:transparent!important; }
        .q-field:hover .q-field__control:before { border-color:var(--hover-stroke)!important; }
        .glass-menu { background:var(--surface)!important; color:var(--ink)!important;
            border:1px solid var(--stroke)!important; border-radius:14px!important; box-shadow:var(--shadow)!important; padding:4px; }
        .glass-menu .q-item { border-radius:9px; margin:2px; }
        .glass-menu .q-item:hover, .glass-menu .q-item--active { background:var(--brand-soft)!important; color:var(--brand-ink)!important; }
        /* Existing utility colors use matching contrast in either theme. */
        [class~="text-slate-400"], [class~="text-slate-500"], [class~="text-slate-600"] { color:var(--muted)!important; }
        [class~="text-slate-700"], [class~="text-slate-800"], [class~="text-slate-900"] { color:var(--ink)!important; }
        [class~="text-blue-500"], [class~="text-blue-600"] { color:var(--brand)!important; }
        [class~="text-emerald-500"], [class~="text-teal-600"] { color:var(--q-positive)!important; }
        [class~="text-amber-500"], [class~="text-orange-500"] { color:var(--q-warning)!important; }
        [class~="text-rose-500"] { color:var(--q-negative)!important; }
        [class~="text-purple-700"] { color:var(--q-secondary)!important; }
        .glass-card [class~="bg-slate-200"], .glass-header [class~="bg-slate-200"] { background:var(--inset)!important; }
        .animate-pulse { animation:none!important; }
        .hover\:scale-\[1\.02\]:hover { transform:none!important; }
        @media (prefers-reduced-motion:reduce) { * { transition:none!important; animation:none!important; } }


        /* Horizon: one accent, quiet surfaces, generous typography. */
        :root { --canvas:#f4f5f7; --surface:#ffffff; --inset:#f6f7f9; --stroke:#e5e8ed;
            --ink:#202935; --muted:#687482; --brand:#426caa; --brand-soft:#edf2f9; --brand-ink:#345d95;
            --shadow:0 3px 14px rgba(25,40,65,.025); }
        body.body--dark { --canvas:#101317; --surface:#1a1f26; --inset:#212831; --stroke:#303842;
            --ink:#eef1f5; --muted:#a1acb9; --brand:#a8c4ed; --brand-soft:#2b3a4e; --brand-ink:#c2d6f5;
            --shadow:none; --q-primary:#a8c4ed!important; --q-positive:#80c1a7!important; }
        body .glass-card, body .plug-card-modern, body .split-card {
            background:var(--surface)!important; border:1px solid var(--stroke)!important;
            border-radius:20px; box-shadow:var(--shadow)!important;
        }
        .q-layout__section--marginal.app-topbar { background:var(--canvas); color:var(--ink); }
        .app-topbar { height:88px; padding:18px max(24px,calc((100vw - 1240px)/2)); border-bottom:1px solid var(--stroke); box-shadow:none; }
        .brand-symbol { width:37px; height:37px; border-radius:12px; background:var(--ink);
            color:var(--surface); display:grid; place-items:center; }
        .brand-name { font-size:21px; font-weight:650; letter-spacing:-.8px; line-height:1.1; }
        .brand-caption { color:var(--muted); font-size:8px; font-weight:600; letter-spacing:1.5px; margin-top:5px; }
        .shell-update { font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
        .theme-button { color:var(--muted); background:var(--surface); border:1px solid var(--stroke); }
        body .workspace-nav.q-btn-group { display:flex; gap:4px; background:var(--inset)!important;
            padding:5px; border:1px solid var(--stroke)!important; border-radius:14px!important; box-shadow:none!important; }
        body .workspace-nav.q-btn-group .q-btn { min-height:37px; padding:0 20px;
            border-radius:9px!important; font-size:12px; font-weight:500!important; }
        body .workspace-nav.q-btn-group .q-btn.bg-primary { background:var(--surface)!important;
            --q-primary:var(--surface)!important; color:var(--ink)!important; box-shadow:0 2px 5px rgba(0,0,0,.05)!important; }
        body .workspace-nav .q-btn .q-btn__content,
        body .workspace-nav .q-btn .q-btn__content * { color:var(--ink)!important; }
        .q-page-container { padding-top:88px!important; }
        .q-page { min-height:calc(100vh - 88px)!important; }
        .q-page > .nicegui-content { padding:0; }
        .dashboard-main { width:100%; max-width:1288px; margin:0 auto; padding:34px 24px 48px; gap:28px; }
        .page-heading { padding-bottom:0; }
        .page-eyebrow { font-size:9px; color:var(--muted); font-weight:600; letter-spacing:1.6px; margin-bottom:4px; }
        .page-title { font-size:36px; font-weight:600; letter-spacing:-1.5px; color:var(--ink); line-height:1.2; }
        .page-description { font-size:13px; color:var(--muted); margin-top:5px; }
        .resource-grid { grid-template-columns:1.1fr 1fr 1fr 1fr; padding:0!important; gap:0!important; overflow:hidden; }
        .resource-cell { padding:25px 28px; gap:12px; min-height:248px; border-right:1px solid var(--stroke); }
        .resource-cell:last-child { border-right:0; }
        .resource-cpu { --resource-accent:#2563eb; align-items:center;
            background:color-mix(in srgb,var(--resource-accent) 8%,var(--surface)); }
        .resource-memory { --resource-accent:#7c3aed; }
        .resource-nvme { --resource-accent:#b45309; }
        .resource-hdd { --resource-accent:#059669; }
        body.body--dark .resource-cpu { --resource-accent:#60a5fa; }
        body.body--dark .resource-memory { --resource-accent:#a78bfa; }
        body.body--dark .resource-nvme { --resource-accent:#fbbf24; }
        body.body--dark .resource-hdd { --resource-accent:#34d399; }
        .resource-cell { --q-primary:var(--resource-accent)!important; }
        .resource-cell .metric-number, .resource-cell .dial-value,
        .resource-cell .metric-icon { color:var(--resource-accent); }
        .resource-cell .metric-icon { opacity:1; }
        .metric-heading { font-size:12px; font-weight:600; color:var(--muted); }
        .metric-icon { color:var(--muted); opacity:.65; }
        .metric-reading { margin-top:13px; margin-bottom:3px; }
        .metric-number { font-size:43px; font-weight:550; letter-spacing:-2px; line-height:1.2;
            font-variant-numeric:tabular-nums; color:var(--ink); }
        .metric-caption, .metric-footnote { font-size:11px; color:var(--muted); line-height:1.5; font-variant-numeric:tabular-nums; }
        .metric-footnote { padding-top:9px; margin-top:auto; }
        .cpu-dial { position:relative; margin:6px auto 2px; width:112px; height:112px; }
        .dial-value { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
            font-size:24px; font-weight:600; letter-spacing:-1px; color:var(--ink); }
        .metric-bar { height:8px; border-radius:2px; margin-top:4px; }
        .resource-cell .q-linear-progress__model { opacity:1; }
        .resource-cell .q-linear-progress__track { opacity:.08; }
        .sensor-card { padding:22px!important; min-height:172px; gap:14px; }
        body .sensor-card .q-badge.bg-positive { --q-positive:var(--inset); color:var(--muted)!important; padding:4px 8px; }
        .room-readings { margin-top:5px; }
        .room-temperature { font-size:43px; font-weight:500; letter-spacing:-2px; line-height:1.1; color:var(--ink); }
        .room-caption { font-size:8px; font-weight:600; letter-spacing:1px; color:var(--muted); }
        .room-secondary { color:var(--muted); padding-bottom:3px; }
        .room-detail { font-size:12px; font-variant-numeric:tabular-nums; }
        .quick-device-grid { grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
        body .fleet-overview { padding:22px!important; }
        .iot-plug-tile { background:var(--inset); border-radius:12px; padding:15px!important; gap:14px; box-shadow:none; }
        .iot-plug-tile .q-btn { background:var(--surface)!important; color:var(--ink)!important;
            border:1px solid var(--stroke); border-radius:8px; min-width:48px; box-shadow:none; }
        .iot-plug-tile .q-icon { color:var(--muted)!important; }
        .iot-plug-tile .q-label[class~="text-teal-600"] { color:var(--ink)!important; }
        .analysis-panel { margin-top:0!important; padding:18px 22px!important; border-left:1px solid var(--stroke)!important; }
        .analysis-panel .q-label { font-size:12px; }
        .analysis-panel .q-label:first-child { text-transform:none; letter-spacing:0; font-weight:600; }
        .energy-summary { min-height:172px; }
        .energy-number { color:var(--ink); font-variant-numeric:tabular-nums; letter-spacing:-1.2px; font-size:43px; }
        .split-left { flex:0 0 200px; padding:24px; }
        .split-left .text-3xl { font-size:25px; font-weight:600; }
        .plug-card-modern { padding:20px!important; }
        .plug-card-modern.plug-active { border-color:var(--stroke)!important; }
        .plug-card-modern.plug-critical { border-left:1px solid var(--stroke)!important; }
        .plug-card-modern .text-[8px] { font-size:9px; }
        @media (max-width:1023px) {
            .shell-update { display:none; }
            .resource-cell { padding:22px 18px; }
            .metric-number { font-size:36px; }
            .quick-device-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        @media (max-width:767px) {
            .app-topbar { height:126px; padding:14px 18px; flex-wrap:wrap; gap:10px; }
            .app-topbar > .workspace-nav { order:3; width:100%; }
            body .workspace-nav.q-btn-group .q-btn { flex:1; padding:0 8px; min-height:32px; }
            .q-page-container { padding-top:126px!important; }
            .dashboard-main { padding:24px 16px; gap:24px; }
            .page-title { font-size:29px; }
            .resource-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .resource-cell { min-height:218px; padding:20px 16px; border-bottom:1px solid var(--stroke); }
            .resource-cell:nth-child(2) { border-right:0; }
            .resource-cell:nth-child(n+3) { border-bottom:0; }
            .resource-cell:nth-child(3) { border-right:1px solid var(--stroke); }
            .metric-number { font-size:35px; }
            .metric-caption, .metric-footnote { font-size:10px; }
            .sensor-card { min-height:158px; }
            body .fleet-overview { padding:16px!important; }
            .quick-device-grid { gap:10px; }
            .iot-plug-tile { padding:12px!important; }
        }
        </style>
    ''')

# ─────────────────────────────────────────────────────────────────────────────
#  RENDER SERVER CONTENT
# ─────────────────────────────────────────────────────────────────────────────
def render_server_content(on_nav_to_plugs=None):
    with ui.column().classes('w-full gap-4 sm:gap-6'):

        with ui.grid().classes('glass-card resource-grid w-full'):
            for key, name, icon in [('cpu', 'Processor', 'memory'), ('memory', 'Memory', 'developer_board'), ('nvme', 'NVMe storage', 'storage'), ('hdd', 'Mass storage', 'dns')]:
                with ui.column().classes(f'resource-cell resource-{key}'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label(name).classes('metric-heading')
                        ui.icon(icon, size='18px').classes('metric-icon')
                    if key == 'cpu':
                        with ui.element('div').classes('cpu-dial'):
                            ui.circular_progress(min=0, max=100, show_value=False, size='112px', color='primary').bind_value_from(system_stats, 'cpu_percent').props('thickness=0.09')
                            ui.label().bind_text_from(system_stats, 'cpu_percent', backward=lambda x: f'{x:.1f}%').classes('dial-value')
                        ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'Core temperature  ·  {x:.1f}°C').classes('metric-caption')
                    else:
                        with ui.column().classes('gap-1 metric-reading'):
                            ui.label().bind_text_from(system_stats, f'{key}_percent', backward=lambda x: f'{x:.1f}%').classes('metric-number')
                            ui.label('Capacity used').classes('metric-caption')
                        ui.linear_progress(show_value=False).bind_value_from(system_stats, f'{key}_percent', backward=lambda x: x/100).props('color=primary').classes('metric-bar')
                        with ui.row().classes('w-full justify-between items-center gap-1'):
                            ui.label().bind_text_from(system_stats, f'{key}_used_gb', backward=lambda x: f'{x:.1f} GB').classes('metric-caption')
                            ui.label().bind_text_from(system_stats, f'{key}_total_gb', backward=lambda x: f'of {x:g} GB').classes('metric-caption')
                        if key == 'nvme':
                            ui.label().bind_text_from(system_stats, 'nvme_temp', backward=lambda x: f'Drive temperature  ·  {x:.1f}°C').classes('metric-footnote')
                        elif key == 'hdd':
                            ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: f'Drive state  ·  {x.title()}').classes('metric-footnote')
                        else:
                            ui.label('System memory').classes('metric-footnote')

        # ── IoT Environment & Smart Plug Fleet ──────────────────────────────
        with ui.row().classes('items-center justify-between mt-2 mb-1 w-full flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('sensors', color='secondary').classes('text-xl')
                ui.label('Environment').classes('text-lg font-bold text-slate-800 dark:text-gray-200')
            if on_nav_to_plugs:
                ui.button('Manage Plugs Fleet →', on_click=on_nav_to_plugs, icon='electrical_services').props('flat rounded dense').classes('text-xs font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 px-3 py-1')

        # 1. Environmental Sensor Cards (ESP32 Multi-room)
        iot_container = ui.row().classes('sensor-grid w-full gap-4 grid grid-cols-1 md:grid-cols-3 items-stretch')

        # 2. Smart Plug Fleet Quick-Control Hub
        with ui.card().classes('glass-card fleet-overview w-full p-4 sm:p-5 relative overflow-hidden'):
            with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('power', color='positive').classes('text-lg')
                    ui.label('Connected devices').classes('text-sm font-semibold text-slate-700 dark:text-slate-300')
                with ui.row().classes('items-center gap-3 text-xs font-semibold'):
                    server_fleet_watts_label = ui.label('0.0 W total').classes('text-amber-500 font-bold')
                    server_fleet_active_label = ui.label('0/8 powered on').classes('text-emerald-500 font-bold')

            iot_plugs_grid = ui.grid().classes('quick-device-grid w-full')

        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if iot_devices:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes(
                            'glass-card sensor-card p-4 '
                            'transition-transform h-full flex flex-col justify-between'):
                            with ui.row().classes('items-center justify-between w-full mb-2'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('wifi', size='xs').classes('text-slate-400 dark:text-slate-300')
                                    with ui.column().classes('gap-0'):
                                        ui.label(data.get('name', device_id.replace('esp32-', '').title())).classes(
                                            'text-sm font-bold text-slate-700 dark:text-slate-200')
                                        ui.label(data.get('zone', 'Homelab')).classes(
                                            'text-[10px] text-slate-400')
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
                for dev_key, cfg in MOCK_DEVICES.items():
                    with plug_lock:
                        s = plug_state[dev_key]["status"]
                    is_on = s["switch"] if s else True
                    watts = s["watts"] if s else 0.0
                    if is_on:
                        active_cnt += 1
                        total_w += watts

                    is_crit = cfg.get("is_critical", False)
                    tile_cls = f"iot-plug-tile {'tile-on' if is_on else ''} {'tile-critical' if is_crit else ''} min-h-[105px] flex flex-col justify-between p-4"
                    with ui.card().classes(tile_cls):
                        with ui.row().classes('items-start justify-between w-full'):
                            with ui.column().classes('gap-1'):
                                ui.icon(cfg.get('icon', 'power'), size='20px').classes(
                                    'text-emerald-500' if is_on else 'text-slate-400'
                                )
                                with ui.column().classes('gap-0 mt-1'):
                                    ui.label(cfg["name"]).classes(
                                        'text-sm font-semibold text-slate-800 dark:text-slate-200 leading-tight'
                                    )
                                    ui.label(cfg.get("zone", "Lab")).classes(
                                        'text-[10px] text-slate-400'
                                    )
                            if is_crit:
                                ui.icon('lock', size='14px').classes('text-rose-500').tooltip('Protected Infrastructure')

                        with ui.row().classes('items-end justify-between w-full mt-auto'):
                            ui.label(f"{watts:.1f} W" if is_on else "OFF").classes(
                                f"text-xs font-bold uppercase tracking-wider {'text-teal-600 dark:text-teal-300' if is_on else 'text-slate-400'}"
                            )

                            def make_toggle_handler(dk=dev_key, crit=is_crit):
                                def _toggle():
                                    with plug_lock:
                                        cur_st = plug_state[dk]["status"]
                                        cur_on = cur_st["switch"] if cur_st else True
                                    if crit and cur_on:
                                        ui.notify(f"⚠ Protected device ({MOCK_DEVICES[dk]['name']})! Use Plugs tab for confirmed shutdown.", type='warning')
                                        return
                                    with plug_lock:
                                        if plug_state[dk]["status"]:
                                            plug_state[dk]["status"]["switch"] = not cur_on
                                    ui.notify(f"{'🔴 Turned OFF' if cur_on else '✅ Turned ON'} ({MOCK_DEVICES[dk]['name']})", type='positive' if not cur_on else 'negative')
                                    update_iot_display()
                                return _toggle

                            ui.button(
                                'ON' if is_on else 'OFF',
                                on_click=make_toggle_handler(dev_key, is_crit)
                            ).props('unelevated rounded').classes(
                                f"text-[11px] font-bold px-3 py-1 transition-colors {'bg-emerald-500 text-white hover:bg-emerald-600' if is_on else 'bg-blue-500 text-white hover:bg-blue-600'}"
                            )

            server_fleet_watts_label.set_text(f"{total_w:.1f} W total")
            server_fleet_active_label.set_text(f"{active_cnt}/{len(MOCK_DEVICES)} powered on")

        ui.timer(3.0, update_iot_display)

        with ui.card().classes(
            'glass-card analysis-panel w-full p-4 '
            'border-l-4 border-slate-300 dark:border-white'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    ui.label('DeepMind analysis').classes(
                        'text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest mb-1')
                    ui.label().bind_text_from(globals(), 'ai_insights').classes(
                        'text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed')

# ─────────────────────────────────────────────────────────────────────────────
#  RENDER ENERGY CONTENT
# ─────────────────────────────────────────────────────────────────────────────
def render_energy_content():
    peak_watt = [0.0]
    selected_device = {'value': 'all'}
    with ui.column().classes('w-full gap-4 sm:gap-6'):


        with ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 md:grid-cols-3 items-stretch'):

            # 1. Live Power
            with ui.card().classes('glass-card energy-summary p-5 flex flex-col items-start justify-center relative overflow-hidden'):
                ui.label('LIVE POWER').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('bolt', size='sm', color='warning').classes('absolute top-4 right-4 opacity-30')
                live_power_label = ui.label('0.0').classes('energy-number text-4xl font-semibold mt-6')
                ui.label('Watts (W)').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')

            # 2. Today's Total Energy
            with ui.card().classes('glass-card energy-summary p-5 flex flex-col items-start justify-center relative overflow-hidden'):
                ui.label("TODAY'S ENERGY").classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('eco', size='sm', color='positive').classes('absolute top-4 right-4 opacity-30')
                total_kwh_label = ui.label('0.000').classes('energy-number text-4xl font-semibold mt-6')
                ui.label('kWh').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')

            # 3. Total Cost
            with ui.card().classes('glass-card energy-summary p-5 flex flex-col items-start justify-center relative overflow-hidden'):
                ui.label("TOTAL COST").classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('payments', size='sm', color='primary').classes('absolute top-4 right-4 opacity-30')
                cost_label = ui.label('0.00').classes('energy-number text-4xl font-semibold mt-6')
                ui.label('RM · Domestic General estimate').classes('text-xs text-slate-500 mt-2 uppercase tracking-widest font-semibold')

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

                device_options = {'All Plugs (Total)': 'all'}
                for k, dev in MOCK_DEVICES.items():
                    device_options[f"{dev['name']} ({dev.get('zone', 'Homelab')})"] = k

                def on_device_change(e):
                    selected_device['value'] = device_options.get(e.value, 'all')

                ui.select(
                    list(device_options.keys()), value='All Plugs (Total)',
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
            with ui.column().classes('split-right min-w-0 w-full'):
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
                                 'splitLine': {'show': True, 'lineStyle': {'color': 'rgba(148,163,184,0.16)'}} }],
                    'yAxis':   [{'type': 'value', 'name': 'Watts',
                                 'nameTextStyle': {'color': '#94a3b8'},
                                 'axisLabel': {'color': '#94a3b8'},
                                 'splitLine': {'show': True, 'lineStyle': {'color': 'rgba(148,163,184,0.16)'}} }],
                    'series':  [{'name': 'Power (W)', 'type': 'line', 'smooth': False,
                                 'lineStyle': {
                                      'color': '#8b5cf6',
                                      'width': 3,
                                      'shadowColor': 'rgba(139, 92, 246, 0.5)',
                                      'shadowBlur': 8
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

        def update_energy_stats():
            dk = selected_device['value']

            if dk == 'all':
                pwr_w, today_kwh, cost_rm, month_kwh = 0.0, 0.0, 0.0, 0.0
                histories = []
                with plug_lock:
                    for d_key, d_cfg in MOCK_DEVICES.items():
                        s = plug_state[d_key]["status"]
                        if s:
                            pwr_w += s["watts"]
                        today = mock_get_today_summary(d_cfg["id"])
                        today_kwh += today["total_kwh"]
                        cost_rm += today["cost_rm"]
                        month_kwh += today["total_kwh"] + d_cfg.get("base_month_kwh", 25.0)
                        histories.append(list(plug_state[d_key]["history"]))

                pwr_kw = pwr_w / 1000.0
                if histories and all(len(h) > 0 for h in histories):
                    min_len = min(len(h) for h in histories)
                    labels = [histories[0][i]["t"] for i in range(min_len)]
                    values = [round(sum(h[i]["w"] for h in histories), 1) for i in range(min_len)]
                else:
                    labels, values = [], []

            else:
                with plug_lock:
                    s = plug_state[dk]["status"]
                    history = list(plug_state[dk]["history"])

                if not s:
                    return

                pwr_w = s["watts"]
                pwr_kw = pwr_w / 1000.0
                today = mock_get_today_summary(MOCK_DEVICES[dk]["id"])
                today_kwh = today["total_kwh"]
                cost_rm = today["cost_rm"]
                month_kwh = today_kwh + MOCK_DEVICES[dk].get("base_month_kwh", 25.0)
                labels = [p["t"] for p in history]
                values = [round(p["w"], 1) for p in history]

            live_power_label.set_text(f"{pwr_w:.1f}")
            total_kwh_label.set_text(f"{today_kwh:.3f}")
            cost_label.set_text(f"{cost_rm:.4f}")
            month_usage_label.set_text(f"{month_kwh:.3f}")

            if pwr_kw > peak_watt[0]:
                peak_watt[0] = pwr_kw
                peak_usage_label.set_text(f"{pwr_kw:.3f}")

            # Update chart with history or mocked intervals
            if chart_filter['value'] != 'Live':
                import random
                from datetime import datetime, timedelta
                n_points = 24 if chart_filter['value'] == 'Day' else 7 if chart_filter['value'] == 'Week' else 30
                now = datetime.now()

                if chart_filter['value'] == 'Day':
                    labels = [(now - timedelta(hours=i)).strftime("%H:00") for i in range(n_points)][::-1]
                    values = [round(random.uniform(0.5, 3.5), 2) for _ in range(n_points)]
                    area_chart.options['yAxis'][0]['name'] = 'Energy (kWh)'
                    area_chart.options['series'][0]['name'] = 'Energy (kWh)'
                else:
                    labels = [(now - timedelta(days=i)).strftime("%b %d") for i in range(n_points)][::-1]
                    values = [round(random.uniform(10.0, 30.0), 2) for _ in range(n_points)]
                    area_chart.options['yAxis'][0]['name'] = 'Energy (kWh)'
                    area_chart.options['series'][0]['name'] = 'Energy (kWh)'

                total_kwh = sum(values)
                chart_cost.set_text(f"EST. COST: RM {mock_calculate_tnb_cost(total_kwh):.2f}")
            else:
                area_chart.options['yAxis'][0]['name'] = 'Watts'
                area_chart.options['series'][0]['name'] = 'Power (W)'
                chart_cost.set_text("")

            area_chart.options['xAxis'][0]['data']  = labels
            area_chart.options['series'][0]['data'] = values
            area_chart.update()

        ui.timer(2.0, update_energy_stats)


# ─────────────────────────────────────────────────────────────────────────────
#  PLUG PAGE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
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
            "backgroundColor": "rgba(15, 23, 42, 0.85)",
            "borderColor": "rgba(255, 255, 255, 0.1)",
            "textStyle": {"color": "#f8fafc", "fontFamily": "Inter", "fontSize": 12},
        },
        "grid": {"left": "10%", "right": "4%", "top": "12%", "bottom": "22%"},
        "xAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#94a3b8", "fontSize": 10, "rotate": 30},
            "axisLine": {"lineStyle": {"color": "rgba(255,255,255,0.08)"}},
        },
        "yAxis": {
            "type": "value",
            "name": "Watts",
            "nameTextStyle": {"color": "#94a3b8", "fontSize": 10},
            "axisLabel": {"color": "#94a3b8", "fontSize": 10},
            "splitLine": {"lineStyle": {"color": "rgba(148,163,184,0.16)", "type": "dashed"}},
        },
        "series": [{
            "data": values, "type": "line", "smooth": False, "symbol": "none",
            "lineStyle": {"color": "#00a884", "width": 3, "shadowColor": "rgba(0,168,132,0.3)", "shadowBlur": 6},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(0, 168, 132, 0.4)"},
                    {"offset": 1, "color": "rgba(0, 168, 132, 0.02)"},
                ],
            }},
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  RENDER PLUGS CONTENT (Scalable Fleet Manager)
# ─────────────────────────────────────────────────────────────────────────────
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
                def _do_confirmed_off():
                    dk = pending_off_dev['key']
                    if dk and dk in plug_state:
                        with plug_lock:
                            if plug_state[dk]["status"]:
                                plug_state[dk]["status"]["switch"] = False
                        ui.notify(f"🔴 Power cut confirmed for {MOCK_DEVICES[dk]['name']}", type='negative')
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
                modal_chart = ui.echart(_plug_chart_options('server')).style('height:200px;width:100%')

            # Controls & Timers
            with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-4 mb-4'):
                # Child Lock & State
                with ui.card().classes('p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800'):
                    ui.label('CHILD LOCK & SAFETY').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                    with ui.row().classes('w-full gap-2'):
                        ui.button('🔒 Lock ON', on_click=lambda: ui.notify("Child lock enabled (Mock)", type='positive')).props('unelevated rounded outline size=sm').classes('flex-1 text-xs')
                        ui.button('🔓 Lock OFF', on_click=lambda: ui.notify("Child lock disabled (Mock)", type='info')).props('unelevated rounded outline size=sm').classes('flex-1 text-xs')

                # LED Indicator
                with ui.card().classes('p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800'):
                    ui.label('HARDWARE LED INDICATOR').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                    with ui.row().classes('w-full gap-2'):
                        for lbl in ['Follow Relay', 'Always ON', 'Always OFF']:
                            ui.button(lbl, on_click=lambda l=lbl: ui.notify(f"LED mode set to {l} (Mock)", type='positive')).props('unelevated rounded outline size=sm').classes('flex-1 text-[11px]')

            # Countdown Timer
            with ui.card().classes('w-full p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 mb-4'):
                ui.label('AUTOMATED TIMER & COUNTDOWN').classes('text-xs font-bold text-slate-400 uppercase tracking-wider mb-3')
                with ui.row().classes('w-full items-center gap-2 flex-wrap sm:flex-nowrap'):
                    for t_min in [15, 30, 60, 120]:
                        ui.button(f"{t_min}m", on_click=lambda m=t_min: ui.notify(f"Timer set for {m} minutes (Mock)", type='positive')).props('unelevated rounded outline size=sm').classes('text-xs')
                    countdown_inp = ui.number(label='Custom seconds', value=0, min=0, max=86400).props('dense outlined rounded').classes('flex-1 text-xs')
                    ui.button('Set Timer', on_click=lambda: ui.notify(f"Custom timer set for {int(countdown_inp.value or 0)}s (Mock)", type='positive')).props('unelevated rounded size=sm color=primary').classes('text-xs font-bold')

            # Hardware Info Footer
            with ui.row().classes('w-full items-center justify-between p-3 rounded-2xl bg-slate-100 dark:bg-slate-800/40 text-xs font-mono text-slate-500 dark:text-slate-400'):
                modal_ip_label = ui.label('IP: 192.168.1.15')
                modal_id_label = ui.label('ID: mock_server_001')
                modal_latency_label = ui.label('Latency: 1.8 ms (Local LAN)')

        def open_detail_modal(dk: str):
            detail_modal_dev['key'] = dk
            cfg = MOCK_DEVICES[dk]
            with plug_lock:
                s = plug_state[dk]["status"]
            modal_title.set_text(cfg["name"])
            modal_subtitle.set_text(f"{cfg.get('zone', 'Homelab')} • ID: {cfg['id']}")
            modal_icon.props(f"name={cfg.get('icon', 'power')}")
            modal_ip_label.set_text(f"IP: {cfg['ip']}")
            modal_id_label.set_text(f"ID: {cfg['id']}")
            modal_live_watts.set_text(f"{s['watts']:.1f} W" if s else "0.0 W")
            modal_chart.options = _plug_chart_options(dk)
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
                        ui.label(f'Monitoring {len(MOCK_DEVICES)} smart plugs across 4 homelab zones').classes('text-xs text-slate-500 dark:text-slate-400')

                def handle_turn_all_on():
                    with plug_lock:
                        for dk in MOCK_DEVICES:
                            if plug_state[dk]["status"]:
                                plug_state[dk]["status"]["switch"] = True
                    ui.notify("✅ All smart plugs turned ON", type='positive')
                    _refresh_plugs()

                def handle_turn_non_critical_off():
                    count = 0
                    with plug_lock:
                        for dk, cfg in MOCK_DEVICES.items():
                            if not cfg.get("is_critical", False) and plug_state[dk]["status"]:
                                plug_state[dk]["status"]["switch"] = False
                                count += 1
                    ui.notify(f"🔴 Turned OFF {count} non-critical plugs (Server & Network protected)", type='info')
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
                        fleet_active_label = ui.label('0 / 8').classes('text-2xl sm:text-3xl font-black text-emerald-500')
                        ui.label('ONLINE').classes('text-[10px] font-bold text-slate-400')

                # 3. Today's Energy & Cost
                with ui.column().classes('p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/60'):
                    ui.label('TODAY ACCUMULATED').classes('text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider')
                    with ui.row().classes('items-baseline gap-2 mt-1'):
                        fleet_today_kwh_label = ui.label('0.00 kWh').classes('text-xl sm:text-2xl font-black text-blue-500')
                        fleet_today_cost_label = ui.label('RM 0.00').classes('text-xs font-bold text-slate-600 dark:text-slate-300')
                    ui.label('Domestic General · monitored estimate').classes('text-[10px] text-slate-400')

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
                    zones = ['All', 'Server Rack', 'Office / Lab', 'Workshop', 'Living Room', 'Networking']
                    zone_btns = {}
                    for z in zones:
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
        cards_grid = ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4')

        with cards_grid:
            for dev_key, cfg in MOCK_DEVICES.items():
                is_crit = cfg.get("is_critical", False)
                with plug_lock:
                    s = plug_state[dev_key]["status"]
                    ok = plug_state[dev_key]["ok"]
                is_on = s["switch"] if s else True

                with ui.element('div').classes('w-full') as card_wrapper:
                    card_cls = f"plug-card-modern p-4 sm:p-5 flex flex-col justify-between h-full {'plug-active' if is_on else ''} {'plug-critical' if is_crit else ''}"
                    with ui.card().classes(card_cls) as card_el:

                        # Header: Icon + Name + Zone + Critical Badge + Pulse Dot
                        with ui.row().classes('items-center justify-between w-full mb-3'):
                            with ui.row().classes('items-center gap-2.5 overflow-hidden'):
                                with ui.element('div').classes('p-2 rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center'):
                                    icon_el = ui.icon(cfg.get('icon', 'power'), size='20px').classes('text-primary')
                                with ui.column().classes('gap-0 overflow-hidden'):
                                    ui.label(cfg["name"]).classes('text-sm font-bold text-slate-800 dark:text-white truncate')
                                    with ui.row().classes('items-center gap-1.5'):
                                        ui.label(cfg.get('zone', 'Homelab')).classes('text-[10px] text-slate-400 font-medium')
                                        ui.label(f"• {cfg['ip']}").classes('text-[10px] text-slate-400 font-mono')

                            with ui.row().classes('items-center gap-2 flex-shrink-0'):
                                if is_crit:
                                    ui.badge('🔒 Protected', color='negative').props('dense rounded').classes('text-[9px] font-bold')
                                dot_el = ui.element('span').classes('pulse-dot-online' if ok else 'pulse-dot-offline')

                        # Center: Big Wattage + Load Bar + Switch
                        with ui.row().classes('items-center justify-between w-full my-2'):
                            with ui.column().classes('gap-0'):
                                with ui.row().classes('items-baseline gap-1'):
                                    watts_val_label = ui.label('0.0').classes('text-2xl font-black text-slate-800 dark:text-white font-mono')
                                    ui.label('W').classes('text-xs font-bold text-slate-400')

                            # Power Switch Button
                            def make_toggle(dk=dev_key, crit=is_crit):
                                def _toggle_fn():
                                    with plug_lock:
                                        cur_s = plug_state[dk]["status"]
                                        cur_on = cur_s["switch"] if cur_s else True

                                    if cur_on and crit:
                                        pending_off_dev['key'] = dk
                                        confirm_desc.set_text(
                                            f"You are about to cut power to {MOCK_DEVICES[dk]['name']} ({MOCK_DEVICES[dk].get('zone', 'Homelab')}). "
                                            f"This device is marked as critical infrastructure. Are you sure?"
                                        )
                                        confirm_dialog.open()
                                        return

                                    # Toggle normal device or turning ON
                                    with plug_lock:
                                        if plug_state[dk]["status"]:
                                            plug_state[dk]["status"]["switch"] = not cur_on
                                    ui.notify(f"{'🔴 Turned OFF' if cur_on else '✅ Turned ON'}: {MOCK_DEVICES[dk]['name']}", type='negative' if cur_on else 'positive')
                                    _refresh_plugs()
                                return _toggle_fn

                            switch_btn = ui.button(
                                "● ON" if is_on else "○ OFF",
                                on_click=make_toggle(dev_key, is_crit)
                            ).classes(f"plug-switch-btn {'plug-switch-on' if is_on else 'plug-switch-off'}")

                        ui.separator().classes('my-2 bg-slate-200/40 dark:bg-slate-800/40')

                        # Metrics Strip: Volts, Amps, Today kWh, Today RM
                        with ui.grid().classes('w-full grid-cols-4 gap-1 text-center my-1'):
                            with ui.column().classes('gap-0 items-center'):
                                volts_label = ui.label('—').classes('text-xs font-mono font-bold text-slate-700 dark:text-slate-200')
                                ui.label('VOLTS').classes('text-[8px] text-slate-400 font-bold uppercase')
                            with ui.column().classes('gap-0 items-center'):
                                amps_label = ui.label('—').classes('text-xs font-mono font-bold text-slate-700 dark:text-slate-200')
                                ui.label('CURRENT').classes('text-[8px] text-slate-400 font-bold uppercase')
                            with ui.column().classes('gap-0 items-center'):
                                today_kwh_label = ui.label('—').classes('text-xs font-mono font-bold text-emerald-500')
                                ui.label('TODAY').classes('text-[8px] text-slate-400 font-bold uppercase')
                            with ui.column().classes('gap-0 items-center'):
                                today_rm_label = ui.label('—').classes('text-xs font-mono font-bold text-blue-500')
                                ui.label('EST. COST').classes('text-[8px] text-slate-400 font-bold uppercase')

                        # Card Footer: Inspect & Controls Button
                        with ui.row().classes('w-full items-center justify-between pt-2 mt-auto border-t border-slate-100 dark:border-slate-800/60'):
                            ui.label(cfg.get('id', 'mock')).classes('text-[9px] font-mono text-slate-400')
                            ui.button('Inspect & Controls ↗', on_click=lambda dk=dev_key: open_detail_modal(dk)).props('flat rounded dense').classes('text-[11px] font-bold text-primary hover:bg-primary/10 px-2 py-0.5')

                cards_data[dev_key] = {
                    "wrapper": card_wrapper,
                    "card": card_el,
                    "watts_label": watts_val_label,
                    "switch_btn": switch_btn,
                    "volts_label": volts_label,
                    "amps_label": amps_label,
                    "today_kwh_label": today_kwh_label,
                    "today_rm_label": today_rm_label,
                    "dot_el": dot_el,
                    "icon_el": icon_el,
                    "cfg": cfg,
                }

    # ── Filtering logic ──────────────────────────────────────────────────────
    def _apply_filters():
        q = search_query['val']
        z = active_zone['val']
        st = active_status['val']

        for dk, refs in cards_data.items():
            cfg = refs["cfg"]
            with plug_lock:
                s = plug_state[dk]["status"]
            is_on = s["switch"] if s else True
            is_crit = cfg.get("is_critical", False)

            # Check Zone
            match_zone = (z == 'All' or cfg.get('zone') == z)

            # Check Status
            if st == 'Active ON':
                match_status = is_on
            elif st == 'Idle / OFF':
                match_status = not is_on
            elif st == 'Protected Critical':
                match_status = is_crit
            else:
                match_status = True

            # Check Search Query
            if q:
                match_search = (
                    q in cfg["name"].lower() or
                    q in cfg.get("zone", "").lower() or
                    q in cfg["ip"].lower() or
                    q in cfg["id"].lower()
                )
            else:
                match_search = True

            refs["wrapper"].set_visibility(match_zone and match_status and match_search)

    # ── Periodic Refresh Loop ────────────────────────────────────────────────
    def _refresh_plugs():
        total_w = 0.0
        active_cnt = 0
        total_today_kwh = 0.0
        total_today_cost = 0.0
        top_consumer = ('—', 0.0)

        for dk, refs in cards_data.items():
            cfg = refs["cfg"]
            with plug_lock:
                s = plug_state[dk]["status"]
                ok = plug_state[dk]["ok"]

            if not s:
                continue

            on = s["switch"]
            watts = s["watts"]

            if on:
                active_cnt += 1
                total_w += watts
                if watts > top_consumer[1]:
                    top_consumer = (cfg["name"], watts)

            today = mock_get_today_summary(cfg["id"])
            total_today_kwh += today["total_kwh"]
            total_today_cost += today["cost_rm"]

            # Update Card UI
            refs["watts_label"].set_text(f"{watts:.1f}")
            if watts > 100:
                refs["watts_label"].classes(replace='text-2xl font-black text-rose-500 font-mono')
            elif watts > 30:
                refs["watts_label"].classes(replace='text-2xl font-black text-amber-500 font-mono')
            elif on:
                refs["watts_label"].classes(replace='text-2xl font-black text-emerald-500 font-mono')
            else:
                refs["watts_label"].classes(replace='text-2xl font-black text-slate-400 font-mono')

            refs["volts_label"].set_text(f"{s['voltage']:.1f}V")
            refs["amps_label"].set_text(f"{s['current_ma']}mA")
            refs["today_kwh_label"].set_text(f"{today['total_kwh']:.2f}")
            refs["today_rm_label"].set_text(f"{today['cost_rm']:.2f}")

            # Switch Button
            refs["switch_btn"].set_text("● ON" if on else "○ OFF")
            refs["switch_btn"].classes(
                remove="plug-switch-on plug-switch-off"
            ).classes("plug-switch-on" if on else "plug-switch-off")

            # Card Active Class
            if on:
                refs["card"].classes(add="plug-active")
            else:
                refs["card"].classes(remove="plug-active")

            # Online dot
            refs["dot_el"].classes(
                remove="pulse-dot-online pulse-dot-offline"
            ).classes("pulse-dot-online" if ok else "pulse-dot-offline")

        # Update Fleet Header
        fleet_watts_label.set_text(f"{total_w:.1f}")
        fleet_kw_label.set_text(f"{total_w/1000.0:.3f} kW combined")
        fleet_active_label.set_text(f"{active_cnt} / {len(MOCK_DEVICES)}")
        fleet_today_kwh_label.set_text(f"{total_today_kwh:.2f} kWh")
        fleet_today_cost_label.set_text(f"RM {total_today_cost:.2f}")
        top_device_name_label.set_text(top_consumer[0])
        top_device_watt_label.set_text(f"{top_consumer[1]:.1f} W draw")

        # If detail modal is open, update its chart & live reading
        if detail_dialog.value and detail_modal_dev['key']:
            target_dk = detail_modal_dev['key']
            with plug_lock:
                target_s = plug_state[target_dk]["status"]
            if target_s:
                modal_live_watts.set_text(f"{target_s['watts']:.1f} W")
            modal_chart.options = _plug_chart_options(target_dk)
            modal_chart.update()

    ui.timer(2.0, _refresh_plugs)


# ─────────────────────────────────────────────────────────────────────────────
#  RENDER NETWORK CONTENT
# ─────────────────────────────────────────────────────────────────────────────
def render_network_content():
    with ui.column().classes('w-full gap-4 sm:gap-6'):
        with ui.row().classes('items-center gap-2 mb-2 w-full'):
            ui.icon('router', color='primary').classes('text-2xl')
            ui.label('Network Monitor').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')
            health_badge = ui.badge('GOOD', color='positive').classes('ml-auto font-bold px-3 py-1 text-sm rounded-full shadow-sm')

        with ui.grid().classes('w-full gap-6 grid-cols-1 lg:grid-cols-3'):
            # Left Column (Charts & Metrics)
            with ui.column().classes('col-span-1 lg:col-span-2 gap-4'):
                # Latency Chart
                with ui.card().classes('glass-card w-full p-4'):
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label('Live Latency (ms)').classes('font-semibold text-slate-700 dark:text-gray-300')
                        ui.icon('timeline', color='gray-400')

                    chart = ui.echart({
                        'tooltip': {'trigger': 'axis'},
                        'legend': {'data': list(network_state["targets"].keys()), 'textStyle': {'color': '#94a3b8'}, 'bottom': 0},
                        'grid': {'left': '3%', 'right': '4%', 'bottom': '15%', 'top': '5%', 'containLabel': True},
                        'xAxis': {'type': 'category', 'boundaryGap': False, 'show': False, 'data': list(range(60))},
                        'yAxis': {'type': 'value', 'splitLine': {'lineStyle': {'color': '#334155'}}},
                        'series': [
                            {'name': target, 'type': 'line', 'smooth': False, 'showSymbol': False, 'lineStyle': {'width': 3}, 'data': list(data["history"])}
                            for target, data in network_state["targets"].items()
                        ],
                        'color': ['#3b82f6', '#a855f7', '#f97316']
                    }).classes('w-full h-64')

                # Targets Status Grid
                target_cards = {}
                with ui.grid().classes('w-full gap-4 grid-cols-1 sm:grid-cols-3'):
                    for target in network_state["targets"].keys():
                        with ui.card().classes('glass-card items-center text-center p-4 transition-all') as c:
                            ui.label(target).classes('text-sm font-medium text-slate-500 dark:text-gray-400 mb-1')
                            lat_label = ui.label('0.0 ms').classes('text-2xl font-bold text-slate-800 dark:text-white')
                            loss_label = ui.label('0.0% loss').classes('text-xs text-positive font-semibold mt-1 bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded')
                            target_cards[target] = {'lat': lat_label, 'loss': loss_label, 'card': c}

            # Right Column (AI & Logs)
            with ui.column().classes('col-span-1 gap-4'):
                # AI Insights
                with ui.card().classes('glass-card w-full relative overflow-hidden p-4'):
                    ui.html('<div class="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-blue-500/5 z-0 pointer-events-none"></div>')
                    with ui.row().classes('w-full justify-between items-center mb-3 z-10'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('auto_awesome', color='purple-400').classes('animate-pulse')
                            ui.label('AI Insights').classes('font-bold text-purple-700 dark:text-purple-400')
                    ai_label = ui.label(network_state["ai_insights"]).classes('text-sm text-slate-600 dark:text-gray-300 z-10 whitespace-pre-line leading-relaxed')

                # Action Buttons
                with ui.card().classes('glass-card w-full p-4'):
                    ui.label('Actions').classes('font-semibold text-slate-700 dark:text-gray-300 mb-3')
                    with ui.button('Generate ISP Report', icon='description', color='primary').props('unelevated rounded outline').classes('w-full mb-2 shadow-sm'):
                        ui.tooltip('Calls Gemini to generate a formal ISP accountability report')
                    with ui.button('Run Manual Traceroute', icon='route', color='secondary').props('unelevated rounded outline').classes('w-full shadow-sm'):
                        pass

                # Route Log
                with ui.card().classes('glass-card w-full flex-grow p-4'):
                    with ui.row().classes('w-full items-center gap-2 mb-3'):
                        ui.icon('list_alt', color='gray-400')
                        ui.label('Route Events').classes('font-semibold text-slate-700 dark:text-gray-300')
                    log_container = ui.column().classes('w-full text-xs font-mono text-slate-600 dark:text-gray-400 gap-2')
                    for log in network_state["route_log"]:
                        with log_container:
                            ui.label(log)

    # ── Live update timer ────────────────────────────────────────────────
    def _refresh_network():
        update_network_mock_data()

        health = network_state["health"]
        health_badge.set_text(health)
        health_badge.props(f'color={"positive" if health == "GOOD" else "warning" if health == "WARNING" else "negative"}')

        for i, (target, data) in enumerate(network_state["targets"].items()):
            chart.options['series'][i]['data'] = list(data["history"])
        chart.update()

        for target, elements in target_cards.items():
            data = network_state["targets"][target]
            elements['lat'].set_text(f"{data['latency']:.1f} ms")
            elements['loss'].set_text(f"{data['packet_loss']:.1f}% loss")

            if data['packet_loss'] > 0:
                elements['loss'].classes(replace='text-xs text-negative font-semibold mt-1 bg-red-100 dark:bg-red-900/30 px-2 py-0.5 rounded animate-pulse')
                elements['card'].classes(add='border-2 border-red-500/50')
            else:
                elements['loss'].classes(replace='text-xs text-positive font-semibold mt-1 bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded')
                elements['card'].classes(remove='border-2 border-red-500/50')

        ai_label.set_text(network_state["ai_insights"])

        log_container.clear()
        for log in network_state["route_log"]:
            with log_container:
                ui.label(log)

    ui.timer(2.0, _refresh_network)

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN SPA PAGE
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/')
def index_page():
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    add_common_styles()
    ui.colors(primary='#226dbe', secondary='#6557b8', accent='#a66328',
              positive='#16805e', warning='#b77915')

    with ui.header().classes('app-topbar items-center justify-between'):
        with ui.row().classes('items-center gap-3'):
            with ui.element('div').classes('brand-symbol'):
                ui.icon('dns', size='21px')
            with ui.column().classes('gap-0'):
                ui.label('homelab').classes('brand-name')
                ui.label('CONTROL CENTER').classes('brand-caption')
        toggle = ui.toggle(['Server', 'Energy', 'Plugs', 'Network'], value='Server').props('unelevated no-caps').classes('workspace-nav')
        with ui.row().classes('items-center gap-3'):
            ui.label().bind_text_from(globals(), 'last_update', backward=lambda x: f'Updated {x}' if x else 'Collecting data').classes('shell-update')
            ui.button(icon='dark_mode', on_click=dark_mode.toggle).props('flat round aria-label="Toggle theme"').classes('theme-button').bind_icon_from(dark_mode, 'value', backward=lambda x: 'light_mode' if x else 'dark_mode')

    headings = {
        'Server': ('Server overview', 'System resources, room conditions and connected devices.'),
        'Energy': ('Energy monitor', 'Power consumption, daily usage and cost estimates.'),
        'Plugs': ('Device fleet', 'Monitor and control your connected smart plugs.'),
        'Network': ('Network monitor', 'Latency, packet loss and route diagnostics.'),
    }
    with ui.column().classes('dashboard-main'):
        with ui.column().classes('page-heading gap-1'):
            ui.label('YOUR HOMELAB').bind_text_from(toggle, 'value', backward=lambda x: f'HOMELAB / {x.upper()}').classes('page-eyebrow')
            ui.label().bind_text_from(toggle, 'value', backward=lambda x: headings[x][0]).classes('page-title')
            ui.label().bind_text_from(toggle, 'value', backward=lambda x: headings[x][1]).classes('page-description')
        with ui.tab_panels(toggle, value='Server').classes('w-full bg-transparent p-0'):
            with ui.tab_panel('Server').classes('p-0'):
                render_server_content(on_nav_to_plugs=lambda: toggle.set_value('Plugs'))
            with ui.tab_panel('Energy').classes('p-0'):
                render_energy_content()
            with ui.tab_panel('Plugs').classes('p-0'):
                render_plugs_content()
            with ui.tab_panel('Network').classes('p-0'):
                render_network_content()

# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────────────────────
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))
threading.Thread(target=plug_polling_loop, daemon=True).start()

ui.run(host='0.0.0.0', port=3001, title='Homelab Dashboard Design', reload=False, favicon='🏠')
