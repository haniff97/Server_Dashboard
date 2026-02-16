#!/usr/bin/env python3
"""
Custom Homelab Dashboard - DESIGN MODE
Safe for local editing. Uses MOCK DATA instead of real sensors.
"""
from nicegui import ui, app
import asyncio
from datetime import datetime
import random

# Global state
system_stats = {
    'cpu_percent': 0,
    'cpu_temp': 0,
    'memory_percent': 0,
    'memory_used_gb': 0,
    'memory_total_gb': 16.0,
    'nvme_percent': 0,
    'nvme_used_gb': 0,
    'nvme_total_gb': 1000.0,
    'nvme_temp': 0,
    'hdd_percent': 0,
    'hdd_used_gb': 0,
    'hdd_total_gb': 4000.0,
    'hdd_status': 'unknown',
}

iot_devices = {
    'esp32-main-room': {'temperature': 24.5, 'humidity': 48.2}
}
ai_insights = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update = ""

# --- MOCK DATA GENERATORS (Same as before) ---
def get_mock_cpu_temp():
    return round(random.uniform(40.0, 65.0), 1)

def get_mock_nvme_temp():
    return round(random.uniform(30.0, 50.0), 1)

def get_mock_hdd_status():
    return 'active' if random.random() > 0.7 else 'idle'

async def update_metrics():
    while True:
        global system_stats, iot_devices, last_update
        try:
            system_stats['cpu_percent'] = round(random.uniform(10.0, 80.0), 1)
            system_stats['cpu_temp'] = get_mock_cpu_temp()
            
            system_stats['memory_used_gb'] = round(random.uniform(4.0, 12.0), 2)
            system_stats['memory_percent'] = round((system_stats['memory_used_gb'] / system_stats['memory_total_gb']) * 100, 1)
            
            system_stats['nvme_used_gb'] = round(random.uniform(200.0, 800.0), 1)
            system_stats['nvme_percent'] = round((system_stats['nvme_used_gb'] / system_stats['nvme_total_gb']) * 100, 1)
            system_stats['nvme_temp'] = get_mock_nvme_temp()
            
            system_stats['hdd_used_gb'] = round(random.uniform(1000.0, 3500.0), 1)
            system_stats['hdd_percent'] = round((system_stats['hdd_used_gb'] / system_stats['hdd_total_gb']) * 100, 1)
            system_stats['hdd_status'] = get_mock_hdd_status()
            
            iot_devices['esp32-main-room'] = {'temperature': round(random.uniform(22.0, 26.0), 1), 'humidity': round(random.uniform(45.0, 60.0), 1)}
            
            last_update = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"❌ Error: {e}")
        await asyncio.sleep(2)

async def update_ai_insights():
    while True:
        global ai_insights
        try:
            await asyncio.sleep(5)
            if random.random() > 0.7:
                ai_insights = "Concerns Detected (MOCK):\nHigh CPU usage check detected\n\nRecommendation: Check active processes"
            else:
                ai_insights = "All systems healthy (MOCK)\nPerformance: Optimal\nNo immediate concerns"
        except Exception:
            pass
        await asyncio.sleep(15)

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
            ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round text-color=slate-900 dark:text-color=white').bind_icon_from(dark_mode, 'value', backward=lambda x: 'dark_mode' if x else 'light_mode')

    # 3. Main Content Area
    # 3. Main Content Area
    with ui.column().classes('w-full max-w-7xl mx-auto p-6 mt-4 gap-8'):
        
        # Section Title
        with ui.row().classes('items-center gap-2 mb-2'):
            ui.icon('analytics', color='primary')
            ui.label('System Performance').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        # Metrics Grid
        with ui.grid().classes('w-full gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-4'):
            # Reusable Card Function
            def metric_card(title, icon, color, progress_bind, value_bind, subtext_bind=None):
                with ui.card().classes('glass-card p-0 flex flex-col items-center justify-between pb-6 h-full transition-all hover:scale-105 duration-300'):
                    # Card Header
                    with ui.row().classes(f'w-full p-3 bg-{color}-900/20 justify-between items-center mb-4'):
                        ui.label(title).classes(f'text-sm font-bold text-{color}-400 uppercase tracking-wider')
                        ui.icon(icon, color=color)
                    
                    # Circular Progress
                    with ui.circular_progress(min=0, max=100, show_value=False, size='90px', color=color).classes('mb-2') as p:
                        p.bind_value_from(system_stats, progress_bind)
                        # Center Text
                        with ui.column().classes('absolute inset-0 items-center justify-center'):
                            ui.label().bind_text_from(system_stats, value_bind).classes('text-xl font-bold text-slate-900 dark:text-white')
                    
                    # Subtext
                    if subtext_bind:
                        ui.label().bind_text_from(system_stats, subtext_bind).classes('text-xs text-slate-500 dark:text-slate-400 mt-2')

            # --- CPU ---
            with ui.card().classes('glass-card p-5 flex flex-col items-center relative overflow-hidden'):
                ui.label('CPU Load').classes('text-slate-400 text-xs font-bold uppercase tracking-widest absolute top-4 left-4')
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
                    ui.label().bind_text_from(system_stats, 'memory_total_gb', backward=lambda x: f'{x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

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
                    ui.label().bind_text_from(system_stats, 'nvme_total_gb', backward=lambda x: f'{x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')

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
                    ui.label().bind_text_from(system_stats, 'hdd_total_gb', backward=lambda x: f'{x} GB').classes('text-sm text-slate-500 dark:text-slate-400 font-semibold')


        # IoT Section
        with ui.row().classes('items-center gap-2 mt-8 mb-2'):
             ui.icon('sensors', color='secondary')
             ui.label('IoT Environment').classes('text-lg font-semibold text-slate-800 dark:text-gray-200')

        # IoT Container - Content Width
        with ui.row().classes('w-auto gap-4'):
             # Mock Device Card (Static for Design Mode)
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

        # AI Insights
        with ui.card().classes('glass-card w-full p-6 mt-4 bg-slate-200/50 dark:bg-slate-800/50 border-l-4 border-slate-300 dark:border-white'):
            with ui.row().classes('items-start gap-4'):
                with ui.column().classes('w-full'):
                    ui.label('DeepMind Analysis').classes('text-slate-900 dark:text-white text-sm font-bold uppercase tracking-widest mb-1')
                    ui.label().bind_text_from(globals(), 'ai_insights').classes('text-slate-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed')

# Start background tasks
app.on_startup(lambda: asyncio.create_task(update_metrics()))
app.on_startup(lambda: asyncio.create_task(update_ai_insights()))

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host='0.0.0.0', port=3000, title='Homelab Dashboard Pro', reload=True, favicon='🚀')
