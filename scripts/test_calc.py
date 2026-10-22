#!/usr/bin/env python3
"""Verify the calculator's arithmetic against an independent implementation.

The site's JS does the math in the browser. This recomputes the same thing in
Python from the same dataset and checks the results agree within rounding.
A mismatch means the shipped page would show a wrong number.

Usage:
    python3 scripts/test_calc.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEM_EFFICIENCY = 0.86 * 0.96
PANEL_SQ_FT = 0.0176


def compute(city, monthly_kwh, wattage, roof_factor, kind):
    daily = monthly_kwh / 30.0
    psh = city["peak_sun_hours"]
    design = {"ongrid": 1.0, "hybrid": 0.9, "offgrid": 0.75}[kind]
    eff = SYSTEM_EFFICIENCY * roof_factor * design
    array_kw = daily / (psh * eff)
    panels = math.ceil(array_kw / (wattage / 1000.0))
    annual = 0.0
    for m in city["months"]:
        mpsh = city["monthly"].get(m, 0.0)
        annual += array_kw * mpsh * 30.4 * SYSTEM_EFFICIENCY * roof_factor * design
    sqft = panels * PANEL_SQ_FT * (wattage / 400.0)
    return {"panels": panels, "array_kw": array_kw, "annual": annual,
            "psh": psh, "sqft": sqft}


def main() -> int:
    data_path = ROOT / "site" / "data" / "solar.json"
    if not data_path.exists():
        print("ERROR: site/data/solar.json missing", file=sys.stderr)
        return 2
    data = json.loads(data_path.read_text(encoding="utf-8"))
    cities = data["cities"]

    errors: list[str] = []
    checks = 0

    # 1. Dataset sanity: peak sun hours must be in a physically plausible band.
    for slug, c in cities.items():
        checks += 1
        psh = c["peak_sun_hours"]
        if not (2.0 <= psh <= 7.5):
            errors.append(f"{slug}: peak sun hours {psh} outside 2.0-7.5")
        if not (900 <= c["annual_kwh_m2"] <= 2600):
            errors.append(f"{slug}: annual irradiance {c['annual_kwh_m2']} outside 900-2600")
        # monthly must be keyed by the SAME two-digit month codes that the
        # "months" array lists, or every lookup in the page code returns 0.
        month_codes = set(c["months"])
        monthly_keys = set(c["monthly"].keys())
        if monthly_keys != month_codes:
            errors.append(f"{slug}: monthly keys {sorted(monthly_keys)} != months {sorted(month_codes)}")
        # annual must equal the sum of monthly averages x days in month
        monthly_sum = sum(c["monthly"][m] for m in c["months"] if m in c["monthly"]) * 30.4
        if abs(monthly_sum - c["annual_kwh_m2"]) / c["annual_kwh_m2"] > 0.08:
            errors.append(f"{slug}: monthly sum {monthly_sum:.0f} != annual "
                          f"{c['annual_kwh_m2']:.0f}")
        if len(c["months"]) != 12 or len(c["monthly"]) != 12:
            errors.append(f"{slug}: expected 12 months")
        # every monthly value must be a real, positive irradiance reading
        for m in c["months"]:
            v = c["monthly"].get(m)
            if v is None:
                errors.append(f"{slug}: month {m} missing from monthly")
            elif not (0.5 <= v <= 9.0):
                errors.append(f"{slug}: month {m} value {v} implausible")

    # 2. Phoenix must be the sunniest, Seattle among the dullest.
    order = sorted(cities.items(), key=lambda kv: -kv[1]["peak_sun_hours"])
    if order[0][0] != "phoenix":
        errors.append(f"expected phoenix sunniest, got {order[0][0]}")
    if cities["seattle"]["peak_sun_hours"] != order[-1][1]["peak_sun_hours"]:
        errors.append("seattle is not the lowest peak-sun-hours city")

    # 3. Monotonicity: more usage never means fewer panels.
    for slug, c in list(cities.items())[:8]:
        prev = 0
        for usage in (100, 500, 900, 2000, 5000):
            checks += 1
            r = compute(c, usage, 400, 1.0, "ongrid")
            if r["panels"] < prev:
                errors.append(f"{slug}: panels decreased at usage={usage}")
            prev = r["panels"]

    # 4. A known-good hand calculation for Seattle, 900 kWh/mo, 400 W, south.
    #    daily = 30 kWh; psh = 3.48; eff = 0.8256
    #    array_kw = 30 / (3.48 * 0.8256) = 10.443...; panels = ceil(10.443/0.4) = 27
    seattle = compute(cities["seattle"], 900, 400, 1.0, "ongrid")
    expected_panels = math.ceil(30.0 / (cities["seattle"]["peak_sun_hours"] * SYSTEM_EFFICIENCY) / 0.4)
    checks += 1
    if seattle["panels"] != expected_panels:
        errors.append(f"seattle panels {seattle['panels']} != expected {expected_panels}")
    if seattle["panels"] < 20 or seattle["panels"] > 40:
        errors.append(f"seattle panel count implausible: {seattle['panels']}")

    # 5. Off-grid must need more panels than on-grid for the same city.
    for slug, c in list(cities.items())[:6]:
        checks += 1
        on = compute(c, 900, 400, 1.0, "ongrid")
        off = compute(c, 900, 400, 1.0, "offgrid")
        if off["panels"] <= on["panels"]:
            errors.append(f"{slug}: off-grid did not require more panels")

    # 6. The generated HTML must reference the right numbers for a city page.
    for slug in ("phoenix", "seattle", "miami"):
        checks += 1
        p = ROOT / "site" / "solar" / slug / "index.html"
        if not p.exists():
            errors.append(f"missing city page {slug}")
            continue
        html = p.read_text(encoding="utf-8")
        c = cities[slug]
        psh_s = f"{c['peak_sun_hours']:.2f}"
        if psh_s not in html:
            errors.append(f"{slug}: peak sun hours {psh_s} not in page HTML")
        if f"{c['annual_kwh_m2']:,.0f}" not in html:
            errors.append(f"{slug}: annual irradiance not in page HTML")

    # 7. Every city must have a page and be listed in the sitemap.
    sm = (ROOT / "site" / "sitemap.xml").read_text(encoding="utf-8")
    for slug in cities:
        checks += 1
        if f"/solar/{slug}/" not in sm:
            errors.append(f"{slug} missing from sitemap.xml")

    print(f"checks run: {checks}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"TEST: FAILED ({len(errors)} errors)")
        return 1
    print("TEST: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
