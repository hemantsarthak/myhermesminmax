# NICHE-SELECTION — evidence for the first site

Agent: tom. Date: 2026-10-22. All sources opened on 2026-10-22 unless noted.

## DECISION

**Site #1: `solarcalc` — per-city solar irradiance & panel output calculator, on
real NASA POWER satellite data, one page per city.**

Domain: `solar.tekify.xyz` (or `solarcalc.tekify.xyz`).

---

## Why this niche wins

### 1. The gap is structural, not a ranking trick

The query cluster is "solar panel output calculator" + a city modifier. Every
incumbent serves the city as a **dropdown option inside one page**. Nobody has
a **page per city** with real data on it.

| Incumbent | Per-city pages? | Data used | Verified how |
|---|---|---|---|
| `docrack.me/en/solar-panel-calculator/` | **NO** — one page, 80+ cities in a dropdown | "real irradiance data for 80+ cities" (Oslo 2.8 → Riyadh 6.8 PSH) | fetched `sitemap_index.xml` → `page-sitemap.xml` → 20 `<loc>` entries, **zero** city URLs |
| `hvacbase.org/solar-panel-calculator` | **NO** — one page | "sun hours by state are **approximate**"; uses a **US-average 5 PSH** default | `sitemap.xml` → 147 URLs, exactly **1** matches solar |
| `top10k.com/tool/sun-hours-by-location` | **NO** — one page | **latitude + climate-zone estimate**, user picks a zone (Desert/Temperate/Oceanic/…) | fetched page; inputs are "Latitude" + "Climate Zone" dropdown; `sitemap.xml` → 0 `<loc>` |
| `renewablewise.com/peak-sun-hours-calculator` | **NO** — one page (+ "by state"/"by zip" pages) | NREL historical data, but resolves a **user-typed location at runtime** | fetched page; `post-sitemap.xml` shows no city pages |
| `joteo.net/ecology-calculators/solar-panel-output-calculator-by-location/` | **NO** — one page | "**estimates** peak sun hours from latitude, seasonal variation, tilt" | fetched page |

**The wedge:** a static site with a real page at `/solar/phoenix/`,
`/solar/seattle/`, `/solar/miami/` etc., where the page's numbers come from
actual satellite reanalysis for that city's coordinates. Google can index
35+ pages; a dropdown cannot be indexed per-city.

### 2. The dataset is a genuine moat I can hold

NASA POWER daily point API — **free, no API key**, verified working:

```
GET https://power.larc.nasa.gov/api/temporal/daily/point
    ?parameters=ALLSKY_SFC_SW_DWN&community=RE
    &longitude=-122.4&latitude=37.77&start=20240101&end=20241231&format=JSON
→ HTTP 200, 366 days, annual 1783.4 kWh/m², avg 4.873 kWh/m²/day
```

Built for **35 US cities** (script: `scripts/build_solar_data.py`,
output `site/data/solar.json`, 13.9 KB). Sanity check passes — the spread is
physically correct, not noise:

| City | Peak sun hours | City | Peak sun hours |
|---|---|---|---|
| Phoenix AZ | **5.84** | Chicago IL | 4.11 |
| Las Vegas NV | 5.53 | Boston MA | 3.87 |
| Los Angeles CA | 5.55 | Portland OR | 3.77 |
| Tampa FL | 5.22 | Cleveland OH | 3.76 |
| Austin TX | 4.83 | **Seattle WA** | **3.48** |

Seattle lowest and Phoenix highest is exactly the real-world ordering. A
content farm using a flat "5 PSH" assumption cannot produce this.

### 3. Demand is real and measurable

Google autocomplete (`scripts/demand.py`, a-z expansion, 2026-10-22):

| Seed | Distinct long-tail suggestions |
|---|---|
| pipe sizing calculator | 176 |
| solar panel calculator | 231 |
| medicaid eligibility calculator | 92 |
| generator size calculator | 83 |
| deck joist span calculator | 64 |

Solar is the **largest cluster measured**, and the head term is confirmed by
real SERP competition (see 1) — meaning money is behind it.

Sample long-tail queries pulled from autocomplete for this cluster:

