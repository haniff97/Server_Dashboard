# TNB cost estimates

Default account: Peninsular Malaysia Domestic General (non-NEM).
Rates verified 9 October 2026 from:
- https://www.mytnb.com.my/tariff/PDF/jadual-tarif-elektrik-terkini-2-julai-2025.pdf
- https://www.mytnb.com.my/tariff/js/rates.js
- https://www.mytnb.com.my/tariff/js/calculator-newDomestic.js
- https://www.tnb.com.my/announcements/peningkatan-aras-perlindungan-hingga-800kwj-pelanggan-terima-kredit-pro-rat

The shared services/tnb_tariff.py calculator includes energy, capacity, network,
efficiency incentive, monthly retail charge, AFA, 8% service tax and 1.6% KWTBB.
October AFA is +RM0.0361/kWh. Protection is 800 kWh for September–December
2026; otherwise 600. Energy and incentive bands apply to total monthly usage,
not progressive blocks. Component rounding follows TNB's calculator.

Device/day costs share one calendar-month estimate in proportion to their kWh.
The basis is SUM(wh_delta) across all monitored devices that month, so plug
measurements must not overlap (e.g. a feeder and a device on that feeder).
Raw monthly energy records must remain available for the allocation basis.
Chart periods crossing months are grouped by month before costing.
Monthly cost history is recalculated on read; stored daily costs are snapshots.

This is not an exact household bill: unmonitored appliances, actual meter-cycle
dates, minimum charges, special rebates, NEM/ToU, and September adjustment
credits are not modeled. Calendar-month totals are month-to-date, not forecasts.
Historical pre-July-2025 estimates retain legacy energy tiers only.

Update AFA in services/tnb_tariff.py after each official monthly publication.
Forecast rates have not been installed. Missing chargeable-month AFA raises
an error instead of silently reusing October's rate. No database migration needed.
Run: python3 -m unittest test_tnb_tariff -v
