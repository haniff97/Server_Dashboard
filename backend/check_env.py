import os
from dotenv import load_dotenv

load_dotenv('../.env')

keys = ["GEMINI_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]

for key in keys:
    val = os.getenv(key)
    if val:
        # Show only first 4 chars for safety
        print(f"✅ {key} found: {val[:4]}****")
    else:
        print(f"❌ {key} NOT found in .env")
