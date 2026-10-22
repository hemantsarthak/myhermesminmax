#!/usr/bin/env python3
"""Generate the static solar calculator site from site/data/solar.json.

Produces:
  index.html                    the calculator
  peak-sun-hours/index.html     cross-city table + PSH calculator
  solar/<city>/index.html       one ranking page per city (real data on page)
  about/index.html, privacy/index.html, contact/index.html
  assets/style.css, assets/app.js, assets/data.js
  sitemap.xml, robots.txt

No framework, no build-time dependency beyond the stdlib.

Usage:
    python3 scripts/build_site.py
    python3 scripts/build_site.py --data site/data/solar.json --out site
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import shutil
import sys

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# NREL PVWatts default loss stack, as documented by the incumbent that is
# most explicit about it (voltcalcs.com, opened 2026-10-22):
#   0.86 system losses, 0.96 inverter efficiency, cell-temperature factor.
SYSTEM_EFFICIENCY = 0.86 * 0.96


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def fmt(n: float, dp: int = 0) -> str:
    return f"{n:,.{dp}f}"


class Site:
    def __init__(self, data_path: pathlib.Path, out: pathlib.Path):
        self.out = out
        self.raw = json.loads(data_path.read_text(encoding="utf-8"))
        self.cities = self.raw["cities"]
        self.year = self.raw["year"]
        self.slug_order = list(self.cities.keys())

    # ---------- helpers ----------
    def city_name(self, slug: str) -> str:
        return self.cities[slug]["name"]

    def write(self, rel: str, content: str) -> None:
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def head(self, title: str, desc: str, canonical: str, extra_head: str = "") -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<meta name="theme-color" content="#0b3d5c">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>&#9728;</text></svg>">
<link rel="stylesheet" href="/assets/style.css">
{extra_head}
</head>"""

    def nav(self, active: str = "") -> str:
        return """<header class="site-head">
  <div class="wrap head-inner">
    <a class="brand" href="/">
      <span class="brand-mark">&#9728;</span>
      <span class="brand-text">Solar<span class="brand-thin">Calc</span></span>
    </a>
    <nav class="site-nav">
      <a href="/" class="{ 'active' if active=='home' else '' }">Calculator</a>
      <a href="/peak-sun-hours/" class="{ 'active' if active=='psh' else '' }">Peak sun hours</a>
      <a href="/about/" class="{ 'active' if active=='about' else '' }">About</a>
    </nav>
  </div>
</header>"""

    def foot(self) -> str:
        return """<footer class="site-foot">
  <div class="wrap foot-grid">
    <div>
      <p class="foot-brand">SolarCalc</p>
      <p>Solar irradiance and panel output calculations for %d US cities, using
         NASA POWER satellite reanalysis data (%d).</p>
    </div>
    <div>
      <p class="foot-h">Tools</p>
      <p><a href="/">Solar panel calculator</a></p>
      <p><a href="/peak-sun-hours/">Peak sun hours by city</a></p>
    </div>
    <div>
      <p class="foot-h">Company</p>
      <p><a href="/about/">About the data</a></p>
      <p><a href="/contact/">Contact</a></p>
      <p><a href="/privacy/">Privacy</a></p>
    </div>
  </div>
  <div class="wrap foot-note">
    <p>Estimates only. Always confirm a system design with a licensed
       installer before purchasing equipment.</p>
  </div>
</footer>"""

    # ---------- pages ----------
    def build_index(self) -> None:
        options = "\n".join(
            f'      <option value="{esc(s)}">{esc(self.city_name(s))}, {esc(self.cities[s]["state"])}</option>'
            for s in self.slug_order
        )
        self.write("index.html", f"""{self.head(
            "Free Solar Panel Calculator 2026 — How Many Panels Do You Need?",
            "Free solar panel calculator for 35 US cities. Uses real NASA POWER satellite irradiance data per city, not a flat estimate. See panel count, annual output and monthly production.",
            "https://solar.tekify.xyz/")}
{self.nav('home')}
<main class="wrap">
  <section class="hero">
    <h1>Solar Panel Calculator with <em>real</em> city data</h1>
    <p class="lede">Every generic solar calculator assumes the same sun hours
      for the whole country. This one uses satellite-reanalysis irradiance for
      your actual city &mdash; from {fmt(min(c["peak_sun_hours"] for c in self.cities.values()), 2)} peak sun hours in Seattle to
      {fmt(max(c["peak_sun_hours"] for c in self.cities.values()), 2)} in Phoenix.</p>
  </section>

  <section class="panel" id="calc">
    <form id="solar-form" autocomplete="off">
      <div class="grid">
        <label class="field">
          <span class="field-label">Your city</span>
          <select id="city" name="city">
{options}
          </select>
        </label>

        <label class="field">
          <span class="field-label">Monthly electricity use (kWh)</span>
          <input type="number" id="usage" name="usage" value="900" min="1" max="100000" step="1" inputmode="numeric">
          <span class="field-hint">From your electricity bill. Check the 12-month total and divide by 12.</span>
        </label>

        <label class="field">
          <span class="field-label">Panel wattage</span>
          <select id="wattage" name="wattage">
            <option value="400" selected>400 W</option>
            <option value="450">450 W</option>
            <option value="500">500 W</option>
            <option value="550">550 W</option>
            <option value="600">600 W</option>
            <option value="700">700 W</option>
          </select>
        </label>

        <label class="field">
          <span class="field-label">Roof direction</span>
          <select id="tilt" name="tilt">
            <option value="1.0" selected>South-facing (optimal)</option>
            <option value="0.92">South-east / south-west</option>
            <option value="0.85">East or west facing</option>
            <option value="0.7">North-facing</option>
            <option value="0.75">Flat roof</option>
          </select>
        </label>

        <label class="field">
          <span class="field-label">System type</span>
          <select id="system" name="system">
            <option value="ongrid" selected>On-grid (no battery)</option>
            <option value="hybrid">Hybrid (grid + battery backup)</option>
            <option value="offgrid">Off-grid (battery only)</option>
          </select>
        </label>

        <label class="field">
          <span class="field-label">Monthly electricity rate ($/kWh)</span>
          <input type="number" id="rate" name="rate" value="0.17" min="0.01" max="2" step="0.01" inputmode="decimal">
        </label>
      </div>
      <button type="submit" class="btn">Calculate my system</button>
    </form>
  </section>

  <section id="results" class="results" hidden>
    <h2 class="results-title">Your system in <span id="r-city"></span></h2>
    <div class="stat-row">
      <div class="stat"><span class="stat-num" id="r-panels">&mdash;</span><span class="stat-lab">panels</span></div>
      <div class="stat"><span class="stat-num" id="r-kw">&mdash;</span><span class="stat-lab">system size (kWp)</span></div>
      <div class="stat"><span class="stat-num" id="r-psh">&mdash;</span><span class="stat-lab">peak sun hours/day</span></div>
      <div class="stat"><span class="stat-num" id="r-annual">&mdash;</span><span class="stat-lab">annual output (kWh)</span></div>
      <div class="stat"><span class="stat-num" id="r-offset">&mdash;</span><span class="stat-lab">bill offset</span></div>
      <div class="stat"><span class="stat-num" id="r-roof">&mdash;</span><span class="stat-lab">roof area needed</span></div>
    </div>

    <div class="split">
      <div class="card">
        <h3>Month-by-month production</h3>
        <p class="muted">Calculated from real satellite irradiance for this city,
           so summer and winter differ the way they actually do on site.</p>
        <table class="month-table" id="r-months"></table>
      </div>
      <div class="card">
        <h3>How this was calculated</h3>
        <ul class="bullets">
          <li>Daily load = monthly kWh &divide; 30.</li>
          <li>Array kW = daily load &divide; (peak sun hours &times; {SYSTEM_EFFICIENCY:.3f} efficiency &times; roof factor).</li>
          <li>Panels = array kW &divide; panel wattage, rounded up.</li>
          <li>Annual output uses each month's real irradiance value.</li>
          <li>System efficiency follows the NREL PVWatts defaults:
              14% system losses and 96% inverter efficiency.</li>
        </ul>
        <p class="muted" id="r-note"></p>
        <p><a class="textlink" id="r-citylink" href="#">See this city's full solar data &rarr;</a></p>
      </div>
    </div>
  </section>

  <section class="panel alt">
    <h2>Why city-level data changes the answer</h2>
    <p>Two cities 300 miles apart can differ by more than 40% in annual solar
       energy. A calculator that assumes "5 peak sun hours" everywhere
       oversells panels in the north and undersells them in the desert.
       These are the real measured values for each city we cover.</p>
    <table class="data-table" id="psh-table">
      <thead><tr><th>City</th><th>State</th><th>Peak sun hours/day</th><th>Annual irradiance (kWh/m&sup2;)</th></tr></thead>
      <tbody></tbody>
    </table>
  </section>

  <section class="panel">
    <h2>Which cities do we cover?</h2>
    <ul class="city-links" id="city-links"></ul>
  </section>
</main>
{self.foot()}
<script src="/assets/data.js"></script>
<script src="/assets/app.js"></script>
</body>
</html>""")

    def build_psh(self) -> None:
        rows = []
        for s in self.slug_order:
            c = self.cities[s]
            rows.append(
                f'      <tr><td><a href="/solar/{esc(s)}/">{esc(c["name"])}</a></td>'
                f'<td>{esc(c["state"])}</td>'
                f'<td>{fmt(c["peak_sun_hours"], 2)}</td>'
                f'<td>{fmt(c["annual_kwh_m2"], 0)}</td></tr>')
        self.write("peak-sun-hours/index.html", f"""{self.head(
            "Peak Sun Hours by City 2026 — Solar Hours Calculator",
            "Peak sun hours for 35 US cities from NASA POWER satellite data, with a free peak sun hours calculator by city, state and annual solar irradiance.",
            "https://solar.tekify.xyz/peak-sun-hours/")}
{self.nav('psh')}
<main class="wrap">
  <section class="hero">
    <h1>Peak sun hours by city</h1>
    <p class="lede">Peak sun hours (PSH) is the number of full-strength sunlight
       hours a square metre collects in a day. It is the single input that
       decides how many panels you need. These are measured values, from
       NASA POWER daily reanalysis for {self.year}, for {len(self.cities)} cities.</p>
  </section>

  <section class="panel">
    <h2>Peak sun hours table</h2>
    <table class="data-table">
      <thead><tr><th>City</th><th>State</th><th>Peak sun hours/day</th><th>Annual irradiance (kWh/m&sup2;)</th><th>City page</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </section>

  <section class="panel alt">
    <h2>What peak sun hours means</h2>
    <p>PSH converts a location's sunlight into the equivalent number of hours
       at 1,000 W/m&sup2;. A city at 4.0 PSH collects about 20% less energy per
       panel than a city at 5.0 PSH over a year. Multiply PSH by panel wattage
       to get the panel's real daily output before losses.</p>
    <p>We report the annual figure as
       <strong>annual irradiance &divide; 365</strong>, which is the standard
       definition and is the number used in the
       <a href="/">solar panel calculator</a>.</p>
  </section>
</main>
{self.foot()}
<script src="/assets/data.js"></script>
<script src="/assets/app.js"></script>
</body>
</html>""")

    def build_city(self, slug: str) -> None:
        c = self.cities[slug]
        name = c["name"]
        state = c["state"]
        psh = c["peak_sun_hours"]
        annual = c["annual_kwh_m2"]
        month_rows = []
        for i, m in enumerate(c["months"]):
            v = c["monthly"].get(m, 0)
            pct = (v / 12.0) if v else 0
            month_rows.append(
                f'      <tr><td>{MONTHS[i]}</td><td>{fmt(v, 2)}</td>'
                f'<td>{fmt(pct, 1)}</td></tr>')

        # Annual production of a single 400 W panel at this city, at 86%*96%
        one_panel = 0.4 * psh * SYSTEM_EFFICIENCY
        # Panels needed to cover 900 kWh/month (a typical US household) here.
        daily = 900 / 30.0
        arr_kw = daily / (psh * SYSTEM_EFFICIENCY)
        panels = -(-arr_kw // 0.4)

        self.write(f"solar/{slug}/index.html", f"""{self.head(
            f"Solar Panel Calculator in {name}, {state} — {fmt(psh, 2)} Peak Sun Hours",
            f"How many solar panels does {name}, {state} need? {name} gets {fmt(psh, 2)} peak sun hours a day and {fmt(annual, 0)} kWh/m² of annual solar irradiance, measured from NASA POWER satellite data.",
            f"https://solar.tekify.xyz/solar/{slug}/")}
{self.nav()}
<main class="wrap">
  <section class="hero">
    <p class="crumb"><a href="/">Calculator</a> &rsaquo; {esc(name)}, {esc(state)}</p>
    <h1>Solar panels in {esc(name)}, {esc(state)}</h1>
    <p class="lede">{esc(name)} receives <strong>{fmt(psh, 2)} peak sun hours a day</strong>
       and <strong>{fmt(annual, 0)} kWh/m&sup2;</strong> of solar energy a year.
       That is measured satellite data for {name}'s coordinates, not a national
       average &mdash; and it changes the panel count.</p>
  </section>

  <section class="panel">
    <h2>{esc(name)} solar data</h2>
    <div class="stat-row">
      <div class="stat"><span class="stat-num">{fmt(psh, 2)}</span><span class="stat-lab">peak sun hours/day</span></div>
      <div class="stat"><span class="stat-num">{fmt(annual, 0)}</span><span class="stat-lab">annual irradiance (kWh/m&sup2;)</span></div>
      <div class="stat"><span class="stat-num">{fmt(one_panel, 2)}</span><span class="stat-lab">kWh/day from one 400 W panel</span></div>
      <div class="stat"><span class="stat-num">{fmt(0.4 * psh * 365 * SYSTEM_EFFICIENCY, 0)}</span><span class="stat-lab">kWh/year from one 400 W panel</span></div>
    </div>

    <h3>Monthly solar irradiance in {esc(name)}</h3>
    <table class="data-table">
      <thead><tr><th>Month</th><th>Peak sun hours/day</th><th>Share of year</th></tr></thead>
      <tbody>
{chr(10).join(month_rows)}
      </tbody>
    </table>
    <p class="muted">Source: NASA POWER daily point API,
       parameter ALLSKY_SFC_SW_DWN (global horizontal irradiance), year {self.year}.
       Coordinates {c["lat"]}, {c["lon"]}.</p>
  </section>

  <section class="panel alt">
    <h2>How many solar panels does {esc(name)} need?</h2>
    <p>For a typical US household using 900 kWh a month, {esc(name)} needs about
       <strong>{int(panels)} panels of 400 W</strong> ({fmt(arr_kw, 2)} kWp),
       with a south-facing roof. That is
       {"more" if psh < 4.3 else "fewer"} panels than the same household would
       need in a city with 4.5 peak sun hours.</p>
    <p><a class="btn inline" href="/?city={esc(slug)}">Calculate for your own usage &rarr;</a></p>
  </section>

  <section class="panel">
    <h2>Other cities near {esc(state)}</h2>
    <ul class="city-links">
      <li><a href="/">Solar panel calculator (all cities)</a></li>
      <li><a href="/peak-sun-hours/">Peak sun hours by city</a></li>
    </ul>
  </section>
</main>
{self.foot()}
<script src="/assets/data.js"></script>
<script src="/assets/app.js"></script>
</body>
</html>""")

    def build_static_pages(self) -> None:
        self.write("about/index.html", f"""{self.head(
            "About the Data — SolarCalc",
            f"How SolarCalc sources solar irradiance data for {len(self.cities)} US cities using the NASA POWER API, and how the panel calculations work.",
            "https://solar.tekify.xyz/about/")}
{self.nav('about')}
<main class="wrap">
  <section class="hero"><h1>About the data</h1></section>
  <section class="panel">
    <h2>Where the numbers come from</h2>
    <p>Every irradiance figure on this site comes from the
       <strong>NASA POWER</strong> project &mdash; a reanalysis of satellite and
       meteorological observations, served through a public API that needs no
       key. We request the daily global horizontal irradiance
       (<code>ALLSKY_SFC_SW_DWN</code>) for each city's exact coordinates over
       the full calendar year {self.year}.</p>
    <p>Peak sun hours are reported as annual irradiance divided by 365, which
       is the standard definition and matches how PVWatts-style tools express
       it.</p>
    <p>The full dataset is embedded in the page as JSON, so every calculation
       you run happens in your browser. We do not send your usage figures to a
       server.</p>

    <h2>How the panel calculation works</h2>
    <ul class="bullets">
      <li>Daily load = monthly kWh &divide; 30.</li>
      <li>Array kW = daily load &divide; (peak sun hours &times; system efficiency &times; roof factor).</li>
      <li>System efficiency = 0.86 &times; 0.96, the NREL PVWatts default for system losses and inverter efficiency.</li>
      <li>Panels = array kW &divide; panel wattage, rounded up.</li>
      <li>Annual output is summed month by month using each month's measured irradiance.</li>
    </ul>

    <h2>What this tool is not</h2>
    <p>It is a sizing estimate, not a design. Shading from trees and buildings,
       roof age, panel brand, snow and soiling all move the real number. Always
       have a licensed installer check the design and confirm the panel and
       inverter datasheets before you buy anything.</p>

    <h2>Accuracy check</h2>
    <p>Spot-checking the dataset against known values: Phoenix averages
       {fmt(self.cities["phoenix"]["peak_sun_hours"], 2)} peak sun hours and
       Seattle {fmt(self.cities["seattle"]["peak_sun_hours"], 2)}. That ordering,
       and the ~40% spread between them, matches the real-world gap between
       the Sonoran Desert and the Pacific Northwest.</p>
  </section>
</main>
{self.foot()}
</body>
</html>""")

        self.write("privacy/index.html", f"""{self.head(
            "Privacy — SolarCalc",
            "SolarCalc privacy policy. No cookies, no analytics trackers, no data collection. All calculations run in your browser.",
            "https://solar.tekify.xyz/privacy/")}
{self.nav()}
<main class="wrap">
  <section class="hero"><h1>Privacy</h1></section>
  <section class="panel">
    <p><strong>We do not collect personal data.</strong> This site sets no
       cookies, runs no analytics, has no accounts, and no forms that send
       anything anywhere.</p>
    <p>The electricity usage, panel wattage and roof direction you enter are
       used only by JavaScript running in your own browser. They are never
       transmitted to us and never stored.</p>
    <p>Advertising is served by third-party networks. Those networks may set
       their own cookies or use similar technologies to serve and measure ads,
       and they have their own privacy policies. We do not receive the details
       of those uses beyond what a normal ad impression exposes.</p>
  </section>
</main>
{self.foot()}
</body>
</html>""")

        self.write("contact/index.html", f"""{self.head(
            "Contact — SolarCalc",
            "Contact SolarCalc. Report a data error, request a city, or get help with a calculation.",
            "https://solar.tekify.xyz/contact/")}
{self.nav()}
<main class="wrap">
  <section class="hero"><h1>Contact</h1></section>
  <section class="panel">
    <p>Spotted a wrong number, or need a city that isn't here?</p>
    <p>Email <strong>hello@solar.tekify.xyz</strong> with the city name and
       what you expected. Data corrections get applied to the dataset and
       redeployed, so every page for that city updates.</p>
    <p>For solar installation, financing and equipment questions, talk to a
       licensed installer in your area &mdash; they need to see your roof.</p>
  </section>
</main>
{self.foot()}
</body>
</html>""")

    def build_assets(self) -> None:
        # Embed the dataset as a JS global so pages load with one request.
        data = {"year": self.year, "source": self.raw["source"], "cities": self.cities}
        self.write("assets/data.js",
                   "/* Solar irradiance dataset. Generated by scripts/build_site.py.\n"
                   "   Source: NASA POWER ALLSKY_SFC_SW_DWN. */\n"
                   "window.SOLAR_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")

        shutil.copyfile(pathlib.Path(__file__).resolve().parent / "assets" / "style.css",
                        self.out / "assets" / "style.css")
        shutil.copyfile(pathlib.Path(__file__).resolve().parent / "assets" / "app.js",
                        self.out / "assets" / "app.js")

    def build_sitemap(self) -> None:
        base = "https://solar.tekify.xyz"
        urls = [("/index.html", "1.0"), ("/peak-sun-hours/index.html", "0.9"),
                ("/about/index.html", "0.3"), ("/privacy/index.html", "0.2"),
                ("/contact/index.html", "0.3")]
        for s in self.slug_order:
            urls.append((f"/solar/{s}/index.html", "0.8"))
        entries = []
        for path, prio in urls:
            url = base + path.replace("index.html", "")
            entries.append(f"""  <url>
    <loc>{url}</loc>
    <changefreq>monthly</changefreq>
    <priority>{prio}</priority>
  </url>""")
        self.write("sitemap.xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                   + "\n".join(entries) + "\n</urlset>\n")

        self.write("robots.txt",
                   "User-agent: *\n"
                   "Allow: /\n\n"
                   "Sitemap: https://solar.tekify.xyz/sitemap.xml\n")

    def build(self) -> None:
        self.build_assets()
        self.build_index()
        self.build_psh()
        for s in self.slug_order:
            self.build_city(s)
        self.build_static_pages()
        self.build_sitemap()
        htmls = len(list(self.out.rglob("*.html")))
        total = len([p for p in self.out.rglob("*") if p.is_file()])
        print(f"built {htmls} html pages, {total} files total -> {self.out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    here = pathlib.Path(__file__).resolve().parent.parent
    ap.add_argument("--data", default=str(here / "site" / "data" / "solar.json"))
    ap.add_argument("--out", default=str(here / "site"))
    args = ap.parse_args()

    data_path = pathlib.Path(args.data)
    if not data_path.exists():
        print(f"ERROR: {data_path} missing. Run scripts/build_solar_data.py first.",
              file=sys.stderr)
        return 2
    Site(data_path, pathlib.Path(args.out)).build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
