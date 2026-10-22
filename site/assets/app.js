/* SolarCalc client-side logic.
   All math happens here in the browser. Nothing is sent anywhere.
   Model matches the NREL PVWatts default loss stack: 0.86 system losses
   x 0.96 inverter efficiency (documented on /about/). */

(function () {
  "use strict";

  var DATA = window.SOLAR_DATA || { cities: {}, year: "" };
  var CITIES = DATA.cities || {};
  var SYSTEM_EFFICIENCY = 0.86 * 0.96;
  var PANEL_SQ_FT = 0.0176; // ~17.6 sq ft per 400 W panel

  function $(id) { return document.getElementById(id); }
  function num(el) { return parseFloat(el.value) || 0; }

  function cityBySlug(slug) { return CITIES[slug]; }

  function cityOptions() {
    return Object.keys(CITIES).map(function (k) { return CITIES[k]; });
  }

  /* ---------- index page ---------- */
  function initCalculator() {
    var form = $("solar-form");
    if (!form) return;

    var results = $("results");
    var citySel = $("city");
    var usage = $("usage");
    var wattage = $("wattage");
    var tilt = $("tilt");
    var system = $("system");
    var rate = $("rate");

    // Deep link: /?city=phoenix
    var params = new URLSearchParams(window.location.search);
    var want = params.get("city");
    if (want && CITIES[want]) citySel.value = want;

    function calculate() {
      var slug = citySel.value;
      var c = cityBySlug(slug);
      if (!c) return;

      var monthlyKwh = num(usage);
      var w = num(wattage) || 400;
      var roofFactor = parseFloat(tilt.value) || 1;
      var kind = system.value;
      var r = num(rate) || 0.17;

      var dailyKwh = monthlyKwh / 30;
      var psh = c.peak_sun_hours;

      // Off-grid needs headroom for cloudy spells; hybrid a little less.
      var designFactor = kind === "offgrid" ? 0.75 : (kind === "hybrid" ? 0.9 : 1);
      var eff = SYSTEM_EFFICIENCY * roofFactor * designFactor;

      var arrayKw = dailyKwh / (psh * eff);
      var panels = Math.ceil(arrayKw / (w / 1000));

      // Annual production from real monthly irradiance, not the annual mean.
      var annualKwh = 0;
      var months = c.months.map(function (m) {
        var mpsh = c.monthly[m] || 0;
        var monthKwh = arrayKw * mpsh * 30.4 * SYSTEM_EFFICIENCY * roofFactor * designFactor;
        annualKwh += monthKwh;
        return { m: m, psh: mpsh, kwh: monthKwh };
      });

      var offset = monthlyKwh > 0 ? Math.min(100, (annualKwh / (monthlyKwh * 12)) * 100) : 0;
      var sqft = panels * (PANEL_SQ_FT * (w / 400));
      var bill = monthlyKwh * r;
      var savings = annualKwh * r;
      var payback = savings > 0 ? (arrayKw * 1000 * 2.5) / savings : 0;

      $("r-city").textContent = c.name + ", " + c.state;
      $("r-panels").textContent = panels;
      $("r-kw").textContent = arrayKw.toFixed(2);
      $("r-psh").textContent = psh.toFixed(2);
      $("r-annual").textContent = Math.round(annualKwh).toLocaleString();
      $("r-offset").textContent = Math.round(offset) + "%";
      $("r-roof").textContent = Math.round(sqft) + " sq ft";

      var rows = months.map(function (x) {
        var mi = parseInt(x.m, 10) - 1;
        var names = ["January","February","March","April","May","June","July",
                     "August","September","October","November","December"];
        return "<tr><td>" + names[mi] + "</td><td>" + x.psh.toFixed(2) +
               "</td><td>" + Math.round(x.kwh).toLocaleString() + "</td></tr>";
      }).join("");
      $("r-months").innerHTML =
        "<thead><tr><th>Month</th><th>Peak sun hours</th><th>Output (kWh)</th></tr></thead>" +
        "<tbody>" + rows + "</tbody>";

      var note = "Estimated annual output " + Math.round(annualKwh).toLocaleString() +
        " kWh, worth about $" + Math.round(savings).toLocaleString() +
        " a year at $" + r.toFixed(2) + "/kWh, against a bill of about $" +
        Math.round(bill).toLocaleString() + "/month.";
      if (kind === "offgrid") {
        note += " Off-grid sizing includes a 25% reserve for cloudy periods.";
      } else if (kind === "hybrid") {
        note += " Hybrid sizing includes a 10% reserve for grid backup.";
      }
      if (payback > 0) {
        note += " Simple payback at a $2.50/W installed cost: about " +
                payback.toFixed(1) + " years.";
      }
      $("r-note").textContent = note;

      var link = $("r-citylink");
      link.href = "/solar/" + slug + "/";
      link.textContent = "See " + c.name + "'s full solar data →";

      results.hidden = false;
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      calculate();
    });
    [citySel, usage, wattage, tilt, system, rate].forEach(function (el) {
      el.addEventListener("change", function () {
        if (results.hidden === false) calculate();
      });
    });

    buildPshTable();
    buildCityLinks();
  }

  function buildPshTable() {
    var tb = document.querySelector("#psh-table tbody");
    if (!tb) return;
    var list = cityOptions().sort(function (a, b) {
      return b.peak_sun_hours - a.peak_sun_hours;
    });
    tb.innerHTML = list.map(function (c) {
      return "<tr><td><a href=\"/solar/" + slugOf(c) + "/\">" + c.name + "</a></td>" +
             "<td>" + c.state + "</td>" +
             "<td>" + c.peak_sun_hours.toFixed(2) + "</td>" +
             "<td>" + Math.round(c.annual_kwh_m2).toLocaleString() + "</td></tr>";
    }).join("");
  }

  function slugOf(c) {
    return Object.keys(CITIES).filter(function (k) { return CITIES[k] === c; })[0];
  }

  function buildCityLinks() {
    var ul = $("city-links");
    if (!ul) return;
    ul.innerHTML = Object.keys(CITIES).sort().map(function (k) {
      var c = CITIES[k];
      return "<li><a href=\"/solar/" + k + "/\">" + c.name + ", " + c.state + "</a></li>";
    }).join("");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCalculator);
  } else {
    initCalculator();
  }
})();
