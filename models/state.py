"""
models/state.py
===============
Single source of truth for all shared global state.
Import this module anywhere — no circular dependency risk.
"""
import os
import threading
from collections import deque
from typing import Any, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
#  ENV
# ─────────────────────────────────────────────────────────────────────────────
NETWORK_TARGETS = ["8.8.8.8", "fast.com", "youtube.com"]
NETWORK_TARGET_LABELS = {
    "8.8.8.8":     "Google",
    "fast.com":    "Fast.com",
    "youtube.com": "YouTube",
}
NETWORK_PROBE_INTERVAL        = 10    # seconds between ping cycles
NETWORK_TRACEROUTE_HOPS       = 20
NETWORK_AI_INTERVAL           = 300
NETWORK_PACKET_LOSS_THRESHOLD = 1.0   # %
NETWORK_LATENCY_THRESHOLD_MS  = 150   # ms
NETWORK_AI_CACHE_PATH  = "/mnt/nvme/Projects/dashboard/gemini_network_cache.txt"
NETWORK_TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
NETWORK_TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY         = os.getenv("GEMINI_API_KEY", "")

PLUG_POLL_INTERVAL = 10  # seconds
AI_CACHE_PATH = "/mnt/nvme/Projects/dashboard/gemini_cache.txt"

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM STATE
# ─────────────────────────────────────────────────────────────────────────────
system_stats: Dict[str, Any] = {
    'cpu_percent': 0, 'cpu_temp': 0,
    'memory_percent': 0, 'memory_used_gb': 0, 'memory_total_gb': 0,
    'nvme_percent': 0, 'nvme_used_gb': 0, 'nvme_total_gb': 0, 'nvme_temp': 0,
    'hdd_percent': 0, 'hdd_used_gb': 0, 'hdd_total_gb': 0, 'hdd_status': 'unknown',
}
iot_devices: Dict[str, Any] = {}
ai_insights   = "🤖 Initializing AI analysis...\n💡 Gathering system data..."
last_update   = ""

# ─────────────────────────────────────────────────────────────────────────────
#  PLUG STATE
# ─────────────────────────────────────────────────────────────────────────────
plug_state: Dict[str, Dict[str, Any]] = {
    "plug":      {"status": None, "ok": False, "history": deque(maxlen=120)},
    "server":    {"status": None, "ok": False, "history": deque(maxlen=120)},
    "extension": {"status": None, "ok": False, "history": deque(maxlen=120)},
}
plug_lock       = threading.Lock()
db_error_notified = False

# ─────────────────────────────────────────────────────────────────────────────
#  ENERGY CACHE
# ─────────────────────────────────────────────────────────────────────────────
energy_cache: Dict[str, dict] = {
    "plug":      {"total_kwh": 0, "cost_rm": 0},
    "server":    {"total_kwh": 0, "cost_rm": 0},
    "extension": {"total_kwh": 0, "cost_rm": 0},
}
energy_cache_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
#  NETWORK STATE
# ─────────────────────────────────────────────────────────────────────────────
network_state: Dict[str, Any] = {
    "health": "GOOD",
    "targets": {
        t: {
            "latency":     0.0,
            "packet_loss": 0.0,
            "jitter":      0.0,
            "status":      "ok",
            "history":     deque([0.0] * 60, maxlen=60),
        }
        for t in NETWORK_TARGETS
    },
    "route_log":      [],
    "ai_insights":    "🤖 Network AI Active...\n💡 Waiting for first probe cycle...",
    "last_traceroute": {},
    "last_ai_run":    0.0,
    "anomaly_active": False,
}
network_lock = threading.Lock()
