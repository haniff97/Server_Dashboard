"""
views/styles.py
===============
All shared CSS injected on every page via add_common_styles().
"""
from nicegui import ui

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
                border: 1px solid rgba(255, 255, 255, 0.05); 
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
                border: 1px solid rgba(255, 255, 255, 0.05);
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
                background: rgba(244, 244, 245, 0.85); 
                backdrop-filter: blur(16px); 
                -webkit-backdrop-filter: blur(16px);
                border-bottom: 1px solid rgba(0, 0, 0, 0.05); 
            }
            body.body--dark .glass-header { 
                background: rgba(0, 0, 0, 0.85); 
                border-bottom: 1px solid rgba(255, 255, 255, 0.1); 
            }
            
            .stat-value { font-family:'Inter',sans-serif; font-size:1.5rem; font-weight:800; color:#E11D48; }
            body.body--dark .stat-value { color: #39FF14; }
            .stat-label { font-size:.75rem; color:#6B7280; text-transform:uppercase; font-weight:700; letter-spacing:.05em; }
            body.body--dark .stat-label { color:#A1A1AA; }

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

            .dot-ok  { width:9px;height:9px;border-radius:50%;background:#22c55e;display:inline-block;box-shadow:0 0 7px rgba(34,197,94,0.7); }
            .dot-err { width:9px;height:9px;border-radius:50%;background:#ef4444;display:inline-block; }

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
            .glass-menu .q-item--active { background: #3B82F6 !important; color: #FFFFFF !important; font-weight: 600; }
            body.body--dark .glass-menu .q-item--active { background: #3B82F6 !important; color: #FFFFFF !important; }

            /* Active Toggle for navigation */
            .q-btn-group { border-radius: 999px !important; background: #F3F4F6 !important; padding: 4px; box-shadow: none !important; border: 1px solid rgba(0,0,0,0.05) !important; }
            body.body--dark .q-btn-group { background: #1A1A1A !important; border: 1px solid rgba(255,255,255,0.05) !important; }
            .q-btn-group .q-btn { border-radius: 999px !important; font-weight: 600 !important; color: #6B7280 !important; }
            body.body--dark .q-btn-group .q-btn { color: #A1A1AA !important; }
            .q-btn-group .q-btn.bg-primary { background: #0F172A !important; color: #FFFFFF !important; }
            body.body--dark .q-btn-group .q-btn.bg-primary { background: #333333 !important; color: #FFFFFF !important; border: 1px solid rgba(255,255,255,0.1) !important; }
        </style>
    ''')
