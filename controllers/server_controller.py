"""
controllers/server_controller.py
=================================
Business logic for system metrics, AI insights, and MQTT publishing.
"""
import os
import sys
import asyncio
import subprocess
import json
from datetime import datetime

from nicegui import run
from prometheus_api_client import PrometheusConnect
import paho.mqtt.client as mqtt_client

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import models.state as state

prom = PrometheusConnect(url="http://localhost:9090", disable_ssl=True)


# ── Hardware helpers ──────────────────────────────────────────────────────────
def get_cpu_temp() -> float:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return round(float(f.read()) / 1000.0, 1)
    except:
        return 0.0

def get_nvme_temp() -> int:
    try:
        result = subprocess.run(['smartctl', '-A', '/dev/nvme0n1'],
                                capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'Temperature' in line and 'Celsius' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'Celsius' and i > 0:
                        return int(parts[i-1])
        return 0
    except:
        return 0

def get_hdd_status() -> str:
    try:
        result = subprocess.run(['iostat', '-d', 'sda', '1', '2'],
                                capture_output=True, text=True, timeout=3)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 3:
            last_line = lines[-1].split()
            if len(last_line) > 3 and float(last_line[3]) > 0.1:
                return 'active'
        return 'idle'
    except:
        return 'idle'


# ── Metrics fetch (runs in thread pool) ───────────────────────────────────────
def _fetch_all_metrics() -> dict:
    """Pure sync — offloaded to thread pool via run.io_bound()."""
    stats: dict = {}
    iot: dict = {}

    cpu_q = prom.custom_query(
        query='100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
    stats['cpu_percent'] = round(float(cpu_q[0]['value'][1]), 1) if cpu_q else 0
    stats['cpu_temp']    = get_cpu_temp()

    mem_used  = prom.custom_query(query='node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
    mem_total = prom.custom_query(query='node_memory_MemTotal_bytes')
    if mem_used and mem_total:
        stats['memory_used_gb']  = round(float(mem_used[0]['value'][1]) / (1024**3), 2)
        stats['memory_total_gb'] = round(float(mem_total[0]['value'][1]) / (1024**3), 2)
        stats['memory_percent']  = round(
            stats['memory_used_gb'] / stats['memory_total_gb'] * 100, 1)

    nvme_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"} - node_filesystem_avail_bytes{mountpoint="/mnt/nvme"}')
    nvme_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"}')
    if nvme_used and nvme_total:
        stats['nvme_used_gb']  = round(float(nvme_used[0]['value'][1]) / (1024**3), 1)
        stats['nvme_total_gb'] = round(float(nvme_total[0]['value'][1]) / (1024**3), 1)
        stats['nvme_percent']  = round(
            stats['nvme_used_gb'] / stats['nvme_total_gb'] * 100, 1)
    stats['nvme_temp'] = get_nvme_temp()

    hdd_used  = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"} - node_filesystem_avail_bytes{mountpoint="/mnt/hdd-public"}')
    hdd_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"}')
    if hdd_used and hdd_total:
        stats['hdd_used_gb']  = round(float(hdd_used[0]['value'][1]) / (1024**3), 1)
        stats['hdd_total_gb'] = round(float(hdd_total[0]['value'][1]) / (1024**3), 1)
        stats['hdd_percent']  = round(
            stats['hdd_used_gb'] / stats['hdd_total_gb'] * 100, 1)
    stats['hdd_status'] = get_hdd_status()

    esp32_temps    = prom.custom_query(query='esp32_temperature_celsius')
    esp32_humidity = prom.custom_query(query='esp32_humidity_percent')
    for metric in esp32_temps:
        did = metric['metric']['device_id']
        iot.setdefault(did, {})['temperature'] = round(float(metric['value'][1]), 1)
    for metric in esp32_humidity:
        did = metric['metric']['device_id']
        iot.setdefault(did, {})['humidity'] = round(float(metric['value'][1]), 1)

    return {'system': stats, 'iot': iot}


# ── Async loops ───────────────────────────────────────────────────────────────
async def update_metrics():
    while True:
        try:
            result = await run.io_bound(_fetch_all_metrics)
            state.system_stats.update(result['system'])
            state.iot_devices.update(result['iot'])
            state.last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Metrics error: {e}")
        await asyncio.sleep(7)


async def update_ai_insights():
    """Reads cached analysis from disk every 30s."""
    while True:
        try:
            if os.path.exists(state.AI_CACHE_PATH):
                mtime = datetime.fromtimestamp(os.path.getmtime(state.AI_CACHE_PATH))
                with open(state.AI_CACHE_PATH, "r") as f:
                    cached = f.read()
                state.ai_insights = f"🕒 Last Analysis: {mtime.strftime('%H:%M')}\n\n{cached}"
            else:
                state.ai_insights = "🤖 Click 'Generate Analysis' to run a system summary."
        except Exception as e:
            state.ai_insights = f"❌ AI Read Error: {e}"
        await asyncio.sleep(30)


def run_deepseek_analysis() -> str:
    """Called by the Generate Analysis button. Uses DeepSeek."""
    import sys
    sys.path.insert(0, "/mnt/nvme/Projects/dashboard")
    try:
        from backend.gemini_ai import analyze_system
        return analyze_system(triggered_by="manual")
    except Exception as e:
        return f"❌ Analysis error: {e}"


# ── Local MQTT publisher ──────────────────────────────────────────────────────
def publish_local_mqtt(device_key: str, watts: float) -> None:
    try:
        c = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        c.connect("localhost", 1883, keepalive=5)
        c.publish("plug/readings", json.dumps({"device_key": device_key, "watts": watts}), qos=0)
        c.disconnect()
    except Exception as e:
        print(f"[local_mqtt] publish error: {e}")
