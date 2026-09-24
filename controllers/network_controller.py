"""
controllers/network_controller.py
===================================
Network probing, traceroute, Gemini AI analysis, Telegram alerts.
"""
import os
import sys
import asyncio
import subprocess
import re
import urllib.request
import urllib.parse
from datetime import datetime

from nicegui import run

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import models.state as state


# ── Probing helpers (sync — runs in thread pool) ───────────────────────────────
def probe_target(target: str, count: int = 4) -> dict:
    empty = {"latency": 0.0, "jitter": 0.0, "packet_loss": 100.0}
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=count * 3
        )
        out = result.stdout
        loss_m = re.search(r'(\d+(?:\.\d+)?)%\s+packet loss', out)
        packet_loss = float(loss_m.group(1)) if loss_m else 100.0

        rtt_m = re.search(r'min/avg/max/m(?:dev|stddev)\s*=\s*[\d.]+/([\d.]+)/[\d.]+/([\d.]+)', out)
        if rtt_m:
            latency = round(float(rtt_m.group(1)), 2)
            jitter  = round(float(rtt_m.group(2)), 2)
        else:
            latency, jitter = 0.0, 0.0

        return {"latency": latency, "jitter": jitter, "packet_loss": packet_loss}
    except Exception as e:
        print(f"[network] ping error ({target}): {e}")
        return empty


def run_traceroute(target: str) -> list:
    try:
        result = subprocess.run(
            ["traceroute", "-q", "1", "-m", str(state.NETWORK_TRACEROUTE_HOPS), target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=60
        )
        hops = []
        for line in result.stdout.split("\n")[1:]:
            ip_m = re.search(r'\(([\d.]+)\)', line)
            if ip_m:
                hops.append(ip_m.group(1))
            elif re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line):
                hops.append(re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line).group(0))
        return hops
    except Exception as e:
        print(f"[network] traceroute error ({target}): {e}")
        return []


def fetch_network_metrics() -> dict:
    return {t: probe_target(t) for t in state.NETWORK_TARGETS}


def call_gemini_network(summary: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "⚠️ DEEPSEEK_API_KEY not set."
    try:
        import requests as _req
        prompt = (
            "You are a network SRE assistant. Analyse the following homelab network probe data "
            "and give a concise 2–4 sentence diagnosis. State if the issue is internal (LAN/router) "
            "or external (ISP/BGP). If all healthy, confirm it briefly.\n\n"
            f"{summary}"
        )
        resp = _req.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        ts = datetime.now().strftime("%H:%M")
        with open(state.NETWORK_AI_CACHE_PATH, "w") as f:
            f.write(text)
        return f"🕒 Last Analysis: {ts}\n\n{text}"
    except Exception as e:
        return f"❌ DeepSeek error: {str(e)[:60]}"


def send_telegram_alert(message: str):
    if not state.NETWORK_TELEGRAM_TOKEN or not state.NETWORK_TELEGRAM_CHAT:
        return
    try:
        url  = f"https://api.telegram.org/bot{state.NETWORK_TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    state.NETWORK_TELEGRAM_CHAT,
            "text":       message,
            "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        print(f"[network telegram] {e}")


# ── Main async loop ────────────────────────────────────────────────────────────
async def update_network_state():
    while True:
        try:
            results = await run.io_bound(fetch_network_metrics)
            anomaly_targets = []
            all_ok = True

            with state.network_lock:
                for target, data in results.items():
                    td = state.network_state["targets"][target]
                    td["latency"]     = data["latency"]
                    td["packet_loss"] = data["packet_loss"]
                    td["jitter"]      = data["jitter"]
                    td["history"].append(data["latency"])

                    is_anomaly = (
                        data["packet_loss"] >= state.NETWORK_PACKET_LOSS_THRESHOLD
                        or data["latency"]  >= state.NETWORK_LATENCY_THRESHOLD_MS
                    )
                    td["status"] = "warn" if is_anomaly else "ok"
                    if is_anomaly:
                        all_ok = False
                        anomaly_targets.append(target)

                state.network_state["health"] = "GOOD" if all_ok else "WARNING"

            for target in anomaly_targets:
                ts_str = datetime.now().strftime("%H:%M:%S")
                hops = await run.io_bound(run_traceroute, target)

                with state.network_lock:
                    prev = state.network_state["last_traceroute"].get(target, [])
                    td   = state.network_state["targets"][target]
                    msg  = (f"{ts_str} - ⚠️ {target}: "
                            f"{td['packet_loss']:.1f}% loss, {td['latency']:.0f}ms latency")
                    state.network_state["route_log"].insert(0, msg)

                    if prev and hops and hops != prev:
                        flap_msg = f"{ts_str} - 🚨 Route CHANGED on {target} (was {len(prev)} hops, now {len(hops)})"
                        state.network_state["route_log"].insert(0, flap_msg)

                    if hops:
                        state.network_state["last_traceroute"][target] = hops

                    state.network_state["route_log"] = state.network_state["route_log"][:15]

            with state.network_lock:
                was_anomaly = state.network_state["anomaly_active"]
                state.network_state["anomaly_active"] = not all_ok

            if not all_ok and not was_anomaly:
                alert_lines = []
                with state.network_lock:
                    for t in anomaly_targets:
                        td = state.network_state["targets"][t]
                        alert_lines.append(
                            f"  • <b>{t}</b>: {td['packet_loss']:.1f}% loss, {td['latency']:.0f}ms"
                        )
                alert_msg = (
                    "🚨 <b>Network Anomaly Detected</b>\n"
                    + "\n".join(alert_lines)
                    + "\n\nTraceroute triggered. Check dashboard for AI diagnosis."
                )
                await run.io_bound(send_telegram_alert, alert_msg)

        except Exception as e:
            print(f"❌ Network monitor error: {e}")

        await asyncio.sleep(state.NETWORK_PROBE_INTERVAL)