- `solar panel output calculator`
- `solar panel output calculator kwh`
- `solar panel output calculator by location`
- `solar panel output calculator uk`
- `solar panel output calculator 12v`
- `kwh per solar panel`
- `average kwh per solar panel`
- `kilowatt hours per solar panel`

Note `by location` and `kwh per solar panel` are exactly the two queries a
per-city, real-data site is built to win, and neither has a dedicated
incumbent page.

### 4. Commercial value of the traffic

Solar is a high-LTV vertical: the visitor is researching a $10k-$30k purchase.
Affiliate programs in this niche are worth far more than ad impressions, and
the SERP already contains affiliate-driven players (`heliosketch.com` sells a
$3,000 subscription tier, `energysage.com` sells quotes, `renewablewise.com`
runs "As an Amazon Affiliate I earn from qualifying purchases"). Popunder CPM
is the fallback, not the plan.

---

## NICHES CONSIDERED AND REJECTED

| Niche | Long-tail | Why rejected |
|---|---|---|
| pipe sizing calculator | 176 | engineeringtoolbox owns it and the SERP is DIY/industrial; weaker consumer intent than solar |
| medicaid eligibility calculator | 92 | state-by-state rules are high-stakes legal/benefits data — wrong data = real harm to users; too risky to ship on a schedule |
| generator size calculator | 83 | electriciancalc.com + generatorsizecalculator.com already occupy it with clean UX; weak differentiator left |
| deck joist span calculator | 64 | decks.com (a major decking brand) owns the SERP with a brand-authority site — not beatable in 90 days |
| car accident settlement calculator | 42 | legal-advice exposure; many state rules; liability risk |
| roof replacement cost calculator | — | SERP is all national roofing brands and lead-gen sites |
| statute of limitations calculator | — | legal-advice exposure, high liability |

**Rejected on risk, not on opportunity:** anything that computes a legal
deadline or a benefits eligibility. Solar sizing has an accepted method
(NREL PVWatts loss model), real public data, and a wrong answer costs the
user money, not a legal right.

---

## BUILD SPEC — `solar.tekify.xyz`

Static, no framework. HTML + CSS + vanilla JS. All math client-side using
the embedded `solar.json`.

### Pages

- `/` — the calculator. City select (35 cities), monthly kWh input (or annual),
  panel wattage, tilt, roof direction, system type (on-grid / hybrid / off-grid).
- `/solar/<city-slug>/` — one page per city (35 pages). Each shows that city's
  real annual + monthly irradiance, its peak sun hours, panels needed, annual
  output, and a month-by-month production table. These are the ranking pages.
- `/solar/<city-slug>/how-many-solar-panels/` — optional deeper page per city
  for the "how many panels" long tail.
- `/peak-sun-hours/` — the cross-city table + calculator (head term).
- `/about/`, `/privacy/`, `/contact/`.

### Calculation model

Follow the NREL PVWatts default loss stack that the best incumbent documents
(`voltcalcs.com`, which states 0.86 system losses × 0.96 inverter efficiency ×
cell-temperature factor). Daily energy = monthly kWh / 30. Array kW =
daily kWh ÷ (PSH × efficiency). Panels = array kW ÷ panel wattage.
Annual output uses the **real monthly** irradiance for that city, not an annual
average — that is the differentiator, and it must be visible on the page.

### Technical requirements

- `scripts/build_solar_data.py` → `site/data/solar.json` (already built).
- `scripts/verify_site.py` → must print `VERIFY: clean` before every deploy.
- `scripts/deploy.sh` → Pages deploy + `solar.tekify.xyz` DNS attach + verify.
- CI on GitHub Actions so the site keeps deploying with the laptop off.
- Ad tags: Adsterra (confirmed no traffic minimum, 5-10 min approval,
  $5 Paxum min, USDC payout works in India — India is NOT on the USDC
  exclusion list). Ad tag injected by `scripts/deploy.sh` only after the
  network account exists; until then the site ships clean so approval passes.

### Success criteria for the 30/60/90-day check

- Day 30: site live on `tekify.xyz`, indexed (Search Console property owned by
  the operator), Adsterra account approved, first impressions in the network.
- Day 60: >= 25 of 35 city pages indexed, >= 100 organic visits/day.
- Day 90: >= 2,000 organic visits/day and a live $1k/month trajectory check
  against Adsterra's reported CPM for the actual traffic mix.
