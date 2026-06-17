# Server Dashboard — Project Context

## What This Project Does

This is a **Homelab Server Dashboard** — a real-time monitoring and control system for a self-hosted home server. It gives a live view of hardware health, IoT sensor data, smart plug power consumption, and AI-generated system insights, all from a single web UI.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend / UI** | [NiceGUI](https://nicegui.io/) (Python-based reactive UI) |
| **Metrics Backend** | Prometheus + Node Exporter |
| **IoT Integration** | ESP32 sensors via MQTT → Prometheus |
| **Smart Plug Control** | Tuya Cloud API (HMAC-SHA256 signed requests) |
| **AI Insights** | Google Gemini API (`gemini-2.5-flash`) |
| **Notifications** | Telegram Bot |
| **Process Manager** | PM2 (`ecosystem.config.js`) |
| **Deployment** | Helm chart (Kubernetes) |

---

## Pages

### `/` — Server Monitor
Displays live system performance pulled from **Prometheus**:
- **CPU** — usage % (via `node_cpu_seconds_total`) + temperature (from `/sys/class/thermal/`)
- **Memory** — used / total GB with a progress bar
- **NVMe SSD** — usage % + temperature (via `smartctl`)
- **HDD** — usage % + active/idle status (via `iostat`)
- **IoT Cards** — temperature & humidity from ESP32 sensors (MQTT → Prometheus)
- **Smart Plug Card** — live power (W), voltage (V), current (A), energy today (kWh), toggle ON/OFF
- **DeepMind Analysis** — AI-generated 4-line SRE health summary, refreshed every 30 min and cached to disk

### `/energy` — Energy Monitor
Tracks power draw of the smart plug over time:
- Gauge showing current **kW draw**
- **Total kWh today** (accumulated since midnight)
- **Peak usage** this session
- **Estimated cost** using TNB (Tenaga Nasional Berhad) Malaysian electricity tariff tiers with rebates
- Area chart and line chart with **Daily / Weekly / Monthly** timeframe toggle

---

## Key Components

### `frontend/dashboard.py`
Main application entry point. Contains both pages (`/` and `/energy`), all UI layout, Tuya API integration (HMAC-SHA256 token auth + polling thread), Prometheus queries, and background async update loops.

### `frontend/dashboard_design.py`
Design variant / visual experiments for the dashboard layout.

### `mqtt/mqtt_exporter.py`
MQTT → Prometheus bridge. Subscribes to `homelab/esp32/+/{temperature,humidity,motion,light}` topics from ESP32 devices and exposes them as Prometheus Gauges on port **9324**.

### `backend/gemini_ai.py`
Gemini AI analysis module. Queries live CPU/RAM/temp data, sends a structured SRE-style prompt to `gemini-2.5-flash`, and writes the result to a cache file. The dashboard reads this cache file every 5 minutes to display AI insights.

### `backend/telegram_bot.py`
Sends alert notifications via Telegram (used for system health alerts).

### `tuya_plug.py`
Standalone Tuya smart plug utility for device discovery and testing.

### `helm/`
Kubernetes Helm chart for deploying the dashboard (Nginx static deployment tested via CI/CD with GitHub Actions).

### `ecosystem.config.js`
PM2 process configuration — defines how `dashboard.py`, `gemini_ai.py`, and `mqtt_exporter.py` run as managed background processes on the server.

---

## Data Flow

```
ESP32 Sensors
    └─► MQTT Broker (localhost:1883)
            └─► mqtt_exporter.py (port 9324)
                    └─► Prometheus (port 9090)
                            └─► dashboard.py (queries Prometheus)
                                    └─► NiceGUI UI (browser)

Tuya Smart Plug
    └─► Tuya Cloud API (HMAC-SHA256)
            └─► dashboard.py polling thread (every 30s)
                    ├─► Prometheus Gauge (port 2000, scraped by Prometheus)
                    └─► NiceGUI UI live labels

gemini_ai.py (runs via PM2 on cron)
    └─► Prometheus + /proc/meminfo + /sys/class/thermal
            └─► Gemini API (gemini-2.5-flash)
                    └─► gemini_cache.txt
                            └─► dashboard.py reads & displays
```

---

## Environment Variables (`.env` at `/mnt/nvme/Projects/dashboard/.env`)

| Variable | Purpose |
|---|---|
| `TUYA_CLIENT_ID` | Tuya Cloud app client ID |
| `TUYA_CLIENT_SECRET` | Tuya Cloud app secret (used for HMAC signing) |
| `TUYA_DEVICE_ID` | Target smart plug device ID |
| `TUYA_REGION` | Tuya API region (e.g. `sg` for Singapore) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID for alerts |

---

## How to Run (via PM2)

```bash
pm2 start ecosystem.config.js   # Start all services
pm2 logs                         # View logs
pm2 status                       # Check process health
```

The dashboard UI is served by NiceGUI (default port **8080**).
Tuya plug metrics are exported to Prometheus on port **2000**.
ESP32 MQTT metrics are exported to Prometheus on port **9324**.


# Tuya Smart Plug Rewrite — Session 2 Handoff
## tinytuya + MariaDB + NiceGUI

---

## What Was Done This Session

### 1. Discovered Two Smart Plugs
Both are **LN 2S metering plugs** (计量插座), same model, firmware 3.5.

| Name | Device ID | Local Key | IP | Version |
|---|---|---|---|---|
| Smart Plug | `a3f2f187ed028f5920seoc` | `-rU&}hvPr8G#&!?s` | 192.168.1.2 | 3.5 |
| Server | `a3a5ce31b84c12052bpneu` | `h+h.yxZD/'sNo\|5\|` | 192.168.1.15 | 3.5 |

### 2. Extracted Local Keys via tinytuya Wizard
- Tuya IoT Platform: `iot.tuya.com`
- Project: **Loxal IOT**
- Data Center: **Singapore (cn region)**
- Access ID: `uk9rat79w4wk8wmjep7m`
- Keys saved to `devices.json` in dashboard project root

### 3. Correct DPS Key Mapping (LN 2S)
| DPS | Code | Unit | Scale | How to read |
|---|---|---|---|---|
| `1` | switch_1 | bool | - | True/False |
| `17` | add_ele | kWh | 3 | ÷ 1000 = kWh (lifetime cumulative) |
| `18` | cur_current | mA | 0 | direct value |
| `19` | cur_power | W | 1 | ÷ 10 = watts |
| `20` | cur_voltage | V | 1 | ÷ 10 = volts |
| `26` | fault | bitmap | - | 0 = no fault |

> Note: DPS 22, 23, 24, 25 are calibration coefficients, NOT power readings.

### 4. Created MariaDB Database & Tables
- Reused existing `db` container on `nextcloud-net`
- Created new database: `homelab`
- Created new user: `serverdashboard` / `Hnff9710!`
- MariaDB container IP: `172.19.0.2`

```sql
-- Tables created:
plug_state           -- on/off events
plug_energy          -- raw wattage readings every 10s
plug_daily_summary   -- aggregated daily kWh + RM cost
plug_monthly_summary -- aggregated monthly kWh + RM cost
```

### 5. Written Three New Files

| File | Location | Purpose |
|---|---|---|
| `tuya_local.py` | `/mnt/nvme/Projects/dashboard/` | tinytuya LAN wrapper |
| `db.py` | `/mnt/nvme/Projects/dashboard/` | MariaDB insert/query functions |
| `tuya_plug.py` | `/mnt/nvme/Projects/dashboard/` | NiceGUI dashboard (replaces old cloud version) |

### 6. Installed Dependencies (in venv)
```bash
pip install tinytuya mysql-connector-python python-dotenv nicegui prometheus_client prometheus-api-client
```

### 7. Updated .env
```env
GEMINI_API_KEY=AIzaSyCpHqVpaEaVfHsxWMPX11XRhsQF_0LWaS4

TELEGRAM_TOKEN=7974388286:AAHfo5YiYY1z4g7XbogZ-UG67MzriLpNkHg
TELEGRAM_CHAT_ID=569894825

TUYA_CLIENT_ID=uk9rat79w4wk8wmjep7m
TUYA_CLIENT_SECRET=ac4550f840574520b6aa7ce3aae22faa
TUYA_DEVICE_ID=a3f2f187ed028f5920seoc
TUYA_REGION=sg

PLUG_ID=a3f2f187ed028f5920seoc
PLUG_IP=192.168.1.2
PLUG_KEY=-rU&}hvPr8G#&!?s

SERVER_PLUG_ID=a3a5ce31b84c12052bpneu
SERVER_PLUG_IP=192.168.1.15
SERVER_PLUG_KEY=h+h.yxZD/'sNo|5|

DB_HOST=172.19.0.2
DB_PORT=3306
DB_USER=serverdashboard
DB_PASSWORD=Hnff9710!
DB_NAME=homelab
```

---

## Current PM2 Services

| ID | Name | Port | Status | Notes |
|---|---|---|---|---|
| 0 | mqtt-exporter | - | online | existing |
| 1 | homelab-bot | - | online | existing |
| 3 | homelab-dashboard | 3003 | online | NEW tuya plug monitor |
| 4 | old-dashboard | 3000 | fixing | primary dashboard (CPU/RAM/storage) |

---

## Current Issue (Unresolved)

The old dashboard (`frontend/dashboard.py`) is crashing because:
1. ~~Missing `prometheus_api_client`~~ → fixed, installed
2. **Port 2000 conflict** — both `tuya_plug.py` (id 3) and `frontend/dashboard.py` (id 4) try to start Prometheus on port 2000

### Fix Needed
Edit `/mnt/nvme/Projects/dashboard/frontend/dashboard.py` line 82:
```python
# Change from:
start_http_server(2000)

# Change to:
start_http_server(2001)
```

Then:
```bash
pm2 restart 4
```

---

## Dashboard URLs

| Dashboard | URL | Purpose |
|---|---|---|
| Old (primary) | `http://192.168.1.10:3000` | CPU, RAM, storage, MQTT stats |
| New (tuya) | `http://192.168.1.10:3003` | Smart plug power monitoring |
| Tailscale old | `http://100.112.81.102:3000` | Remote access |
| Tailscale new | `http://100.112.81.102:3003` | Remote access |

---

## Architecture

```
Smart Plug (192.168.1.2)   ─┐
                              ├── tinytuya (LAN port 6668)
Server Plug (192.168.1.15) ─┘        │
                                      ↓
                              tuya_local.py
                                      │
                              tuya_plug.py (NiceGUI port 3003)
                                      │
                              db.py ──→ MariaDB (172.19.0.2)
                                              │
                                      Grafana (port 3001)
```

---

## Server Plug Double-Confirm OFF Logic

The server plug (192.168.1.15) has a safety feature:
- **1st click OFF** → button turns amber, warning banner appears
- **2nd click OFF** → actually cuts power
- **Click ON anytime** → resets confirmation state, turns on normally

---

## TNB Cost Calculation

Rates stored in `db.py → calculate_tnb_cost()`:

| Block | kWh Range | Rate |
|---|---|---|
| 1 | 1–200 | RM 0.218/kWh |
| 2 | 201–300 | RM 0.334/kWh |
| 3 | 301–600 | RM 0.516/kWh |
| 4 | 601+ | RM 0.546/kWh |

Storage flow: `watts → Wh delta (per poll) → kWh (daily) → RM cost`

---

## Known Bugs Fixed This Session

| Bug | Fix |
|---|---|
| `chart.options` has no setter (NiceGUI version change) | Use `chart.options.update()` instead |
| Port 2000 conflict between old and new Prometheus | Change old dashboard to port 2001 |
| `externally-managed-environment` pip error | Always use `source venv/bin/activate` first |
| `year_month` reserved word in MariaDB | Wrap in backticks in SQL |

---

## TODO / Next Steps

- [ ] Fix old dashboard Prometheus port (2000 → 2001) and confirm port 3000 works
- [ ] Add daily aggregation cron job (runs at midnight, updates `plug_daily_summary`)
- [ ] Add monthly aggregation cron job (runs on 1st of month)
- [ ] Connect Grafana to MariaDB `homelab` database for energy panels
- [ ] Assign static IP to smart plugs via router DHCP reservation (prevent IP changes)
- [ ] Test double-confirm OFF on server plug
- [ ] Verify wattage readings with something plugged in
