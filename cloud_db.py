"""
cloud_db.py — boto3 wrapper for reading plug readings from DynamoDB.
Used by the /cloud page in the homelab dashboard.
Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in .env.
"""
import os
from dotenv import load_dotenv
load_dotenv("/mnt/nvme/Projects/dashboard/.env")
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone, timedelta

AWS_REGION = "ap-southeast-1"
TABLE_NAME = "plug-readings"


def _get_table():
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    return dynamodb.Table(TABLE_NAME)


def get_recent_readings(device_key: str, limit: int = 20) -> list:
    """Return the most recent readings for a device (last 24h, newest first)."""
    try:
        table = _get_table()
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        resp = table.query(
            KeyConditionExpression=(
                Key("device_key").eq(device_key) & Key("timestamp").gte(since)
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])
    except Exception as e:
        print(f"[cloud_db] get_recent_readings({device_key}) error: {e}")
        return []


def get_today_summary(device_key: str) -> dict:
    """Return today's energy summary for a device."""
    try:
        table = _get_table()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp = table.query(
            KeyConditionExpression=(
                Key("device_key").eq(device_key) & Key("timestamp").begins_with(today)
            ),
        )
        items = resp.get("Items", [])
        if not items:
            return {"readings": 0, "total_wh": 0.0, "avg_watts": 0.0, "peak_watts": 0.0}
        watts_list = [float(i.get("watts", 0)) for i in items]
        total_wh   = sum(float(i.get("wh_delta", 0)) for i in items)
        return {
            "readings":   len(items),
            "total_wh":   round(total_wh, 4),
            "total_kwh":  round(total_wh / 1000, 6),
            "avg_watts":  round(sum(watts_list) / len(watts_list), 2),
            "peak_watts": round(max(watts_list), 2),
        }
    except Exception as e:
        print(f"[cloud_db] get_today_summary({device_key}) error: {e}")
        return {"readings": 0, "total_wh": 0.0, "avg_watts": 0.0, "peak_watts": 0.0}
