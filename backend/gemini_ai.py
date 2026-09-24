"""
gemini_ai.py — now powered by DeepSeek (OpenAI-compatible API).
Button-triggered only — no auto-timer, no wasted tokens.
Called from homelab-bot when user requests a summary or an anomaly is detected.
"""
import os
import json
import requests
import subprocess

from dotenv import load_dotenv

load_dotenv("/mnt/nvme/Projects/dashboard/.env")

API_KEY       = os.getenv("DEEPSEEK_API_KEY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CACHE_FILE    = "/mnt/nvme/Projects/dashboard/gemini_cache.txt"

DEEPSEEK_URL  = "https://api.deepseek.com/chat/completions"
MODEL         = "deepseek-chat"


def get_live_data() -> dict:
    stats = {"cpu_percent": 0, "cpu_temp": 0, "memory_percent": 0, "top_app": ""}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            stats["cpu_temp"] = round(float(f.read()) / 1000.0, 1)

        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].replace(":", "")] = int(parts[1])
        total     = meminfo.get("MemTotal", 1)
        available = meminfo.get("MemAvailable", 0)
        stats["memory_percent"] = round(((total - available) / total) * 100, 1)

        cpu_res = requests.get(
            "http://localhost:9090/api/v1/query",
            params={"query": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'},
            timeout=5,
        ).json()
        if cpu_res.get("data", {}).get("result"):
            stats["cpu_percent"] = round(float(cpu_res["data"]["result"][0]["value"][1]), 1)

        cmd = "ps -eo comm,%cpu --sort=-%cpu | awk 'NR>1 && $1!=\"ps\" && $1!=\"awk\" {printf \"%-15s %s\\n\", $1, $2}' | head -6"
        stats["top_app"] = subprocess.check_output(cmd, shell=True).decode().strip()
    except Exception:
        pass
    return stats


def analyze_system(triggered_by: str = "manual") -> str:
    """
    Call DeepSeek to generate a system summary.
    triggered_by: 'manual' (button) or 'anomaly' (auto-triggered by threshold breach)
    Result is written to CACHE_FILE so the dashboard can read it.
    """
    if not API_KEY:
        return "⚠️ DEEPSEEK_API_KEY not set."

    live = get_live_data()

    prompt = f"""
SYSTEM DATA: {json.dumps(live)}

ACT AS: A professional SRE Monitoring Agent.
OUTPUT RULES:
1. Reply STRICTLY in 4 lines.
2. No "Here is a summary" or extra text.
3. Use exactly these emojis.

LINE 1: ⚙️ SYSTEM: [Status of CPU {live['cpu_percent']}% and RAM {live['memory_percent']}%]
LINE 2: 🌡️ THERMALS: [CPU Temp {live['cpu_temp']}°C status]
LINE 3: 🔥 TOP APP: [{live['top_app']} is the heaviest process]
LINE 4: 💡 INSIGHT: [1 short actionable SRE tip]
"""

    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        analysis = resp.json()["choices"][0]["message"]["content"].strip()

        with open(CACHE_FILE, "w") as f:
            f.write(f"[{triggered_by.upper()}]\n{analysis}")

        return analysis
    except Exception as e:
        return f"❌ DeepSeek error: {str(e)[:60]}"


if __name__ == "__main__":
    print(analyze_system())
