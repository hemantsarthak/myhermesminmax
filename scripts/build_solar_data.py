#!/usr/bin/env python3
"""Build the solar irradiance dataset from NASA POWER (free, no API key).

For each city we pull one full year of daily global horizontal irradiance
(ALLSKY_SFC_SW_DWN, kWh/m2/day) plus the monthly averages used for the
"solar panel output by month" tables. The result is a JSON file the static
site embeds, so the browser can do all math client-side with no API call.

Why this dataset is the moat: every generic "solar panel calculator" uses a
flat 4 peak-sun-hours assumption for the whole country. Real per-city,
per-month irradiance from a satellite reanalysis is something no content farm
has, and it is exactly what makes a page worth ranking for
"<city> solar panel output".

Usage:
    python3 scripts/build_solar_data.py [--out site/data/solar.json] [--year 2024]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = ("https://power.larc.nasa.gov/api/temporal/daily/point"
       "?parameters=ALLSKY_SFC_SW_DWN&community=RE"
       "&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON")

# city -> (lat, lon, state/region label, country)
CITIES: dict[str, tuple[float, float, str, str]] = {
    "austin": (30.2672, -97.7431, "Texas", "US"),
    "atlanta": (33.7490, -84.3880, "Georgia", "US"),
    "baltimore": (39.2904, -76.6122, "Maryland", "US"),
    "boston": (42.3601, -71.0589, "Massachusetts", "US"),
    "charlotte": (35.2271, -80.8431, "North Carolina", "US"),
    "chicago": (41.8781, -87.6298, "Illinois", "US"),
    "cleveland": (41.4993, -81.6944, "Ohio", "US"),
    "dallas": (32.7767, -96.7970, "Texas", "US"),
    "denver": (39.7392, -104.9903, "Colorado", "US"),
    "detroit": (42.3314, -83.0458, "Michigan", "US"),
    "houston": (29.7604, -95.3698, "Texas", "US"),
    "indianapolis": (39.7684, -86.1581, "Indiana", "US"),
    "jacksonville": (30.3322, -81.6557, "Florida", "US"),
    "kansas-city": (39.0997, -94.5786, "Missouri", "US"),
    "las-vegas": (36.1699, -115.1398, "Nevada", "US"),
    "los-angeles": (34.0522, -118.2437, "California", "US"),
    "louisville": (38.2527, -85.7585, "Kentucky", "US"),
    "memphis": (35.1495, -90.0490, "Tennessee", "US"),
    "miami": (25.7617, -80.1918, "Florida", "US"),
    "milwaukee": (43.0389, -87.9065, "Wisconsin", "US"),
    "minneapolis": (44.9778, -93.2650, "Minnesota", "US"),
    "nashville": (36.1627, -86.7816, "Tennessee", "US"),
    "new-orleans": (29.9511, -90.0715, "Louisiana", "US"),
    "new-york": (40.7128, -74.0060, "New York", "US"),
    "phoenix": (33.4484, -112.0740, "Arizona", "US"),
    "pittsburgh": (40.4406, -79.9959, "Pennsylvania", "US"),
    "portland": (45.5152, -122.6784, "Oregon", "US"),
    "raleigh": (35.7796, -78.6382, "North Carolina", "US"),
    "richmond": (37.5407, -77.4360, "Virginia", "US"),
    "san-antonio": (29.4241, -98.4936, "Texas", "US"),
    "san-diego": (32.7157, -117.1611, "California", "US"),
    "san-francisco": (37.7749, -122.4194, "California", "US"),
    "seattle": (47.6062, -122.3321, "Washington", "US"),
    "st-louis": (38.6270, -90.1994, "Missouri", "US"),
    "tampa": (27.9506, -82.4572, "Florida", "US"),
}


def fetch(lat: float, lon: float, year: int) -> dict:
    start = f"{year}0101"
    end = f"{year}1231"
    url = API.format(lat=lat, lon=lon, start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": "moneymmax-solar/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    here = pathlib.Path(__file__).resolve().parent.parent
    ap.add_argument("--out", default=str(here / "site" / "data" / "solar.json"))
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()

    out = {"year": args.year, "source": "NASA POWER (SYN1DEG), ALLSKY_SFC_SW_DWN",
           "unit": "kWh/m2/day", "cities": {}}

    ok = fail = 0
    for slug, (lat, lon, state, country) in CITIES.items():
        try:
            data = fetch(lat, lon, args.year)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  FAIL {slug}: {exc}", file=sys.stderr)
            fail += 1
            continue
        param = data.get("properties", {}).get("parameter", {})
        series = param.get("ALLSKY_SFC_SW_DWN", {})
        days = {k: v for k, v in series.items() if v is not None and v > -9000}
        if len(days) < 300:
            print(f"  FAIL {slug}: only {len(days)} days of data", file=sys.stderr)
            fail += 1
            continue

        monthly: dict[str, float] = {}
        for d, v in days.items():
            m = d[:6]  # e.g. "202401"
            monthly.setdefault(m, []).append(v)  # type: ignore[arg-type]
        monthly_avg = {m: round(sum(vs) / len(vs), 3) for m, vs in sorted(monthly.items())}

        annual = round(sum(days.values()), 2)
        # Peak-sun-hours equivalent: annual irradiation / 365, i.e. average
        # equivalent full-sun hours per day at 1000 W/m2.
        psh = round(annual / 365.0, 2)

        # The monthly keys are YYYYMM; the page code indexes them by the
        # two-digit month. Keep both aligned: emit the two-digit key.
        by_month = {m[-2:]: v for m, v in monthly_avg.items()}

        out["cities"][slug] = {
            "name": slug.replace("-", " ").title(),
            "lat": lat, "lon": lon, "state": state, "country": country,
            "annual_kwh_m2": annual,
            "peak_sun_hours": psh,
            "monthly": by_month,
            "months": ["01", "02", "03", "04", "05", "06",
                       "07", "08", "09", "10", "11", "12"],
        }
        ok += 1
        print(f"  ok  {slug:16s} annual={annual:8.1f} kWh/m2  psh={psh}")
        time.sleep(0.4)

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    size = out_path.stat().st_size
    print(f"\n{ok} cities written, {fail} failed -> {out_path} ({size/1024:.1f} KB)")
    return 0 if ok >= len(CITIES) * 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
