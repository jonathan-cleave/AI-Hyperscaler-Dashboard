(function () {
  const data = window.dashboardData || {};
  const page = document.body.dataset.page;
  const colors = ["#ff7a18", "#ffb15e", "#5ee7ff", "#f4efe8", "#7de38d", "#ff6b6b"];
  const MSFT_COLOR = "#7FBA00";

  function isNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function moneyMillions(value) {
    if (!isNumber(value)) return "n/a";
    const sign = value < 0 ? "-" : "";
    const abs = Math.abs(value);
    if (abs >= 1000000) return `${sign}$${(abs / 1000000).toFixed(2)}T`;
    if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}B`;
    return `${sign}$${abs.toFixed(0)}M`;
  }

  function moneyUsd(value) {
    if (!isNumber(value)) return "n/a";
    const sign = value < 0 ? "-" : "";
    const abs = Math.abs(value);
    if (abs >= 1000000000000) return `${sign}$${(abs / 1000000000000).toFixed(2)}T`;
    if (abs >= 1000000000) return `${sign}$${(abs / 1000000000).toFixed(1)}B`;
    if (abs >= 1000000) return `${sign}$${(abs / 1000000).toFixed(1)}M`;
    return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }

  function format(value, type) {
    if (!isNumber(value)) return "n/a";
    if (type === "percent") return `${(value * 100).toFixed(1)}%`;
    if (type === "multiple") return `${value.toFixed(1)}x`;
    if (type === "money_m") return moneyMillions(value);
    if (type === "money_usd") return moneyUsd(value);
    if (type === "price") return `$${value.toFixed(2)}`;
    if (type === "rank") return `${value.toFixed(0)}`;
    return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  function normalizedTicker(label) {
    return String(label || "").trim().toUpperCase().split(":").pop();
  }

  function colorForLabel(label, fallbackColor) {
    return normalizedTicker(label) === "MSFT" ? MSFT_COLOR : fallbackColor;
  }

  function translucentColorForLabel(label, fallbackColor, alphaHex) {
    return `${colorForLabel(label, fallbackColor)}${alphaHex}`;
  }

  function fallback(canvas, message) {
    if (!canvas || !canvas.parentElement) return;
    const div = document.createElement("div");
    div.className = "chart-fallback";
    div.textContent = message || "Chart library unavailable.";
    canvas.replaceWith(div);
  }

  function commonOptions(formatType) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#d9d1c9",
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
            generateLabels: function (chart) {
              const labels = Chart.defaults.plugins.legend.labels.generateLabels(chart);
              if (labels.length === 1) {
                return labels.map((label) => ({
                  ...label,
                  fillStyle: "rgba(0,0,0,0)",
                  strokeStyle: "rgba(0,0,0,0)",
                  lineWidth: 0,
                  pointStyle: false
                }));
              }
              return labels;
            }
          }
        },
        tooltip: {
          backgroundColor: "rgba(8, 8, 9, 0.94)",
          borderColor: "rgba(255, 122, 24, 0.45)",
          borderWidth: 1,
          titleColor: "#fff4e7",
          bodyColor: "#e4ddd6",
          callbacks: {
            label: function (context) {
              return `${context.dataset.label}: ${format(context.parsed.y, formatType)}`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: "#a7a19a", maxRotation: 0 },
          grid: { color: "rgba(255,255,255,0.055)" }
        },
        y: {
          ticks: {
            color: "#a7a19a",
            callback: function (value) {
              return format(Number(value), formatType);
            }
          },
          grid: { color: "rgba(255,255,255,0.07)" }
        }
      }
    };
  }

  function renderLineChart(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    new Chart(canvas, {
      type: "line",
      data: {
        labels: chart.labels || [],
        datasets: (chart.series || []).map((series, index) => {
          const seriesColor = colorForLabel(series.display_ticker || series.ticker, colors[index % colors.length]);
          return {
            label: series.display_ticker,
            data: series.values,
            borderColor: seriesColor,
            backgroundColor: seriesColor,
            pointRadius: 2.8,
            pointHoverRadius: 5,
            tension: 0.32,
            borderWidth: 2.4,
            spanGaps: true
          };
        })
      },
      options: commonOptions(chart.format)
    });
  }

  function renderBarChart(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: chart.labels || [],
        datasets: [{
          label: chart.metric || chart.title,
          data: chart.values || [],
          backgroundColor: (chart.values || []).map((_, index) => translucentColorForLabel((chart.labels || [])[index], colors[index % colors.length], "cc")),
          borderColor: (chart.values || []).map((_, index) => colorForLabel((chart.labels || [])[index], colors[index % colors.length])),
          borderWidth: 1.4,
          borderRadius: 6
        }]
      },
      options: commonOptions(chart.format)
    });
  }

  function renderGroupedBar(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: chart.labels || [],
        datasets: (chart.datasets || []).map((dataset, index) => ({
          label: dataset.label,
          data: dataset.values,
          backgroundColor: (dataset.values || []).map((_, labelIndex) => translucentColorForLabel((chart.labels || [])[labelIndex], colors[index % colors.length], "c7")),
          borderColor: (dataset.values || []).map((_, labelIndex) => colorForLabel((chart.labels || [])[labelIndex], colors[index % colors.length])),
          borderWidth: 1.2,
          borderRadius: 5
        }))
      },
      options: commonOptions(chart.format)
    });
  }

  let compsDistanceChart = null;

  function renderAllCharts() {
    (data.charts || []).forEach(renderLineChart);
    (data.line_charts || []).forEach(renderLineChart);
    (data.bar_charts || []).forEach(renderBarChart);
    (data.multiple_charts || []).forEach(renderBarChart);
    if (data.bridge_chart) renderGroupedBar(data.bridge_chart);
    if (data.rank_chart) renderGroupedBar(data.rank_chart);
    renderMsftDcf();
  }

  function renderMsftDcf() {
    const canvas = document.getElementById("msft-dcf-chart");
    if (!canvas || !data.msft_valuation || !data.msft_valuation.dcf) return;
    const dcf = data.msft_valuation.dcf;
    if (!window.Chart) return fallback(canvas);
    const rows = {};
    (dcf.rows || []).forEach((row) => { rows[row.label] = row.values; });
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: dcf.headers || [],
        datasets: [
          {
            label: "FCFF",
            data: rows.FCFF || [],
            backgroundColor: "rgba(255,122,24,0.72)",
            borderColor: "#ff7a18",
            borderWidth: 1.4,
            borderRadius: 5
          },
          {
            label: "PV",
            data: rows.PV || [],
            backgroundColor: "rgba(94,231,255,0.42)",
            borderColor: "#5ee7ff",
            borderWidth: 1.4,
            borderRadius: 5
          }
        ]
      },
      options: commonOptions("money_m")
    });
  }

  const valuationControls = {
    revenue_growth: {
      slider: "revenueGrowthSlider",
      input: "revenueGrowthInput",
      scale: 100,
      outputType: "percent"
    },
    ebitda_margin: {
      slider: "ebitdaMarginSlider",
      input: "ebitdaMarginInput",
      scale: 100,
      outputType: "percent"
    },
    exit_multiple: {
      slider: "exitMultipleSlider",
      input: "exitMultipleInput",
      scale: 1,
      outputType: "multiple"
    },
    net_debt: {
      slider: "netDebtSlider",
      input: "netDebtInput",
      scale: 1,
      outputType: "money_m"
    },
    shares: {
      slider: "sharesSlider",
      input: "sharesInput",
      scale: 1,
      outputType: "number"
    }
  };

  let valuationTimer = null;

  function controlValue(name) {
    const control = valuationControls[name];
    const input = document.getElementById(control.input);
    if (!input) return null;
    const raw = Number(input.value);
    if (!Number.isFinite(raw)) return null;
    return raw / control.scale;
  }

  function setControl(name, value, range) {
    const control = valuationControls[name];
    const slider = document.getElementById(control.slider);
    const input = document.getElementById(control.input);
    if (!slider || !input) return;
    const scale = control.scale;
    const scaledValue = value * scale;
    const scaledRange = {
      min: range.min * scale,
      max: range.max * scale,
      step: range.step * scale
    };
    [slider, input].forEach((element) => {
      element.min = scaledRange.min;
      element.max = scaledRange.max;
      element.step = scaledRange.step;
      element.value = scaledValue.toFixed(control.outputType === "money_m" ? 0 : 2);
    });
  }

  function syncControl(name, source) {
    const control = valuationControls[name];
    const slider = document.getElementById(control.slider);
    const input = document.getElementById(control.input);
    if (!slider || !input) return;
    const value = source === "slider" ? slider.value : input.value;
    slider.value = value;
    input.value = value;
    scheduleValuation();
  }

  function loadCompanyModel(ticker) {
    const model = data.models && data.models[ticker];
    if (!model) return;
    Object.keys(valuationControls).forEach((name) => {
      setControl(name, model.inputs[name], model.ranges[name]);
    });
    updateAssumptions(model);
    scheduleValuation(0);
  }

  function updateAssumptions(model) {
    const container = document.getElementById("assumptionCards");
    if (!container) return;
    const assumptions = model.assumptions || {};
    const items = [
      ["WACC", assumptions.wacc, "percent"],
      ["Cost of debt", assumptions.cost_of_debt, "percent"],
      ["Cost of equity", assumptions.cost_of_equity, "percent"],
      ["Tax rate", assumptions.tax_rate, "percent"],
      ["Beta", assumptions.beta, "number"],
      ["Market equity", assumptions.market_equity, "money_m"]
    ];
    container.innerHTML = items.map(([label, value, type]) => (
      `<div class="assumption-pill"><span>${label}</span><strong>${format(value, type)}</strong></div>`
    )).join("");
  }

  function scheduleValuation(delay) {
    window.clearTimeout(valuationTimer);
    valuationTimer = window.setTimeout(updateValuation, delay === undefined ? 90 : delay);
  }

  function updateValuation() {
    const select = document.getElementById("valuationCompany");
    if (!select) return;
    const payload = {
      ticker: select.value,
      revenue_growth: controlValue("revenue_growth"),
      ebitda_margin: controlValue("ebitda_margin"),
      exit_multiple: controlValue("exit_multiple"),
      net_debt: controlValue("net_debt"),
      shares: controlValue("shares")
    };
    fetch("/api/valuation/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then((response) => response.json())
      .then((result) => {
        if (result.error) throw new Error(result.error);
        const outputs = result.outputs || {};
        setText("forecastRevenue", format(outputs.forecast_revenue, "money_m"));
        setText("forecastEbitda", format(outputs.forecast_ebitda, "money_m"));
        setText("enterpriseValue", format(outputs.enterprise_value, "money_m"));
        setText("equityValue", format(outputs.equity_value, "money_m"));
        setText("impliedPrice", format(outputs.implied_share_price, "price"));
        const upside = document.getElementById("upsideDownside");
        if (upside) {
          upside.textContent = format(outputs.upside_downside, "percent");
          upside.classList.toggle("positive", isNumber(outputs.upside_downside) && outputs.upside_downside >= 0);
          upside.classList.toggle("negative", isNumber(outputs.upside_downside) && outputs.upside_downside < 0);
        }
      })
      .catch((error) => {
        setText("impliedPrice", error.message || "n/a");
      });
  }

  function setText(id, text) {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function selectedCompareBy() {
    const selected = document.querySelector('input[name="compare_by"]:checked');
    return selected ? selected.value : "none";
  }

  function setCompsStatus(message, type) {
    const status = document.getElementById("compsStatus");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("error", type === "error");
    status.classList.toggle("loading", type === "loading");
  }

  function renderCompsNameRanking(result) {
    const ranking = document.getElementById("compsNameRanking");
    if (!ranking) return;
    const target = result.target || {};
    const matches = result.matches || [];
    ranking.innerHTML = `
      <div class="name-rank-row target">
        <span>Target</span>
        <strong>${escapeHtml(target.company_name || result.ticker)}</strong>
      </div>
      ${matches.map((match, index) => `
        <div class="name-rank-row">
          <span>${index + 1}</span>
          <strong>${escapeHtml(match.company_name)}</strong>
        </div>
      `).join("")}
    `;
  }

  function renderCompsResults(result) {
    const container = document.getElementById("compsResults");
    if (!container) return;
    const matches = result.matches || [];
    if (!matches.length) {
      container.innerHTML = `<div class="chart-fallback">No comparable companies found for this filter.</div>`;
      renderCompsDistanceChart(result);
      return;
    }
    container.innerHTML = matches.map((match, index) => `
      <article class="comp-match-card">
        <div class="match-rank">${index + 1}</div>
        <div class="match-body">
          <div class="card-topline">
            <span>${escapeHtml(match.ticker)}</span>
            <small>Distance ${format(match.distance, "number")}</small>
          </div>
          <h3>${escapeHtml(match.company_name)}</h3>
          <p>${escapeHtml(match.industry_group || "n/a")} - ${escapeHtml(match.primary_sector || "n/a")}</p>
          <div class="metric-grid compact">
            <div><span>SIC</span><strong>${escapeHtml(match.sic_code || "n/a")}</strong></div>
            <div><span>Country</span><strong>${escapeHtml(match.country || "n/a")}</strong></div>
            <div><span>Market cap</span><strong>${format(match.market_cap, "money_usd")}</strong></div>
            <div><span>EV / EBITDA</span><strong>${format(match.ev_ebitda, "multiple")}</strong></div>
            <div><span>Price / sales</span><strong>${format(match.ps, "multiple")}</strong></div>
            <div><span>Net margin</span><strong>${format(match.net_margin, "percent")}</strong></div>
          </div>
        </div>
      </article>
    `).join("");
    renderCompsDistanceChart(result);
  }

  function renderCompsDistanceChart(result) {
    const canvas = document.getElementById("comps-distance-chart");
    if (!canvas || !window.Chart) return;
    const matches = result.matches || [];
    if (compsDistanceChart) compsDistanceChart.destroy();
    compsDistanceChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: matches.map((match) => match.ticker),
        datasets: [{
          label: result.distance_column || "Distance",
          data: matches.map((match) => match.distance),
          backgroundColor: matches.map((match, index) => translucentColorForLabel(match.ticker, colors[index % colors.length], "cc")),
          borderColor: matches.map((match, index) => colorForLabel(match.ticker, colors[index % colors.length])),
          borderWidth: 1.4,
          borderRadius: 6
        }]
      },
      options: commonOptions("number")
    });
  }

  function runComparableSearch() {
    const input = document.getElementById("compsTicker");
    if (!input) return;
    const ticker = input.value.trim().toUpperCase();
    const compareBy = selectedCompareBy();
    if (!ticker) {
      setCompsStatus("Enter a ticker first.", "error");
      return;
    }
    input.value = ticker;
    setCompsStatus("Running distance search...", "loading");
    fetch(`/api/comparables?ticker=${encodeURIComponent(ticker)}&compare_by=${encodeURIComponent(compareBy)}`)
      .then((response) => response.json().then((body) => ({ ok: response.ok, body })))
      .then(({ ok, body }) => {
        if (!ok || body.error) throw new Error(body.error || "Comparable-company search failed.");
        renderCompsNameRanking(body);
        renderCompsResults(body);
        setCompsStatus(
          `${body.matches.length} closest matches found from ${body.universe_count.toLocaleString()} filtered firms.`,
          "ok"
        );
      })
      .catch((error) => {
        setCompsStatus(error.message, "error");
      });
  }

  function initComparables() {
    if (page !== "comparables") return;
    const form = document.getElementById("compsForm");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      runComparableSearch();
    });
    document.querySelectorAll('input[name="compare_by"]').forEach((radio) => {
      radio.addEventListener("change", runComparableSearch);
    });
    runComparableSearch();
  }

  function initValuation() {
    if (page !== "valuation" || !data.models) return;
    const select = document.getElementById("valuationCompany");
    if (!select) return;
    select.addEventListener("change", () => loadCompanyModel(select.value));
    Object.keys(valuationControls).forEach((name) => {
      const control = valuationControls[name];
      const slider = document.getElementById(control.slider);
      const input = document.getElementById(control.input);
      if (slider) slider.addEventListener("input", () => syncControl(name, "slider"));
      if (input) input.addEventListener("input", () => syncControl(name, "input"));
    });
    loadCompanyModel(select.value);
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderAllCharts();
    initValuation();
    initComparables();
  });
})();
