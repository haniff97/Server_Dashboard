"""
aws_iot_publisher.py
====================
Publishes smart plug readings to AWS IoT Core via MQTT over TLS (port 8883).

Design:
  - One connect → publish → disconnect per call.
    Simple and reliable for a 10-second poll loop. No persistent connection
    state to manage across threads.
  - If IOT_ENDPOINT is not set in .env the function is a silent no-op,
    so the dashboard still starts during local dev/testing.
  - Uses paho-mqtt 2.x CallbackAPIVersion.VERSION2 API.

Topic: plug/readings
AWS IoT policy allows:
  iot:Connect  → client ID: orange-pi-smart-plug
  iot:Publish  → topic:     plug/readings
"""

import json
import os
import ssl
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv("/mnt/nvme/Projects/dashboard/.env")

# ── AWS IoT config (set these in .env) ────────────────────────────────────────
IOT_ENDPOINT  = os.getenv("IOT_ENDPOINT")   # e.g. a2mwi46ureof9h-ats.iot.ap-southeast-1.amazonaws.com
IOT_CLIENT_ID = os.getenv("IOT_CLIENT_ID", "orange-pi-smart-plug")
IOT_PORT      = 8883
IOT_TOPIC     = "plug/readings"

# ── Cert paths (copied via scp in setup) ──────────────────────────────────────
_CERT_DIR   = "/mnt/nvme/Projects/dashboard/certs"
CA_CERT     = os.path.join(_CERT_DIR, "amazon-root-ca.pem")
DEVICE_CERT = os.path.join(_CERT_DIR, "device-cert.pem")
PRIVATE_KEY = os.path.join(_CERT_DIR, "device-private-key.pem")

_CONNECT_TIMEOUT_S = 5   # seconds to wait for CONNACK before giving up
_PUBLISH_TIMEOUT_S = 5   # seconds to wait for PUBACK (QoS 1)


def publish(device_key: str, status: dict, wh_delta: float) -> bool:
    """
    Publish one energy reading to AWS IoT Core.

    Args:
        device_key:  'plug' or 'server'  (matches DEVICES keys in tuya_local.py)
        status:      dict returned by tuya_local.get_status()
        wh_delta:    Wh consumed since the previous poll (calculated in plug_polling_loop)

    Returns:
        True on successful delivery, False on any error.

    Call this immediately after a successful tuya poll + DB insert.
    Any exception is caught and printed — never raises, so it cannot crash
    the polling thread.
    """
    if not IOT_ENDPOINT:
        # Silent no-op if env var is missing (e.g. local dev without certs)
        return False

    payload = {
        "device_key":  device_key,
        "device_name": status.get("device_name"),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "switch":      status.get("switch"),
        "watts":       status.get("watts"),
        "voltage":     status.get("voltage"),
        "current_ma":  status.get("current_ma"),
        "add_ele_kwh": status.get("add_ele_kwh"),
        "wh_delta":    round(wh_delta, 6),
    }

    connected_event = threading.Event()
    connect_error: list[str] = []

    def _on_connect(client, userdata, connect_flags, reason_code, properties):
        if reason_code.is_failure:
            connect_error.append(str(reason_code))
        else:
            connected_event.set()

    try:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=IOT_CLIENT_ID,
        )
        client.on_connect = _on_connect
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=DEVICE_CERT,
            keyfile=PRIVATE_KEY,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

        client.connect(IOT_ENDPOINT, IOT_PORT, keepalive=10)
        client.loop_start()

        if not connected_event.wait(timeout=_CONNECT_TIMEOUT_S):
            client.loop_stop()
            client.disconnect()
            reason = connect_error[0] if connect_error else "timeout"
            print(f"[aws_iot] connect failed ({device_key}): {reason}")
            return False

        msg_info = client.publish(IOT_TOPIC, json.dumps(payload), qos=1)
        msg_info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_S)

        client.loop_stop()
        client.disconnect()
        print(f"[aws_iot] published {device_key} → {IOT_TOPIC} ({status['watts']}W)")
        return True

    except Exception as e:
        print(f"[aws_iot] publish error ({device_key}): {e}")
        return False
