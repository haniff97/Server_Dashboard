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
    # 1. Dark Theme & Global Styles
    dark_mode = ui.dark_mode()
    dark_mode.enable()
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            
            body { 
                font-family: 'Inter', sans-serif; 
                background: #f8fafc; /* Slate-50 */
                color: #1e293b; /* Slate-800 */
                transition: background-color 0.3s ease, color 0.3s ease;
            }
            body.body--dark { 
                background: #0f172a; /* Slate-900 */
                color: #f8fafc; /* Slate-50 */
            }

            .glass-card {
                background: rgba(255, 255, 255, 0.7);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 16px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }
            body.body--dark .glass-card {
                background: rgba(30, 41, 59, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            }

            .glass-header {
                background: rgba(255, 255, 255, 0.8);
                backdrop-filter: blur(8px);
                border-bottom: 1px solid rgba(0, 0, 0, 0.05);
                transition: background-color 0.3s ease, border-color 0.3s ease;
            }
            body.body--dark .glass-header {
                background: rgba(15, 23, 42, 0.8);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
        </style>
    ''')
    
    # Custom colors
    ui.colors(primary='#3b82f6', secondary='#8b5cf6', accent='#ec4899', positive='#10b981', warning='#f59e0b')
    
    # 2. Header
    with ui.header().classes('glass-header items-center justify-between p-4 fixed top-0 w-full z-50'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('dashboard', size='md', color='primary')
            ui.label('HOMELAB').classes('text-2xl font-bold tracking-tight text-slate-900 dark:text-white')
        
        with ui.row().classes('items-center gap-4'):
            with ui.row().classes('items-center gap-2 bg-slate-200 dark:bg-slate-800 rounded-full px-3 py-1'):
                ui.icon('schedule', size='xs', color='gray-400')
                ui.label().bind_text_from(globals(), 'last_update').classes('text-sm text-slate-600 dark:text-gray-300 font-mono')
            
            # Theme Switch
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round').classes('text-slate-900 dark:text-white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    # 3. Main Content Area
    with ui.column().classes('w-full max-w-7xl mx-auto p-6 mt-4 gap-8'):
        
        # Section Title
        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        # Metrics Grid
        with ui.grid().classes('w-full gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4'):
            
            # --- CPU ---
            with ui.card().classes('glass-card p-5 flex flex-col items-center relative overflow-hidden'):
                ui.label('CPU Load').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
                ui.icon('speed', size='sm', color='primary').classes('absolute top-4 right-4 opacity-50')
                
                with ui.circular_progress(min=0, max=100, show_value=True, size='110px', color='primary').props('thickness=0.1').classes('mt-4') as p:
                    p.bind_value_from(system_stats, 'cpu_percent')
                
                ui.label().bind_text_from(system_stats, 'cpu_temp', backward=lambda x: f'{x}°C').classes('text-2xl font-bold text-slate-900 dark:text-white mt-4')
                ui.label('Core Temp').classes('text-xs text-slate-500')

            # --- Memory ---
            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MEMORY').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                
                with ui.row().classes('items-end gap-2'):
                    ui.label().bind_text_from(system_stats, 'memory_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-secondary')
                    ui.label('Used').classes('text-sm text-slate-600 dark:text-slate-500 mb-2')
                
                # Custom Progress Bar (Memory)
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'memory_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=secondary track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'memory_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'memory_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            # --- NVMe ---
            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('NVME STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'nvme_temp', backward=lambda x: f'{x}°C').classes('absolute top-4 right-5 text-lg text-accent font-bold')
                 
                with ui.row().classes('items-end gap-2'):
                     ui.label().bind_text_from(system_stats, 'nvme_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-accent')

                # Custom Progress Bar (NVMe)
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'nvme_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=accent track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'nvme_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'nvme_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

            # --- HDD ---
            with ui.card().classes('glass-card p-5 flex flex-col justify-between relative'):
                ui.label('MASS STORAGE').classes('text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-widest mb-4')
                ui.label().bind_text_from(system_stats, 'hdd_status', backward=lambda x: x.upper()).classes('absolute top-4 right-5 text-lg font-bold text-slate-400 dark:text-slate-300')
                 
                with ui.row().classes('items-end justify-between w-full'):
                     ui.label().bind_text_from(system_stats, 'hdd_percent', backward=lambda x: f'{x:.1f}%').classes('text-4xl font-bold text-positive')

                # Custom Progress Bar (HDD)
                with ui.element('div').classes('relative w-full my-4 h-6 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden'):
                    ui.linear_progress(show_value=False).bind_value_from(system_stats, 'hdd_percent', backward=lambda x: x/100).classes('absolute inset-0 h-full bg-transparent').props('color=positive track-color=transparent')
                    ui.label().bind_text_from(system_stats, 'hdd_used_gb', backward=lambda x: f'{x:.1f}GB').classes('absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white z-10')
                
                with ui.row().classes('justify-center w-full mt-2'):
                    ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'/ {x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')
    
        # IoT Devices
        with ui.row().classes('items-center gap-2 mt-8 mb-2'):
             ui.icon('sensors', color='secondary')
             ui.label('IoT Environment').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')
        
        # IoT Container - Content Width
        iot_container = ui.row().classes('w-full gap-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4')
        
        def update_iot_display():
            iot_container.clear()
            with iot_container:
                if not iot_devices:
                     with ui.card().classes('glass-card p-4 min-w-[200px]'):
                        ui.label('Looking for devices...').classes('text-slate-500 animate-pulse')
                else:
                    for device_id, data in iot_devices.items():
                        with ui.card().classes('glass-card p-4 min-w-[200px] hover:scale-105 transition-transform cursor-pointer'):
                            with ui.row().classes('items-center gap-3 mb-3'):
                                ui.icon('wifi', size='xs').classes('text-slate-400 dark:text-slate-300')
                                with ui.column().classes('gap-0'):
                                    ui.label(device_id.replace('esp32-', '').title()).classes('text-md font-bold text-slate-700 dark:text-slate-200')
                                    ui.label('Active').classes('text-[10px] text-positive uppercase tracking-wide')
                            
                            ui.separator().classes('bg-slate-300/50 dark:bg-slate-700/50 mb-3')
                            
                            with ui.row().classes('justify-between items-center gap-6'):
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('thermostat', size='xs', color='orange')
                                    ui.label(f"{data.get('temperature')}°C").classes('text-lg font-bold text-slate-800 dark:text-white')
                                
                                with ui.column().classes('items-center gap-1'):
                                    ui.icon('water_drop', size='xs', color='blue')
                                    ui.label(f"{data.get('humidity')}%").classes('text-lg font-bold text-slate-800 dark:text-white')
        
        ui.timer(2.0, update_iot_display)
    
    # AI Insights
    with ui.card().classes('glass-card w-full p-6 mt-4 bg-slate-200/50 dark:bg-slate-800/50 border-l-4 border-slate-300 dark:border-white mx-auto max-w-7xl'):
        with ui.row().classes('items-start gap-4'):
            with ui.column().classes('w-full'):
                ui.label('DeepMind Analysis').classes('text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest mb-1')
                ui.label().bind_text_from(globals(), 'ai_insights').classes('text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed')

# Start background tasks
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))

ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard', reload=False, favicon='🏠')
