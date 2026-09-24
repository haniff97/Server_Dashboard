#!/usr/bin/env python3
"""
Custom Homelab Dashboard - DESIGN MODE
Built with NiceGUI + Mock Data (Simulating tinytuya local LAN + MariaDB)
Pages: / (Server) | /energy (Energy Monitor) | /plugs (Smart Plugs)
"""
import os
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
    """Simulate db.calculate_tnb_cost()."""
    tiers = [(200, 0.218), (100, 0.334), (300, 0.516), (float("inf"), 0.546)]
    cost, remaining = 0.0, kwh
    for limit, rate in tiers:
        if remaining <= 0:
            break
        usage = min(remaining, limit)
        cost += usage * rate
        remaining -= usage
    return round(cost, 4)

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
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
            
            body { 
                font-family: 'Inter', sans-serif; 
                background: #F4F4F5;
                color: #111827; 
                transition: background 0.3s, color 0.3s; 
                min-height: 100vh;
            }
            body.body--dark { 
                background: #000000;
                color: #FFFFFF; 
            }
            .glass-card { 
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.05); 
                border-radius: 24px; 
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03); 
                transition: transform 0.2s ease, box-shadow 0.2s ease; 
            }
            .glass-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.06);
            }
            body.body--dark .glass-card { 
                background: #1A1A1A; 
                border: none; 
                box-shadow: none;
            }
            body.body--dark .glass-card:hover {
                transform: translateY(-2px);
            }
            
            .dark-highlight-card {
                background: #0F172A;
                color: #FFFFFF;
                border-radius: 24px;
                box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
            }
            body.body--dark .dark-highlight-card {
                background: #222222;
                border: 1px solid rgba(255,255,255,0.05);
                box-shadow: none;
            }

            .split-card {
                border-radius: 24px;
                overflow: hidden;
                display: flex;
                background: #FFFFFF;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
                border: 1px solid rgba(0, 0, 0, 0.05);
            }
            .split-left {
                background: #E11D48;
                color: #FFFFFF;
                padding: 24px;
                flex: 1;
            }
            .split-right {
                background: #FFFFFF;
                padding: 24px;
                flex: 2;
            }
            body.body--dark .split-card {
                background: #1A1A1A;
                border: none;
                box-shadow: none;
            }
            body.body--dark .split-left {
                background: #222222;
                color: #FFFFFF;
            }
            body.body--dark .split-right {
                background: #1A1A1A;
            }

            .glass-header { 
                background: rgba(244, 244, 245, 0.8); 
                backdrop-filter: blur(16px); 
                -webkit-backdrop-filter: blur(16px);
                border-bottom: 1px solid rgba(0, 0, 0, 0.05); 
            }
            body.body--dark .glass-header { 
                background: rgba(0, 0, 0, 0.8); 
                border-bottom: 1px solid rgba(255, 255, 255, 0.1); 
            }
            
            .stat-value { font-family:'Inter',sans-serif; font-size:1.5rem; font-weight:800; color:#E11D48; }
            body.body--dark .stat-value { color: #39FF14; }
            .stat-label { font-size:.75rem; color:#6B7280; text-transform:uppercase; font-weight:700; letter-spacing:.05em; }
            body.body--dark .stat-label { color:#A1A1AA; }

            /* Plug page styles */
            .plug-card { background:#FFFFFF; border:1px solid rgba(0,0,0,.05); border-radius:24px; overflow:hidden; transition:all .3s; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
            body.body--dark .plug-card { background:#1A1A1A; border:none; box-shadow:none; }
            .plug-card.plug-on { border: 1px solid rgba(225, 29, 72, 0.3); box-shadow:0 0 20px rgba(225, 29, 72, 0.1); }
            body.body--dark .plug-card.plug-on { border: 1px solid rgba(57, 255, 20, 0.3); box-shadow:none; }
            
            /* Modern Scalable Plug Cards */
            .plug-card-modern {
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 20px;
                overflow: hidden;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03);
            }
            .plug-card-modern:hover {
                transform: translateY(-3px);
                box-shadow: 0 12px 28px rgba(0, 0, 0, 0.07);
            }
            body.body--dark .plug-card-modern {
                background: #161A22;
                border: 1px solid rgba(255, 255, 255, 0.06);
                box-shadow: none;
            }
            body.body--dark .plug-card-modern:hover {
                transform: translateY(-3px);
                border-color: rgba(255, 255, 255, 0.16);
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
            }
            .plug-card-modern.plug-active {
                border-color: rgba(16, 185, 129, 0.35);
            }
            body.body--dark .plug-card-modern.plug-active {
                border-color: rgba(16, 185, 129, 0.3);
                box-shadow: 0 0 20px rgba(16, 185, 129, 0.06);
            }
            .plug-card-modern.plug-critical {
                border-left: 4px solid #F43F5E;
            }

            .plug-switch-btn {
                border-radius: 999px !important;
                font-family: 'Inter', sans-serif !important;
                font-weight: 700 !important;
                font-size: 0.78rem !important;
                letter-spacing: 0.04em !important;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
                border: none !important;
                padding: 7px 16px !important;
            }
            .plug-switch-on {
                background: #10B981 !important;
                color: #FFFFFF !important;
                box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3) !important;
            }
            body.body--dark .plug-switch-on {
                background: #10B981 !important;
                color: #042F1A !important;
                font-weight: 800 !important;
                box-shadow: 0 0 16px rgba(16, 185, 129, 0.4) !important;
            }
            .plug-switch-off {
                background: #F1F5F9 !important;
                color: #64748B !important;
            }
            body.body--dark .plug-switch-off {
                background: #242A35 !important;
                color: #94A3B8 !important;
            }
            .plug-switch-warn {
                background: #F43F5E !important;
                color: #FFFFFF !important;
                animation: pulse 1.5s infinite;
            }

            /* IoT Micro Tiles for Server page */
            .iot-plug-tile {
                background: #F8FAFC;
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 16px;
                padding: 12px 14px;
                transition: all 0.2s ease;
            }
            .iot-plug-tile:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(0, 0, 0, 0.05);
            }
            body.body--dark .iot-plug-tile {
                background: #1A1F29;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            body.body--dark .iot-plug-tile:hover {
                background: #212734;
                border-color: rgba(255, 255, 255, 0.1);
            }

            /* Pulse Dot Status */
            .pulse-dot-online {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #10B981;
                display: inline-block;
                box-shadow: 0 0 8px rgba(16, 185, 129, 0.7);
            }
            .pulse-dot-offline {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #F43F5E;
                display: inline-block;
            }

            /* Filter chips */
            .filter-chip-btn {
                border-radius: 999px !important;
                font-size: 0.75rem !important;
                font-weight: 600 !important;
                padding: 4px 12px !important;
                transition: all 0.2s !important;
            }

            .plug-stat-strip { display:flex; flex-wrap:wrap; gap:16px; align-items:center; background:#F9FAFB; border-radius:16px; padding:14px 18px; }
            body.body--dark .plug-stat-strip { background:#222222; border:none; }
            
            .plug-stat-num { font-family:'Inter',sans-serif; font-size:1.4rem; font-weight:800; line-height:1; color:#111827; }
            body.body--dark .plug-stat-num { color:#FFFFFF; }
            
            .plug-stat-lbl { font-size:.6rem; color:#6B7280; text-transform:uppercase; letter-spacing:.08em; margin-top:3px; font-weight: 700; }
            body.body--dark .plug-stat-lbl { color:#A1A1AA; }
            
            .plug-sep { width:1px; height:36px; background:rgba(0,0,0,.05); }
            body.body--dark .plug-sep { background:rgba(255,255,255,.05); }

            .plug-toggle { width:100%; padding:14px 0!important; border-radius:999px!important; font-family:'Inter',sans-serif!important; font-size:.85rem!important; font-weight:700!important; letter-spacing:.05em!important; transition:all .3s ease!important; border:none!important;}
            .plug-toggle-on  { background:#E11D48!important; color:#ffffff!important; box-shadow: 0 4px 15px rgba(225, 29, 72, 0.2)!important;}
            body.body--dark .plug-toggle-on { background:#39FF14!important; color:#000000!important; box-shadow: none!important; }
            .plug-toggle-off { background:#F3F4F6!important; color:#4B5563!important; }
            body.body--dark .plug-toggle-off { background:#222222!important; color:#A1A1AA!important; }
            .plug-toggle-warn { background:#FF5E00!important; color:#ffffff!important; box-shadow: 0 4px 15px rgba(255, 94, 0, 0.3)!important;}
            body.body--dark .plug-toggle-warn { background:#FF5E00!important; color:#000000!important; box-shadow: none!important; }

            .plug-energy-row { display:flex; flex-wrap:wrap; gap:10px; background:#F9FAFB; border-radius:16px; padding:14px 18px; }
            body.body--dark .plug-energy-row { background:#222222; }

            .plug-ctrl-btn { background:#F3F4F6!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-family:'Inter',sans-serif!important; font-weight:600!important; font-size:.75rem!important; padding:9px 16px!important; transition:all .2s!important; }
            body.body--dark .plug-ctrl-btn { background:#222222!important; color:#E5E7EB!important; }
            .plug-ctrl-btn:hover { background:#E5E7EB!important; color:#111827!important; }
            body.body--dark .plug-ctrl-btn:hover { background:#333333!important; color:#FFFFFF!important; }

            .plug-led-btn { background:#F3F4F6!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-weight:600!important; font-size:.7rem!important; padding:8px 12px!important; transition:all .2s!important; flex:1; min-width:70px; }
            body.body--dark .plug-led-btn { background:#222222!important; color:#A1A1AA!important; }
            .plug-led-btn:hover { background:#E5E7EB!important; color:#111827!important; }
            body.body--dark .plug-led-btn:hover { background:#333333!important; color:#FFFFFF!important; }

            .dot-ok  { width:10px;height:10px;border-radius:50%;background:#E11D48;display:inline-block; }
            body.body--dark .dot-ok { background:#39FF14; }
            .dot-err { width:10px;height:10px;border-radius:50%;background:#F87171;display:inline-block; }
            body.body--dark .dot-err { background:#FF5E00; }

            .plug-warn-banner { background:#FEF2F2; border-radius:16px; padding:12px 16px; margin-top:10px; font-family:'Inter',sans-serif; font-size:.75rem; color:#991B1B; font-weight:500; display:none; }
            body.body--dark .plug-warn-banner { background:#431407; color:#FFEDD5; }
            .plug-warn-banner.visible { display:block; }

            .plug-section-title { font-family:'Inter',sans-serif; font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; color:#6B7280; margin-bottom:10px; font-weight: 700; }
            body.body--dark .plug-section-title { color:#A1A1AA; }
            
            .plug-inner-card { background:#F9FAFB; border-radius:20px; padding:16px 18px; margin-top:12px; }
            body.body--dark .plug-inner-card { background:#222222; }

            /* Select & Dropdown styling */
            .q-field--outlined .q-field__control { border-radius: 999px !important; }
            .q-field--outlined .q-field__control:before { border: 1px solid rgba(0, 0, 0, 0.1) !important; background: #FFFFFF !important; transition: all 0.3s; }
            body.body--dark .q-field--outlined .q-field__control:before { border: none !important; background: #222222 !important; }
            .q-field:hover .q-field__control:before { border-color: rgba(0, 0, 0, 0.2) !important; }
            body.body--dark .q-field:hover .q-field__control:before { background: #2A2A2A !important; }
            
            .glass-menu { background: #FFFFFF !important; border: 1px solid rgba(0, 0, 0, 0.05) !important; border-radius: 16px !important; box-shadow: 0 10px 25px rgba(0,0,0,0.1) !important; padding: 4px 0; }
            body.body--dark .glass-menu { background: #1A1A1A !important; border: 1px solid rgba(255,255,255,0.05) !important; color: #FFFFFF !important; box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;}
            .glass-menu .q-item { border-radius: 12px; margin: 2px 6px; transition: all 0.2s; }
            .glass-menu .q-item:hover { background: #F3F4F6 !important; }
            body.body--dark .glass-menu .q-item:hover { background: #222222 !important; }
            .glass-menu .q-item--active { background: #E11D48 !important; color: #FFFFFF !important; font-weight: 600; }
            body.body--dark .glass-menu .q-item--active { background: #39FF14 !important; color: #000000 !important; }

            /* Active Toggle for navigation */
            .q-btn-group { border-radius: 999px !important; background: #F3F4F6 !important; padding: 4px; box-shadow: none !important; border: 1px solid rgba(0,0,0,0.05) !important; }
            body.body--dark .q-btn-group { background: #1A1A1A !important; border: none !important; }
            .q-btn-group .q-btn { border-radius: 999px !important; font-weight: 600 !important; color: #6B7280 !important; }
            body.body--dark .q-btn-group .q-btn { color: #A1A1AA !important; }
            .q-btn-group .q-btn.bg-primary { background: #0F172A !important; color: #FFFFFF !important; }
            body.body--dark .q-btn-group .q-btn.bg-primary { background: #333333 !important; color: #FFFFFF !important; border: 1px solid rgba(255,255,255,0.1) !important; }
        </style>
    ''')

# ─────────────────────────────────────────────────────────────────────────────
#  RENDER SERVER CONTENT
# ─────────────────────────────────────────────────────────────────────────────
def render_server_content(on_nav_to_plugs=None):
    with ui.column().classes('w-full gap-4 sm:gap-8'):

        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        with ui.grid().classes('w-full gap-4 sm:gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4'):

            with ui.card().classes('glass-card p-5 flex flex-col items-center relative overflow-hidden'):
                ui.label('CPU Load').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('speed', size='sm', color='primary').classes('absolute top-4 right-4 opacity-50')
                with ui.circular_progress(min=0, max=100, show_value=True, size='110px', color='primary').props('thickness=0.1').classes('mt-4') as p:
                    p.bind_value_from(system_stats, 'cpu_percent')
                ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'{x}°C').classes('text-2xl font-bold text-slate-900 dark:text-white mt-4')
                ui.label('Core Temp').classes('text-xs text-slate-500')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MEMORY').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                with ui.row().classes('items-end gap-2'):
                    ui.label().bind_text_from(system_stats, 'memory_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-secondary')
                    ui.label('Used').classes('text-sm text-slate-600 dark:text-slate-500 mb-2')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'memory_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=secondary track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'memory_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'memory_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('NVME STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'nvme_temp', backward=lambda x: f'{x}°C').classes('absolute top-4 right-5 text-lg text-accent font-bold')
                with ui.row().classes('items-end gap-2'):
                    ui.label().bind_text_from(system_stats, 'nvme_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-accent')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'nvme_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=accent track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'nvme_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'nvme_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MASS STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: x.upper()).classes('absolute top-4 right-5 text-lg font-bold text-slate-400 dark:text-slate-300')
                with ui.row().classes('items-end justify-between w-full'):
                    ui.label().bind_text_from(system_stats, 'hdd_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-positive')
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'hdd_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=positive track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'hdd_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

        # ── IoT Environment & Smart Plug Fleet ──────────────────────────────
        with ui.row().classes('items-center justify-between mt-8 mb-3 w-full flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('sensors', color='secondary').classes('text-xl')
                ui.label('IoT Environment & Smart Plugs').classes('text-lg font-bold text-slate-800 dark:text-gray-200')
            if on_nav_to_plugs:
                ui.button('Manage Plugs Fleet →', on_click=on_nav_to_plugs, icon='electrical_services').props('flat rounded dense').classes('text-xs font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 px-3 py-1')

        # 1. Environmental Sensor Cards (ESP32 Multi-room)
        iot_container = ui.row().classes('w-full gap-4 sm:gap-6 grid grid-cols-1 md:grid-cols-3 items-stretch mb-4')

        # 2. Smart Plug Fleet Quick-Control Hub
        with ui.card().classes('glass-card w-full p-4 sm:p-5 relative overflow-hidden'):
            with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('power', color='positive').classes('text-lg')
                    ui.label('Smart Plug Fleet Status').classes('text-sm font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide')
                with ui.row().classes('items-center gap-3 text-xs font-semibold'):
                    server_fleet_watts_label = ui.label('⚡ 0.0 W load').classes('text-amber-500 font-bold')
                    server_fleet_active_label = ui.label('🟢 0/8 Active').classes('text-emerald-500 font-bold')

            iot_plugs_grid = ui.grid().classes('w-full gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4')

        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if iot_devices:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes(
                            'glass-card p-4 hover:scale-[1.02] '
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
                            ui.separator().classes('bg-slate-300/40 dark:bg-slate-700/40 mb-3')
                            with ui.row().classes('justify-around items-center gap-4 mt-auto'):
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('thermostat', size='xs', color='orange')
                                    ui.label(f"{data.get('temperature', 0)}°C").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('TEMP').classes('text-[9px] text-slate-400 font-bold')
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('water_drop', size='xs', color='blue')
                                    ui.label(f"{data.get('humidity', 0)}%").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('HUMIDITY').classes('text-[9px] text-slate-400 font-bold')
                                with ui.column().classes('items-center gap-0'):
                                    ui.icon('signal_cellular_alt', size='xs', color='positive')
                                    ui.label(f"{data.get('rssi', -60)}").classes(
                                        'text-lg font-bold text-slate-800 dark:text-white')
                                    ui.label('RSSI dBm').classes('text-[9px] text-slate-400 font-bold')

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
                    tile_cls = f"iot-plug-tile {'tile-on' if is_on else ''} {'tile-critical' if is_crit else ''}"
                    with ui.card().classes(tile_cls):
                        with ui.row().classes('items-center justify-between w-full mb-1'):
                            with ui.row().classes('items-center gap-2 overflow-hidden'):
                                ui.icon(cfg.get('icon', 'power'), size='xs').classes(
                                    'text-emerald-500' if is_on else 'text-slate-400'
                                )
                                with ui.column().classes('gap-0 overflow-hidden'):
                                    ui.label(cfg["name"]).classes(
                                        'text-xs font-bold text-slate-800 dark:text-slate-200 truncate'
                                    )
                                    ui.label(cfg.get("zone", "Lab")).classes(
                                        'text-[9px] text-slate-400'
                                    )
                            if is_crit:
                                ui.icon('lock', size='12px').classes('text-rose-500').tooltip('Protected Infrastructure')

                        with ui.row().classes('items-center justify-between w-full mt-2'):
                            ui.label(f"{watts:.1f} W" if is_on else "OFF").classes(
                                f"text-xs font-mono font-bold {'text-emerald-500 dark:text-emerald-400' if is_on else 'text-slate-400'}"
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
                            ).props('dense unelevated rounded').classes(
                                f"text-[10px] font-bold px-2 py-0.5 {'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' if is_on else 'bg-slate-200 dark:bg-slate-800 text-slate-500'}"
                            )

            server_fleet_watts_label.set_text(f"⚡ {total_w:.1f} W load")
            server_fleet_active_label.set_text(f"🟢 {active_cnt}/{len(MOCK_DEVICES)} Active")

        ui.timer(3.0, update_iot_display)

        with ui.card().classes(
            'glass-card w-full p-4 sm:p-6 mt-2 sm:mt-4 bg-slate-200/50 dark:bg-slate-800/50 '
            'border-l-4 border-slate-300 dark:border-white'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    ui.label('DeepMind Analysis').classes(
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
                chart_cost.set_text(f"EST. COST: RM {total_kwh * 0.218:.2f}")
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
            "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)", "type": "dashed"}},
        },
        "series": [{
            "data": values, "type": "line", "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#10B981", "width": 2.5},
            "areaStyle": {"color": {
                "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [
                    {"offset": 0, "color": "rgba(16, 185, 129, 0.35)"},
                    {"offset": 1, "color": "rgba(16, 185, 129, 0.01)"},
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
                    fleet_active_bar = ui.linear_progress(value=0.75).props('color=positive track-color=grey-8 rounded').classes('h-1.5 mt-1')

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
                                    icon_el = ui.icon(cfg.get('icon', 'power'), size='sm').classes('text-primary')
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
        fleet_active_bar.set_value(active_cnt / max(1, len(MOCK_DEVICES)))
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
                            {'name': target, 'type': 'line', 'smooth': True, 'showSymbol': False, 'data': list(data["history"])}
                            for target, data in network_state["targets"].items()
                        ],
                        'color': ['#3b82f6', '#10b981', '#f59e0b']
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
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899',
              positive='#10b981', warning='#f59e0b')

    with ui.header().classes('glass-header items-center justify-between p-3 fixed top-0 w-full z-50 flex-wrap sm:flex-nowrap'):
        with ui.row().classes('items-center gap-3 z-10 w-full sm:w-auto sm:flex-1 justify-center sm:justify-start relative'):
            ui.icon('dns', size='md', color='primary').classes('drop-shadow-md')
            ui.label('HOMELAB').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
            # Mobile-only dark mode button placed on the right edge
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('lt-sm absolute right-2 text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')
        
        with ui.row().classes('items-center justify-center z-10 w-full sm:w-auto sm:flex-1 mt-3 sm:mt-0'):
            toggle = ui.toggle(
                ['Server', 'Energy', 'Plugs', 'Network'], value='Server'
            ).props('unelevated rounded').classes('q-btn-group').style('border-radius: 20px; font-weight: 600;')

        with ui.row().classes('items-center justify-end gap-4 z-10 gt-xs sm:flex-1'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1 gt-sm'):
                ui.icon('schedule', size='xs', color='gray-400')
                ui.label().bind_text_from(globals(), 'last_update').classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    with ui.column().classes('w-full max-w-7xl mx-auto px-4 sm:px-6 pt-0 pb-4 sm:pb-6 mt-0 gap-4 sm:gap-8'):
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