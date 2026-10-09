"""Domestic General calendar-month estimates, RP4 (July 2025–December 2027).
Source: https://www.mytnb.com.my/tariff/js/rates.js
and js/calculator-newDomestic.js, verified 2026-10-09.
Plug totals are a monitored-load estimate, not a household meter reading.
Future AFA forecasts deliberately excluded. No NEM, ToU, special rebates,
minimum bill, arrears, billing-cycle proration or September adjustment credits.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import math

INCENTIVES = ((200, '.25'), (250, '.245'), (300, '.225'),
    (350, '.21'), (400, '.17'), (450, '.145'), (500, '.12'),
    (550, '.105'), (600, '.09'), (650, '.075'), (700, '.055'),
    (750, '.045'), (800, '.04'), (850, '.025'), (900, '.01'), (1000, '.005'))
AFA = dict(zip(('2025-07','2025-08','2025-09','2025-10','2025-11','2025-12',
    '2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07',
    '2026-08','2026-09','2026-10'),
    ('0','-.0145','-.0110','-.0650','-.0891','-.0642','-.0499','-.0277',
     '-.0215','-.0047','.0138','.0259','.0359','.0380','.0367','.0361')))

def _usage(value):
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError('Usage must be finite and non-negative')
    return Decimal(str(value))

def _rm(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def calculate_tnb_cost(kwh, *, year_month=None):
    """Full monthly estimate in RM; do not apply brackets to individual days."""
    usage = _usage(kwh)
    month = year_month or date.today().strftime('%Y-%m')
    date.fromisoformat(month + '-01')
    if not usage:
        return 0.0
    if month < '2025-07':
        # Historical Tariff A had a separate 601–900 tier.
        remaining, cost = usage, Decimal(0)
        for size, rate in ((200,'.218'),(100,'.334'),(300,'.516'),(300,'.546'),(float('inf'),'.571')):
            part = min(remaining, Decimal(str(size)))
            cost += part * Decimal(rate)
            remaining -= part
        return float(_rm(cost))
    if month > '2027-12':
        raise ValueError('RP4 tariff expires December 2027; update rates')
    protection = 800 if '2026-09' <= month <= '2026-12' else 600
    incentive = next((Decimal(rate) for limit, rate in INCENTIVES if usage <= limit), Decimal(0))
    energy = Decimal('.3703' if usage > 1500 else '.2703')
    retail = Decimal(10) if usage > protection else Decimal(0)
    if usage > protection and month not in AFA:
        raise ValueError(f'AFA not published locally for {month}; update AFA table')
    fuel_rate = Decimal(AFA.get(month, '0')) if usage > protection else Decimal(0)
    non_tax_usage = min(usage, Decimal(protection))
    taxable_usage = usage - non_tax_usage
    rates = (energy, Decimal('.0455'), Decimal('.1285'), fuel_rate)
    rebate = _rm(usage*incentive)
    non_tax_rebate = rebate*non_tax_usage/usage
    taxable_rebate = rebate - non_tax_rebate
    non_tax = _rm(sum((_rm(non_tax_usage*rate) for rate in rates), Decimal(0)) - non_tax_rebate)
    taxable = _rm(sum((_rm(taxable_usage*rate) for rate in rates), Decimal(0)) + retail - taxable_rebate)
    tax = _rm(taxable*Decimal('.08')) if taxable_usage else Decimal(0)
    levy_base = sum((_rm(non_tax_usage*rate)+_rm(taxable_usage*rate)
                     for rate in rates[:3]), Decimal(0)) - rebate
    levy = _rm(levy_base*Decimal('.016')) if usage > 300 else Decimal(0)
    return float(_rm(non_tax + taxable + tax + levy))


def allocate_tnb_cost(kwh, monthly_kwh, *, year_month=None):
    """Allocate a single monthly estimate by consumption, without repeated fees."""
    usage, monthly = _usage(kwh), _usage(monthly_kwh)
    if usage > monthly:
        raise ValueError('Allocated usage cannot exceed monthly usage')
    if not monthly:
        return 0.0
    return round(calculate_tnb_cost(float(monthly), year_month=year_month) * float(usage/monthly), 6)
