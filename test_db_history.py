import asyncio
import os, sys
from datetime import datetime

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import db
from tuya_local import DEVICES

async def test_db():
    try:
        print("Testing Hourly (Day):")
        pts1 = await asyncio.to_thread(db.get_hourly_history, DEVICES["plug"]["id"], 24)
        pts2 = await asyncio.to_thread(db.get_hourly_history, DEVICES["server"]["id"], 24)
        d1 = {p["hour_str"]: p["kwh"] for p in pts1}
        d2 = {p["hour_str"]: p["kwh"] for p in pts2}
        all_hours = sorted(list(set(d1.keys()) | set(d2.keys())))
        pts = [{"hour_str": h, "kwh": d1.get(h, 0) + d2.get(h, 0)} for h in all_hours]
        labels = [datetime.strptime(p["hour_str"], "%Y-%m-%d %H:%M:%S").strftime("%H:00") for p in pts]
        values = [round(p["kwh"], 3) for p in pts]
        total_kwh = sum(values)
        print(f"Hourly cost: {db.calculate_tnb_cost(total_kwh)}")
        
        print("\nTesting Daily (Week):")
        pts1 = await asyncio.to_thread(db.get_daily_history, DEVICES["plug"]["id"], 7)
        pts2 = await asyncio.to_thread(db.get_daily_history, DEVICES["server"]["id"], 7)
        d1 = {str(p["date_str"]): p["kwh"] for p in pts1}
        d2 = {str(p["date_str"]): p["kwh"] for p in pts2}
        all_days = sorted(list(set(d1.keys()) | set(d2.keys())))
        pts = [{"date_str": d, "kwh": d1.get(d, 0) + d2.get(d, 0)} for d in all_days]
        labels = [datetime.strptime(str(p["date_str"]), "%Y-%m-%d").strftime("%b %d") for p in pts]
        values = [round(p["kwh"], 3) for p in pts]
        total_kwh = sum(values)
        print(f"Daily cost: {db.calculate_tnb_cost(total_kwh)}")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_db())
