from google import genai
import os

# Use your existing key
API_KEY = "YOUR_API_KEY_HERE"
client = genai.Client(api_key=API_KEY)

print("📡 Pinging Google AI Gateway...")

try:
    # This specifically asks Google "What can this key actually do?"
    models = client.models.list()
    print("\n✅ SUCCESS! Your key can see these models:")
    for m in models:
        print(f"  - {m.name}")
except Exception as e:
    print(f"\n❌ FAILED: The API returned an error.")
    print(f"Error Details: {e}")
