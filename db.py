"""
db.py
=====
MariaDB helper for plug energy monitoring.
Handles inserts, daily aggregation, and monthly summaries.
"""

import os
from datetime import date, datetime
from contextlib import contextmanager

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "db"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER", "nextcloud"),
    "password": os.getenv("DB_PASSWORD", "your_strong_password"),
    "database": os.getenv("DB_NAME", "homelab"),
}


@contextmanager
def get_conn():
    """Context manager for DB connection — auto-closes on exit."""
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Inserts ────────────────────────────────────────────────────────────────

def insert_energy(device_id: str, device_name: str,
                  watts: float, wh_delta: float,
                  voltage: float, current_ma: int) -> None:
    """Store a single energy poll reading."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO plug_energy
                (device_id, device_name, watts, wh_delta, voltage, current_ma, polled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (device_id, device_name, watts, wh_delta, voltage, current_ma, datetime.now()))
        cursor.close()


def insert_state_change(device_id: str, device_name: str,
                        state: bool, source: str = "dashboard") -> None:
    """Log a switch state change event."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO plug_state (device_id, device_name, state, source, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (device_id, device_name, 1 if state else 0, source, datetime.now()))
        cursor.close()


# ── Aggregation ────────────────────────────────────────────────────────────

def calculate_tnb_cost(kwh: float) -> float:
    """
    TNB Tariff A residential tiered cost in RM.
    Tiers: 0-200 @ RM0.218 | 201-300 @ RM0.334 | 301-600 @ RM0.516 | 601+ @ RM0.546
    """
    tiers = [
        (200, 0.218),
        (100, 0.334),
        (300, 0.516),
        (float("inf"), 0.546),
    ]
    cost = 0.0
    remaining = kwh
    for limit, rate in tiers:
        if remaining <= 0:
            break
        usage = min(remaining, limit)
        cost += usage * rate
        remaining -= usage
    return round(cost, 4)


def aggregate_daily(device_id: str, date_str: str = None) -> None:
    """
    Aggregate plug_energy rows for a given date into plug_daily_summary.
    Defaults to today if date_str not provided.
    date_str format: 'YYYY-MM-DD'
    """
    if not date_str:
        date_str = date.today().isoformat()

    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                device_id,
                device_name,
                SUM(wh_delta)  AS total_wh,
                AVG(watts)     AS avg_watts,
                MAX(watts)     AS peak_watts,
                COUNT(*)       AS reading_count
            FROM plug_energy
            WHERE DATE(polled_at) = %s AND device_id = %s
            GROUP BY device_id, device_name
        """, (date_str, device_id))

        row = cursor.fetchone()
        if not row:
            cursor.close()
            return

        total_wh  = float(row["total_wh"] or 0)
        total_kwh = total_wh / 1000.0
        cost_rm   = calculate_tnb_cost(total_kwh)

        cursor.execute("""
            INSERT INTO plug_daily_summary
                (device_id, device_name, date, total_wh, cost_rm, avg_watts, peak_watts)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_wh   = VALUES(total_wh),
                cost_rm    = VALUES(cost_rm),
                avg_watts  = VALUES(avg_watts),
                peak_watts = VALUES(peak_watts)
        """, (
            row["device_id"],
            row["device_name"],
            date_str,
            total_wh,
            cost_rm,
            round(float(row["avg_watts"] or 0), 2),
            round(float(row["peak_watts"] or 0), 2),
        ))
        cursor.close()


def aggregate_monthly(device_id: str, year_month: str = None) -> None:
    """
    Aggregate plug_daily_summary for a month into plug_monthly_summary.
    year_month format: 'YYYY-MM'
    """
    if not year_month:
        year_month = date.today().strftime("%Y-%m")

    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                device_id,
                device_name,
                SUM(total_kwh) AS total_kwh
            FROM plug_daily_summary
            WHERE DATE_FORMAT(date, '%%Y-%%m') = %s AND device_id = %s
            GROUP BY device_id, device_name
        """, (year_month, device_id))

        row = cursor.fetchone()
        if not row:
            cursor.close()
            return

        total_kwh = float(row["total_kwh"] or 0)
        cost_rm   = calculate_tnb_cost(total_kwh)

        cursor.execute("""
            INSERT INTO plug_monthly_summary
                (device_id, device_name, `year_month`, total_kwh, cost_rm)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_kwh = VALUES(total_kwh),
                cost_rm   = VALUES(cost_rm)
        """, (row["device_id"], row["device_name"], year_month, total_kwh, cost_rm))
        cursor.close()


# ── Queries ────────────────────────────────────────────────────────────────

def get_today_summary(device_id: str) -> dict:
    """Return today's total kWh and estimated cost for a device."""
    today = date.today().isoformat()
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT COALESCE(SUM(wh_delta), 0) AS total_wh
            FROM plug_energy
            WHERE DATE(polled_at) = %s AND device_id = %s
        """, (today, device_id))
        row = cursor.fetchone()
        cursor.close()

    total_wh  = float(row["total_wh"] or 0)
    total_kwh = total_wh / 1000.0
    return {
        "total_wh":  round(total_wh, 4),
        "total_kwh": round(total_kwh, 6),
        "cost_rm":   calculate_tnb_cost(total_kwh),
    }


def get_power_history(device_id: str, limit: int = 120) -> list:
    """Return last N power readings for chart."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT watts, polled_at
            FROM plug_energy
            WHERE device_id = %s
            ORDER BY polled_at DESC
            LIMIT %s
        """, (device_id, limit))
        rows = cursor.fetchall()
        cursor.close()
    return list(reversed(rows))


def get_monthly_history(device_id: str, months: int = 6) -> list:
    """Return last N months of kWh + cost summaries."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT `year_month`, total_kwh, cost_rm
            FROM plug_monthly_summary
            WHERE device_id = %s
            ORDER BY `year_month` DESC
            LIMIT %s
        """, (device_id, months))
        rows = cursor.fetchall()
        cursor.close()
    return list(reversed(rows))


def get_hourly_history(device_id: str, hours: int = 24) -> list:
    """Return hourly kWh summaries for the last N hours."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                DATE_FORMAT(polled_at, '%Y-%m-%d %H:00:00') as hour_str,
                SUM(wh_delta) / 1000.0 as kwh
            FROM plug_energy
            WHERE device_id = %s AND polled_at >= NOW() - INTERVAL %s HOUR
            GROUP BY hour_str
            ORDER BY hour_str DESC
            LIMIT %s
        """, (device_id, hours, hours))
        rows = cursor.fetchall()
        cursor.close()
    return list(reversed(rows))


def get_daily_history(device_id: str, days: int = 30) -> list:
    """Return daily kWh summaries for the last N days."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT date as date_str, total_wh / 1000.0 as kwh
            FROM plug_daily_summary
            WHERE device_id = %s AND date >= CURDATE() - INTERVAL %s DAY
            ORDER BY date DESC
            LIMIT %s
        """, (device_id, days, days))
        rows = cursor.fetchall()
        cursor.close()
    return list(reversed(rows))
