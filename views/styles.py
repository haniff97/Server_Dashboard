"""
views/styles.py
===============
All shared CSS injected on every page via add_common_styles().
Horizon design system — clean surfaces, one accent, generous typography.
"""
from nicegui import ui

def add_common_styles():
    ui.add_head_html(r'''
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        :root {
            --canvas:#f4f5f7; --surface:#ffffff; --inset:#f6f7f9; --stroke:#e5e8ed;
            --ink:#202935; --muted:#687482; --brand:#426caa; --brand-soft:#edf2f9; --brand-ink:#345d95;
            --shadow:0 3px 14px rgba(25,40,65,.025);
            --q-primary:#426caa; --q-secondary:#6557b8; --q-accent:#a66328;
            --q-positive:#16805e; --q-warning:#b77915; --q-negative:#c23d58;
        }
        body.body--dark {
            --canvas:#101317; --surface:#1a1f26; --inset:#212831; --stroke:#303842;
            --ink:#eef1f5; --muted:#a1acb9; --brand:#a8c4ed; --brand-soft:#2b3a4e; --brand-ink:#c2d6f5;
            --shadow:none;
            --q-primary:#a8c4ed!important; --q-secondary:#b5a7f4!important; --q-accent:#e5b180!important;
            --q-positive:#80c1a7!important; --q-warning:#edc478!important; --q-negative:#f18ca2!important;
            color-scheme:dark;
        }
        body {
            font-family:'Inter',system-ui,sans-serif;
            background:var(--canvas); color:var(--ink);
            min-height:100vh; -webkit-font-smoothing:antialiased;
        }

        /* ── Core Card & Surface Components ──────────────────────────────── */
        .glass-card, .plug-card, .plug-card-modern, .split-card, .iot-plug-tile {
            background:var(--surface); border:1px solid var(--stroke);
            border-radius:20px; box-shadow:var(--shadow); transition:border-color .18s ease;
        }
        .glass-card:hover, .plug-card-modern:hover, .iot-plug-tile:hover {
            border-color:color-mix(in srgb,var(--brand) 30%,var(--stroke));
        }
        .plug-card, .plug-card-modern, .split-card { overflow:hidden; }
        .iot-plug-tile {
            border-radius:12px; padding:15px;
            background:var(--inset); box-shadow:none;
        }

        /* ── Glass Header / Top Bar ───────────────────────────────────────── */
        .glass-header { background:color-mix(in srgb,var(--canvas) 92%,transparent);
            backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
            border-bottom:1px solid var(--stroke); color:var(--ink); }
        .app-topbar {
            height:88px;
            padding:18px max(24px,calc((100vw - 1240px)/2));
            border-bottom:1px solid var(--stroke);
            box-shadow:none;
            background:var(--canvas);
            color:var(--ink);
        }
        .q-layout__section--marginal.app-topbar { background:var(--canvas); color:var(--ink); }

        /* ── Brand Symbol & Name ──────────────────────────────────────────── */
        .brand-symbol {
            width:37px; height:37px; border-radius:12px;
            background:var(--ink); color:var(--surface);
            display:grid; place-items:center;
        }
        .brand-name { font-size:21px; font-weight:650; letter-spacing:-.8px; line-height:1.1; }
        .brand-caption { color:var(--muted); font-size:8px; font-weight:600; letter-spacing:1.5px; margin-top:5px; }
        .shell-update { font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
        .theme-button { color:var(--muted); background:var(--surface); border:1px solid var(--stroke); }

        /* ── Workspace Nav (Tab Toggle) ───────────────────────────────────── */
        body .workspace-nav.q-btn-group {
            display:flex; gap:4px; background:var(--inset)!important;
            padding:5px; border:1px solid var(--stroke)!important;
            border-radius:14px!important; box-shadow:none!important;
        }
        body .workspace-nav.q-btn-group .q-btn {
            min-height:37px; padding:0 20px;
            border-radius:9px!important; font-size:12px; font-weight:500!important;
        }
        body .workspace-nav.q-btn-group .q-btn.bg-primary {
            background:var(--surface)!important;
            --q-primary:var(--surface)!important;
            color:var(--ink)!important;
            box-shadow:0 2px 5px rgba(0,0,0,.05)!important;
        }

        /* ── Page Layout ──────────────────────────────────────────────────── */
        .q-page-container { padding-top:88px!important; }
        .q-page { min-height:calc(100vh - 88px)!important; }
        .q-page > .nicegui-content { padding:0; }
        .dashboard-main { width:100%; max-width:1288px; margin:0 auto; padding:34px 24px 48px; gap:28px; }

        /* ── Page Heading ─────────────────────────────────────────────────── */
        .page-heading { padding-bottom:0; }
        .page-eyebrow { font-size:9px; color:var(--muted); font-weight:600; letter-spacing:1.6px; margin-bottom:4px; }
        .page-title { font-size:36px; font-weight:600; letter-spacing:-1.5px; color:var(--ink); line-height:1.2; }
        .page-description { font-size:13px; color:var(--muted); margin-top:5px; }

        /* ── Resource Grid (Server page 4-cell layout) ────────────────────── */
        .resource-grid {
            grid-template-columns:1.1fr 1fr 1fr 1fr;
            padding:0!important; gap:0!important; overflow:hidden;
        }
        .resource-cell {
            padding:25px 28px; gap:12px; min-height:248px;
            border-right:1px solid var(--stroke);
            display:flex; flex-direction:column;
        }
        .resource-cell:last-child { border-right:0; }
        .resource-cpu { background:var(--brand-soft); align-items:center; }
        .metric-heading { font-size:12px; font-weight:600; color:var(--muted); }
        .metric-icon { color:var(--muted); opacity:.65; }
        .metric-reading { margin-top:13px; margin-bottom:3px; }
        .metric-number {
            font-size:43px; font-weight:550; letter-spacing:-2px; line-height:1.2;
            font-variant-numeric:tabular-nums; color:var(--ink);
        }
        .metric-caption, .metric-footnote {
            font-size:11px; color:var(--muted); line-height:1.5;
            font-variant-numeric:tabular-nums;
        }
        .metric-footnote { padding-top:9px; margin-top:auto; }
        .cpu-dial { position:relative; margin:6px auto 2px; width:112px; height:112px; }
        .dial-value {
            position:absolute; inset:0;
            display:flex; align-items:center; justify-content:center;
            font-size:24px; font-weight:600; letter-spacing:-1px; color:var(--ink);
        }
        .metric-bar { height:8px; border-radius:2px; margin-top:4px; }
        .resource-cell .q-linear-progress__model { opacity:1; }
        .resource-cell .q-linear-progress__track { opacity:.08; }

        /* ── IoT Sensor Cards ─────────────────────────────────────────────── */
        .sensor-card { padding:22px!important; min-height:172px; gap:14px; }
        body .sensor-card .q-badge.bg-positive {
            --q-positive:var(--inset); color:var(--muted)!important; padding:4px 8px;
        }
        .room-readings { margin-top:5px; }
        .room-temperature {
            font-size:43px; font-weight:500; letter-spacing:-2px; line-height:1.1; color:var(--ink);
        }
        .room-caption { font-size:8px; font-weight:600; letter-spacing:1px; color:var(--muted); }
        .room-secondary { color:var(--muted); padding-bottom:3px; }
        .room-detail { font-size:12px; font-variant-numeric:tabular-nums; }

        /* ── Smart Plug Fleet Quick Grid ──────────────────────────────────── */
        .quick-device-grid { grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
        body .fleet-overview { padding:22px!important; }
        .iot-plug-tile .q-btn {
            background:var(--surface)!important; color:var(--ink)!important;
            border:1px solid var(--stroke); border-radius:8px; min-width:48px; box-shadow:none;
        }
        .iot-plug-tile .q-icon { color:var(--muted)!important; }

        /* ── Analysis Panel ───────────────────────────────────────────────── */
        .analysis-panel { margin-top:0!important; padding:18px 22px!important; }
        .analysis-panel .q-label { font-size:12px; }

        /* ── Energy Summary Cards ─────────────────────────────────────────── */
        .energy-summary { min-height:172px; }
        .energy-number {
            color:var(--ink); font-variant-numeric:tabular-nums;
            letter-spacing:-1.2px; font-size:43px;
        }

        /* ── Split Card (Chart Analytics Panel) ──────────────────────────── */
        .dark-highlight-card {
            background:linear-gradient(125deg,#0c5361,#153349);
            color:#f0fdfa; border:1px solid #285266; border-radius:20px; box-shadow:var(--shadow);
        }
        .split-card { display:flex; }
        .split-left {
            flex:0 0 200px; background:var(--brand-soft); color:var(--brand-ink);
            padding:24px;
        }
        .split-left .text-3xl { font-size:25px; font-weight:600; }
        .split-right { background:var(--surface); padding:24px; flex:2; }
        body.body--dark .split-left { background:var(--brand-soft); color:var(--brand-ink); }
        body.body--dark .split-right { background:var(--surface); }

        /* ── Plug Cards (Fleet Manager) ───────────────────────────────────── */
        .plug-card-modern { padding:20px!important; }
        .plug-card-modern.plug-active {
            border-color:color-mix(in srgb,var(--brand) 35%,var(--stroke))!important;
        }
        .plug-card-modern.plug-critical { border-left:3px solid var(--q-warning); }

        /* ── Stat Values ──────────────────────────────────────────────────── */
        .plug-stat-num, .stat-value {
            font-size:1.5rem; font-weight:700; line-height:1.2; color:var(--ink);
        }
        .stat-value { color:var(--brand); }
        .plug-stat-lbl, .stat-label, .plug-section-title {
            font-size:11px; font-weight:600;
            color:var(--muted); letter-spacing:.06em; text-transform:uppercase;
        }

        /* ── Button Styles ────────────────────────────────────────────────── */
        .plug-switch-btn, .plug-toggle, .plug-ctrl-btn, .plug-led-btn, .filter-chip-btn {
            font-family:inherit!important; border-radius:10px!important; font-weight:600!important;
            box-shadow:none!important; letter-spacing:0!important;
        }
        .plug-switch-btn { padding:7px 16px!important; font-size:12px!important; }
        .plug-switch-on, .plug-toggle-on {
            background:var(--brand-soft)!important;
            color:var(--brand-ink)!important;
            border:1px solid color-mix(in srgb,var(--brand) 25%,transparent)!important;
        }
        .plug-switch-off, .plug-toggle-off {
            background:var(--inset)!important; color:var(--muted)!important;
            border:1px solid var(--stroke)!important;
        }
        .plug-switch-warn { background:var(--q-negative)!important; color:var(--canvas)!important; }
        .plug-ctrl-btn, .plug-led-btn {
            background:var(--inset)!important; color:var(--ink)!important;
            border:1px solid var(--stroke)!important; padding:9px 14px!important; font-size:12px!important;
        }
        .plug-ctrl-btn:hover, .plug-led-btn:hover { border-color:var(--brand)!important; }
        .filter-chip-btn { padding:4px 12px!important; font-size:12px!important; }

        /* ── Status Dots ──────────────────────────────────────────────────── */
        .pulse-dot-online, .pulse-dot-offline, .dot-ok, .dot-err {
            display:inline-block; width:8px; height:8px; border-radius:50%;
        }
        .pulse-dot-online, .dot-ok { background:var(--q-positive); }
        .pulse-dot-offline, .dot-err { background:var(--q-negative); }

        /* ── Quasar Component Overrides ───────────────────────────────────── */
        .q-btn-group {
            background:var(--inset)!important; padding:4px;
            border:1px solid var(--stroke)!important;
            border-radius:14px!important; box-shadow:none!important;
        }
        body .q-btn-group .q-btn {
            color:var(--muted)!important; border-radius:10px!important;
            font-weight:600!important; font-size:12px; letter-spacing:0;
        }
        body .q-btn-group .q-btn.bg-primary {
            background:var(--surface)!important;
            color:var(--brand-ink)!important;
            box-shadow:0 2px 5px rgba(0,0,0,.07)!important;
        }
        .q-btn { font-variant-numeric:tabular-nums; }
        .q-btn:focus-visible { outline:2px solid var(--brand); outline-offset:3px; }
        .glass-card .q-linear-progress__model { opacity:.28; }
        .glass-card .q-linear-progress__track { opacity:.08; }
        .glass-card .q-separator { background:var(--stroke)!important; }
        .q-field--outlined .q-field__control { border-radius:12px!important; background:var(--inset); }
        .q-field--outlined .q-field__control:before { border-color:var(--stroke)!important; background:transparent!important; }
        .q-field:hover .q-field__control:before { border-color:color-mix(in srgb,var(--brand) 40%,var(--stroke))!important; }

        /* ── Dropdown / Menu ──────────────────────────────────────────────── */
        .glass-menu {
            background:var(--surface)!important; color:var(--ink)!important;
            border:1px solid var(--stroke)!important; border-radius:14px!important;
            box-shadow:var(--shadow)!important; padding:4px;
        }
        .glass-menu .q-item { border-radius:9px; margin:2px; }
        .glass-menu .q-item:hover, .glass-menu .q-item--active {
            background:var(--brand-soft)!important; color:var(--brand-ink)!important;
        }

        /* ── Utility Color Normalisation ──────────────────────────────────── */
        [class~="text-slate-400"],[class~="text-slate-500"],[class~="text-slate-600"] { color:var(--muted)!important; }
        [class~="text-slate-700"],[class~="text-slate-800"],[class~="text-slate-900"] { color:var(--ink)!important; }
        [class~="text-blue-500"],[class~="text-blue-600"] { color:var(--brand)!important; }
        [class~="text-emerald-500"],[class~="text-teal-600"] { color:var(--q-positive)!important; }
        [class~="text-amber-500"],[class~="text-orange-500"] { color:var(--q-warning)!important; }
        [class~="text-rose-500"] { color:var(--q-negative)!important; }
        [class~="text-purple-700"] { color:var(--q-secondary)!important; }
        .glass-card [class~="bg-slate-200"] { background:var(--inset)!important; }

        /* ── Responsive Breakpoints ───────────────────────────────────────── */
        @media (max-width:1023px) {
            .shell-update { display:none; }
            .resource-cell { padding:22px 18px; }
            .metric-number { font-size:36px; }
            .quick-device-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        @media (max-width:767px) {
            .app-topbar { height:auto; min-height:88px; padding:14px 18px; flex-wrap:wrap; gap:10px; }
            .app-topbar > .workspace-nav { order:3; width:100%; }
            body .workspace-nav.q-btn-group .q-btn { flex:1; padding:0 8px; min-height:32px; }
            .q-page-container { padding-top:130px!important; }
            .dashboard-main { padding:24px 16px; gap:24px; }
            .page-title { font-size:29px; }
            .resource-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .resource-cell {
                min-height:218px; padding:20px 16px;
                border-bottom:1px solid var(--stroke);
            }
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
        @media (prefers-reduced-motion:reduce) { * { transition:none!important; animation:none!important; } }
        </style>
    ''')
