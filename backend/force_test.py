
import google.generativeai as genai

import os

from dotenv import load_dotenv

# PASTE YOUR KEY HERE MANUALLY ONE LAST TIME

env_path = "/mnt/nvme/Projects/dashboard/.env" 
load_dotenv(env_path)

KEY = os.getenv("GEMINI_API_KEY") 



genai.configure(api_key=KEY)



try:

    print("🛰️ Attempting to list models with stable library...")

    for m in genai.list_models():

        if 'generateContent' in m.supported_generation_methods:

            print(f"✅ Ready: {m.name}")

except Exception as e:

    print(f"❌ Still Invalid: {e}")

