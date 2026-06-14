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
