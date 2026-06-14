"""
tuya_local.py
=============
tinytuya local LAN wrapper for two smart plugs.
No cloud dependency after initial key extraction.

Devices:
  - Smart plug  (192.168.1.2)   -> full control
  - Server plug (192.168.1.15)  -> full control + double-confirm off
"""

import os
import tinytuya
from dotenv import load_dotenv

load_dotenv()

# ── Device configs ─────────────────────────────────────────────────────────

DEVICES = {
    "plug": {
        "name":      "Smart Plug",
        "id":        os.getenv("PLUG_ID"),
        "ip":        os.getenv("PLUG_IP"),
        "key":       os.getenv("PLUG_KEY"),
        "version":   3.5,
        "is_server": False,
    },
    "server": {
        "name":      "Server",
        "id":        os.getenv("SERVER_PLUG_ID"),
        "ip":        os.getenv("SERVER_PLUG_IP"),
        "key":       os.getenv("SERVER_PLUG_KEY"),
        "version":   3.5,
        "is_server": True,
    },
}

# ── DPS key mapping (LN 2S metering plug) ─────────────────────────────────
DPS_SWITCH  = "1"
DPS_CURRENT = "18"   # mA
DPS_POWER   = "19"   # W x 10  → divide by 10
DPS_VOLTAGE = "20"   # V x 10  → divide by 10
DPS_ADD_ELE = "17"   # kWh x 1000 → divide by 1000
DPS_FAULT   = "26"


def _get_device(key: str) -> tinytuya.OutletDevice:
    """Create a fresh tinytuya device connection."""
    cfg = DEVICES[key]
    d = tinytuya.OutletDevice(
        dev_id=cfg["id"],
        address=cfg["ip"],
        local_key=cfg["key"],
        version=cfg["version"],
    )
    d.set_socketPersistent(False)
    d.set_socketTimeout(5)
    d.set_socketRetryLimit(2)
    return d


def get_status(device_key: str) -> dict | None:
    """
    Poll device and return parsed status dict.
    Returns None on failure.
    """
    try:
        d = _get_device(device_key)
        raw = d.status()
        dps = raw.get("dps", {})

        if not dps:
            return None

        return {
            "device_key":  device_key,
            "device_name": DEVICES[device_key]["name"],
            "switch":      bool(dps.get(DPS_SWITCH, False)),
            "watts":       round(dps.get(DPS_POWER, 0) / 10.0, 2),
            "voltage":     round(dps.get(DPS_VOLTAGE, 0) / 10.0, 1),
            "current_ma":  int(dps.get(DPS_CURRENT, 0)),
            "add_ele_kwh": round(dps.get(DPS_ADD_ELE, 0) / 1000.0, 4),
            "fault":       int(dps.get(DPS_FAULT, 0)),
            "raw_dps":     dps,
        }
    except Exception as e:
        print(f"[tuya_local] get_status({device_key}) error: {e}")
        return None


def set_switch(device_key: str, state: bool) -> bool:
    """Turn device on (True) or off (False). Returns True on success."""
    try:
        d = _get_device(device_key)
        result = d.turn_on() if state else d.turn_off()
        if isinstance(result, dict) and result.get("Error"):
            print(f"[tuya_local] set_switch error: {result}")
            return False
        return True
    except Exception as e:
        print(f"[tuya_local] set_switch({device_key}, {state}) error: {e}")
        return False


def set_child_lock(device_key: str, locked: bool) -> bool:
    """Enable or disable child lock."""
    try:
        d = _get_device(device_key)
        result = d.set_value("40", locked)
        if isinstance(result, dict) and result.get("Error"):
            return False
        return True
    except Exception as e:
        print(f"[tuya_local] set_child_lock error: {e}")
        return False


def set_countdown(device_key: str, seconds: int) -> bool:
    """Set countdown timer in seconds (0 = cancel)."""
    try:
        d = _get_device(device_key)
        result = d.set_value("9", seconds)
        if isinstance(result, dict) and result.get("Error"):
            return False
        return True
    except Exception as e:
        print(f"[tuya_local] set_countdown error: {e}")
        return False


def set_led_mode(device_key: str, mode: str) -> bool:
    """Set LED indicator mode: 'relay' | 'pos' | 'none'"""
    if mode not in {"relay", "pos", "none"}:
        return False
    try:
        d = _get_device(device_key)
        result = d.set_value("39", mode)
        if isinstance(result, dict) and result.get("Error"):
            return False
        return True
    except Exception as e:
        print(f"[tuya_local] set_led_mode error: {e}")
        return False


def is_server_plug(device_key: str) -> bool:
    return DEVICES.get(device_key, {}).get("is_server", False)
