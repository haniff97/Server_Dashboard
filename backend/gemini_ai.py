
import os
import time
import json
import requests
import subprocess
import google.generativeai as genai

from dotenv import load_dotenv


# --- CONFIGURATION ---

env_path = "/mnt/nvme/Projects/dashboard/.env" 
load_dotenv(env_path)

API_KEY = os.getenv("GEMINI_API_KEY")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") 

CACHE_FILE = "/mnt/nvme/Projects/dashboard/gemini_cache.txt"

CACHE_DURATION = 1800 



genai.configure(api_key=API_KEY)



def get_live_data():

    stats = {'cpu_percent': 0, 'cpu_temp': 0, 'memory_percent': 0}

    try:

        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:

            stats['cpu_temp'] = round(float(f.read()) / 1000.0, 1)

        

        meminfo = {}

        with open('/proc/meminfo', 'r') as f:

            for line in f:

                parts = line.split()

                if len(parts) >= 2: meminfo[parts[0].replace(':','')] = int(parts[1])

        

        total = meminfo.get('MemTotal', 1)

        available = meminfo.get('MemAvailable', 0)

        stats['memory_percent'] = round(((total - available) / total) * 100, 1)



        cpu_res = requests.get('http://localhost:9090/api/v1/query', params={'query': '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'}).json()

        if cpu_res.get('data', {}).get('result'):

            stats['cpu_percent'] = round(float(cpu_res['data']['result'][0]['value'][1]), 1)


        cmd = "ps -eo comm,%cpu --sort=-%cpu | awk 'NR>1 && $1!=\"ps\" && $1!=\"awk\" {printf \"%-15s %s\\n\", $1, $2}' | head -6"

        stats['top_app'] = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()

    except Exception: pass

    return stats



def analyze_system():

    # Force delete cache for testing if you want, but keep logic for production

    if os.path.exists(CACHE_FILE) and (time.time() - os.path.getmtime(CACHE_FILE) < CACHE_DURATION):

        with open(CACHE_FILE, "r") as f: return f.read()



    live_stats = get_live_data()

    

    # STRICT PROMPT FOR UI CONSISTENCY

    prompt = f"""

    SYSTEM DATA: {json.dumps(live_stats)}

    

    ACT AS: A professional SRE Monitoring Agent.

    OUTPUT RULES:

    1. Reply STRICTLY in 4 lines. 

    2. No "Here is a summary" or extra text.

    3. Use exactly these emojis.



    LINE 1: ⚙️ SYSTEM: [Status of CPU {live_stats['cpu_percent']}% and RAM {live_stats['memory_percent']}%]

    LINE 2: 🌡️ THERMALS: [CPU Temp {live_stats['cpu_temp']}°C status]

    LINE 3: 🔥 TOP APP: [The app {live_stats['top_app']} is the heaviest]

    LINE 4: 💡 INSIGHT: [1 short actionable SRE tip]

    """

    

    try:

        model = genai.GenerativeModel('gemini-2.5-flash')

        response = model.generate_content(prompt)

        analysis = response.text.strip()

        with open(CACHE_FILE, "w") as f: f.write(analysis)

        return analysis

    except Exception as e:

        return f"❌ ERROR: {str(e)[:40]}"



if __name__ == "__main__":

    print(analyze_system())

