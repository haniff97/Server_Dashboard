
import google.generativeai as genai

import os



# PASTE YOUR KEY HERE MANUALLY ONE LAST TIME

KEY = "AIzaSyCHizHPKchUu2U_a_qia2Zqm7Bq6XiJcVg"



genai.configure(api_key=KEY)



try:

    print("🛰️ Attempting to list models with stable library...")

    for m in genai.list_models():

        if 'generateContent' in m.supported_generation_methods:

            print(f"✅ Ready: {m.name}")

except Exception as e:

    print(f"❌ Still Invalid: {e}")

