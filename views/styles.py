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
            .plug-card { background:#FFFFFF; border:1px solid rgba(0,0,0,.06); border-radius:20px; overflow:hidden; transition:all .3s; box-shadow: 0 2px 12px rgba(0,0,0,0.04); }
            body.body--dark .plug-card { background:#161b22; border:1px solid rgba(255,255,255,0.07); box-shadow: 0 4px 24px rgba(0,0,0,0.3); }
            .plug-card.plug-on { border: 1px solid rgba(59, 130, 246, 0.25); box-shadow:0 0 20px rgba(59, 130, 246, 0.08); }
            body.body--dark .plug-card.plug-on { border: 1px solid rgba(59, 130, 246, 0.3); box-shadow: 0 0 24px rgba(59, 130, 246, 0.12); }
            .plug-stat-strip { display:flex; flex-wrap:wrap; gap:16px; align-items:center; background:rgba(0,0,0,0.03); border-radius:14px; padding:14px 18px; }
            body.body--dark .plug-stat-strip { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.05); }
            .plug-stat-num { font-family:'Inter',sans-serif; font-size:1.4rem; font-weight:800; line-height:1; color:#111827; }
            body.body--dark .plug-stat-num { color:#FFFFFF; }
            .plug-stat-lbl { font-size:.6rem; color:#6B7280; text-transform:uppercase; letter-spacing:.08em; margin-top:3px; font-weight: 700; }
            body.body--dark .plug-stat-lbl { color:#6b7280; }
            .plug-sep { width:1px; height:36px; background:rgba(0,0,0,.06); }
            body.body--dark .plug-sep { background:rgba(255,255,255,.07); }
            .plug-toggle { width:100%; padding:14px 0!important; border-radius:999px!important; font-family:'Inter',sans-serif!important; font-size:.85rem!important; font-weight:700!important; letter-spacing:.05em!important; transition:all .3s ease!important; border:none!important;}
            .plug-toggle-on  { background:#3B82F6!important; color:#ffffff!important; box-shadow: 0 4px 18px rgba(59,130,246,0.4)!important;}
            body.body--dark .plug-toggle-on { background:#3B82F6!important; color:#ffffff!important; box-shadow: 0 4px 18px rgba(59,130,246,0.3)!important; }
            .plug-toggle-off { background:rgba(0,0,0,0.05)!important; color:#6B7280!important; }
            body.body--dark .plug-toggle-off { background:rgba(255,255,255,0.06)!important; color:#6b7280!important; }
            .plug-toggle-warn { background:#f97316!important; color:#ffffff!important; box-shadow: 0 4px 15px rgba(249,115,22,0.35)!important;}
            .plug-energy-row { display:flex; flex-wrap:wrap; gap:10px; background:rgba(0,0,0,0.03); border-radius:14px; padding:14px 18px; }
            body.body--dark .plug-energy-row { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.05); }
            .plug-ctrl-btn { background:rgba(0,0,0,0.04)!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-family:'Inter',sans-serif!important; font-weight:600!important; font-size:.75rem!important; padding:9px 16px!important; transition:all .2s!important; }
            body.body--dark .plug-ctrl-btn { background:rgba(255,255,255,0.07)!important; color:#9ca3af!important; }
            .plug-ctrl-btn:hover { background:rgba(0,0,0,0.08)!important; color:#111827!important; }
            body.body--dark .plug-ctrl-btn:hover { background:rgba(255,255,255,0.12)!important; color:#FFFFFF!important; }
            .plug-led-btn { background:rgba(0,0,0,0.04)!important; border:none!important; border-radius:999px!important; color:#4B5563!important; font-weight:600!important; font-size:.7rem!important; padding:8px 12px!important; transition:all .2s!important; flex:1; min-width:70px; }
            body.body--dark .plug-led-btn { background:rgba(255,255,255,0.07)!important; color:#9ca3af!important; }
            .plug-led-btn:hover { background:rgba(0,0,0,0.08)!important; color:#111827!important; }
            body.body--dark .plug-led-btn:hover { background:rgba(255,255,255,0.12)!important; color:#FFFFFF!important; }
            .dot-ok  { width:9px;height:9px;border-radius:50%;background:#22c55e;display:inline-block;box-shadow:0 0 7px rgba(34,197,94,0.7); }
            .dot-err { width:9px;height:9px;border-radius:50%;background:#ef4444;display:inline-block; }
            .plug-warn-banner { background:#FEF2F2; border-radius:14px; padding:12px 16px; margin-top:10px; font-family:'Inter',sans-serif; font-size:.75rem; color:#991B1B; font-weight:500; display:none; }
            body.body--dark .plug-warn-banner { background:rgba(239,68,68,0.1); color:#fca5a5; border:1px solid rgba(239,68,68,0.2); }
            .plug-warn-banner.visible { display:block; }
            .plug-section-title { font-family:'Inter',sans-serif; font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:#9ca3af; margin-bottom:10px; font-weight: 700; }
            .plug-inner-card { background:rgba(0,0,0,0.03); border-radius:16px; padding:16px 18px; margin-top:12px; }
            body.body--dark .plug-inner-card { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); }

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
#  (nav_toggle removed, using index_page SPA toggle instead)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — SERVER
