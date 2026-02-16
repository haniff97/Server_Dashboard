#!/usr/bin/env python3
"""
Custom Homelab Dashboard
Built with NiceGUI + Prometheus + MQTT
"""
from nicegui import ui, app
from prometheus_api_client import PrometheusConnect
import asyncio
from datetime import datetime
import subprocess

# Connect to Prometheus
prom = PrometheusConnect(url="http://localhost:9090", disable_ssl=True)

# Global state
system_stats = {
    'cpu_percent': 0,
    'cpu_temp': 0,
    'memory_percent': 0,
    'memory_used_gb': 0,
    'memory_total_gb': 0,
    'nvme_percent': 0,
    'nvme_used_gb': 0,
    'nvme_total_gb': 0,
    'nvme_temp': 0,
    'hdd_percent': 0,
    'hdd_used_gb': 0,
    'hdd_total_gb': 0,
    'hdd_status': 'unknown',
}

iot_devices = {}
ai_insights = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update = ""

def get_cpu_temp():
    """Get CPU temperature from system"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = float(f.read()) / 1000.0
        return round(temp, 1)
    except:
        return 0

def get_nvme_temp():
    """Get NVMe temperature using smartctl"""
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

def get_hdd_status():
    """Check if HDD is active or idle"""
    try:
        result = subprocess.run(['iostat', '-d', 'sda', '1', '2'], 
                              capture_output=True, text=True, timeout=3)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 3:
            last_line = lines[-1].split()
            if len(last_line) > 3:
                writes = float(last_line[3])
                if writes > 0.1:
                    return 'active'
        return 'idle'
    except:
        return 'idle'

async def update_metrics():
    """Fetch metrics from Prometheus every 5 seconds"""
    while True:
        global system_stats, iot_devices, last_update
        
        try:
            # CPU Usage
            cpu_query = prom.custom_query(query='100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
            system_stats['cpu_percent'] = round(float(cpu_query[0]['value'][1]), 1) if cpu_query else 0
            
            # CPU Temperature
            system_stats['cpu_temp'] = get_cpu_temp()
            
            # Memory
            mem_used = prom.custom_query(query='node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
            mem_total = prom.custom_query(query='node_memory_MemTotal_bytes')
            
            if mem_used and mem_total:
                system_stats['memory_used_gb'] = round(float(mem_used[0]['value'][1]) / (1024**3), 2)
                system_stats['memory_total_gb'] = round(float(mem_total[0]['value'][1]) / (1024**3), 2)
                system_stats['memory_percent'] = round((system_stats['memory_used_gb'] / system_stats['memory_total_gb']) * 100, 1)
            
            # NVMe Storage
            nvme_used = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"} - node_filesystem_avail_bytes{mountpoint="/mnt/nvme"}')
            nvme_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/nvme"}')
            
            if nvme_used and nvme_total:
                system_stats['nvme_used_gb'] = round(float(nvme_used[0]['value'][1]) / (1024**3), 1)
                system_stats['nvme_total_gb'] = round(float(nvme_total[0]['value'][1]) / (1024**3), 1)
                system_stats['nvme_percent'] = round((system_stats['nvme_used_gb'] / system_stats['nvme_total_gb']) * 100, 1)
            
            # NVMe Temperature
            system_stats['nvme_temp'] = get_nvme_temp()
            
            # HDD Storage
            hdd_used = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"} - node_filesystem_avail_bytes{mountpoint="/mnt/hdd-public"}')
            hdd_total = prom.custom_query(query='node_filesystem_size_bytes{mountpoint="/mnt/hdd-public"}')
            
            if hdd_used and hdd_total:
                system_stats['hdd_used_gb'] = round(float(hdd_used[0]['value'][1]) / (1024**3), 1)
                system_stats['hdd_total_gb'] = round(float(hdd_total[0]['value'][1]) / (1024**3), 1)
                system_stats['hdd_percent'] = round((system_stats['hdd_used_gb'] / system_stats['hdd_total_gb']) * 100, 1)
            
            # HDD Status
            system_stats['hdd_status'] = get_hdd_status()
            
            # IoT Devices (ESP32)
            esp32_temps = prom.custom_query(query='esp32_temperature_celsius')
            esp32_humidity = prom.custom_query(query='esp32_humidity_percent')
            
            for metric in esp32_temps:
                device_id = metric['metric']['device_id']
                if device_id not in iot_devices:
                    iot_devices[device_id] = {}
                iot_devices[device_id]['temperature'] = round(float(metric['value'][1]), 1)
            
            for metric in esp32_humidity:
                device_id = metric['metric']['device_id']
                if device_id not in iot_devices:
                    iot_devices[device_id] = {}
                iot_devices[device_id]['humidity'] = round(float(metric['value'][1]), 1)
            
            last_update = datetime.now().strftime("%H:%M:%S")
            
        except Exception as e:
            print(f"❌ Error fetching metrics: {e}")
        
        await asyncio.sleep(5)

async def update_ai_insights():
    """Update AI insights every 5 minutes"""
    while True:
        global ai_insights
        
        try:
            await asyncio.sleep(10)  # Wait 10 seconds for first data
            
            # Generate simple insights based on metrics
            concerns = []
            if system_stats.get('cpu_temp', 0) > 70:
                concerns.append("⚠️ High CPU temperature")
            if system_stats.get('nvme_temp', 0) > 60:
                concerns.append("⚠️ High NVMe temperature")
            if system_stats.get('nvme_percent', 0) > 80:
                concerns.append("⚠️ NVMe storage >80% full")
            if system_stats.get('memory_percent', 0) > 90:
                concerns.append("⚠️ High memory usage")
            
            if concerns:
                ai_insights = "🚨 Concerns Detected:\n" + "\n".join(concerns)
                ai_insights += "\n\n💡 Recommendation: Monitor system closely"
            else:
                ai_insights = "✅ All systems healthy\n📊 Performance: Optimal\n💡 No immediate concerns"
            
        except Exception as e:
            ai_insights = f"❌ AI analysis error: {e}"
        
        await asyncio.sleep(300)  # Update every 5 minutes

@ui.page('/')
def main_page():
    ui.colors(primary='#1e88e5', secondary='#26a69a', accent='#ff6f00', positive='#21ba45')
    
    # Header
    with ui.header().classes('items-center justify-between bg-primary text-white shadow-lg'):
        ui.label('🏠 Homelab Dashboard').classes('text-h4 font-bold')
        with ui.row().classes('gap-4'):
            ui.label().bind_text_from(globals(), 'last_update', backward=lambda x: f'⏱️ {x}')
            ui.label('Orange Pi 4 Pro').classes('text-subtitle1')
    
    # System Monitoring
    ui.label('📊 System Monitoring').classes('text-h5 q-mt-lg q-ml-md font-bold')
    
    with ui.row().classes('w-full gap-4 p-4 flex-wrap'):
        # CPU Card
        with ui.card().classes('shadow-lg'):
            ui.label('CPU Usage').classes('text-h6 text-primary')
            cpu_progress = ui.circular_progress(min=0, max=100, show_value=True, size='xl', color='primary')
            cpu_progress.bind_value_from(system_stats, 'cpu_percent')
            ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'🌡️ {x}°C' if x else '')
        
        # Memory Card
        with ui.card().classes('shadow-lg'):
            ui.label('Memory').classes('text-h6 text-secondary')
            mem_progress = ui.circular_progress(min=0, max=100, show_value=True, size='xl', color='secondary')
            mem_progress.bind_value_from(system_stats, 'memory_percent')
            ui.label().bind_text_from(system_stats, 'memory_used_gb', backward=lambda x: f'{x} GB')
            ui.label().bind_text_from(system_stats, 'memory_total_gb', backward=lambda x: f'/ {x} GB total')
        
        # NVMe Card
        with ui.card().classes('shadow-lg'):
            ui.label('NVMe Storage').classes('text-h6 text-accent')
            nvme_progress = ui.circular_progress(min=0, max=100, show_value=True, size='xl', color='orange')
            nvme_progress.bind_value_from(system_stats, 'nvme_percent')
            ui.label().bind_text_from(system_stats, 'nvme_used_gb', backward=lambda x: f'{x} GB')
            ui.label().bind_text_from(system_stats, 'nvme_total_gb', backward=lambda x: f'/ {x} GB total')
            ui.label().bind_text_from(system_stats, 'nvme_temp', backward=lambda x: f'🌡️ {x}°C' if x else '')
        
        # HDD Card
        with ui.card().classes('shadow-lg'):
            ui.label('HDD Storage').classes('text-h6 text-positive')
            hdd_progress = ui.circular_progress(min=0, max=100, show_value=True, size='xl', color='green')
            hdd_progress.bind_value_from(system_stats, 'hdd_percent')
            ui.label().bind_text_from(system_stats, 'hdd_used_gb', backward=lambda x: f'{x} GB')
            ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'/ {x} GB total')
            ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: f'💿 {x.upper()}' if x else '')
    
    # IoT Devices
    ui.label('🔌 IoT Devices').classes('text-h5 q-mt-lg q-ml-md font-bold')
    
    iot_container = ui.row().classes('w-full gap-4 p-4 flex-wrap')
    
    def update_iot_display():
        iot_container.clear()
        with iot_container:
            if not iot_devices:
                with ui.card().classes('shadow-lg'):
                    ui.label('No IoT devices connected').classes('text-grey-6')
                    ui.label('Waiting for ESP32 sensors...').classes('text-caption')
            else:
                for device_id, data in iot_devices.items():
                    with ui.card().classes('shadow-lg'):
                        ui.label(f'ESP32 - {device_id}').classes('text-h6 text-primary')
                        ui.separator()
                        ui.label(f"🌡️ Temperature: {data.get('temperature', 'N/A')}°C")
                        ui.label(f"💧 Humidity: {data.get('humidity', 'N/A')}%")
    
    ui.timer(5, update_iot_display)
    
    # AI Insights
    ui.label('🤖 AI Insights').classes('text-h5 q-mt-lg q-ml-md font-bold')
    
    with ui.card().classes('w-full q-ma-md shadow-lg bg-blue-1'):
        ai_label = ui.label().classes('text-body1 whitespace-pre-wrap')
        ai_label.bind_text_from(globals(), 'ai_insights')

# Start background tasks
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard', reload=False, favicon='🏠')
