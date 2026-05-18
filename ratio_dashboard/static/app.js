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
    if (type === "zscore") return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
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

  function initFastNavigation() {
    document.querySelectorAll(".side-nav a").forEach((link) => {
      link.addEventListener("click", (event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (link.target === "_blank") return;
        const href = link.getAttribute("href");
        if (!href || href === window.location.pathname) return;
        document.body.classList.add("page-leaving");
      });
    });
  }

  function commonOptions(formatType, directionText, indexAxis) {
    const horizontal = indexAxis === "y";
    const valueAxis = horizontal ? "x" : "y";
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", axis: horizontal ? "y" : "x", intersect: false },
      plugins: {
        subtitle: {
          display: Boolean(directionText),
          text: directionText || "",
          color: "#9a9690",
          font: {
            size: 12,
            weight: "700"
          },
          padding: {
            top: 0,
            bottom: 4
          }
        },
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
          itemSort: function (a, b) {
            const aValue = Number(a.parsed && a.parsed[valueAxis]);
            const bValue = Number(b.parsed && b.parsed[valueAxis]);
            if (!Number.isFinite(aValue) && !Number.isFinite(bValue)) return 0;
            if (!Number.isFinite(aValue)) return 1;
            if (!Number.isFinite(bValue)) return -1;
            return bValue - aValue;
          },
          callbacks: {
            label: function (context) {
              return `${context.dataset.label}: ${format(Number(context.parsed[valueAxis]), formatType)}`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: "#a7a19a",
            stepSize: horizontal && formatType === "rank" ? 1 : undefined,
            precision: horizontal && formatType === "rank" ? 0 : undefined,
            maxRotation: 0,
            autoSkip: false,
            callback: function (value, index) {
              if (horizontal) {
                if (formatType === "rank" && !Number.isInteger(Number(value))) return "";
                return format(Number(value), formatType);
              }
              const labels = this.chart.data.labels || [];
              const label = labels[index];
              const year = Number(label);
              if (labels.length >= 8 && Number.isInteger(year) && year >= 1900 && year <= 2100) {
                return year % 2 === 0 ? label : "";
              }
              return label;
            }
          },
          grid: { color: "rgba(255,255,255,0.055)" }
        },
        y: {
          ticks: {
            color: "#a7a19a",
            stepSize: !horizontal && formatType === "rank" ? 1 : undefined,
            precision: !horizontal && formatType === "rank" ? 0 : undefined,
            callback: function (value, index) {
              if (horizontal) {
                const labels = this.chart.data.labels || [];
                return labels[index] || value;
              }
              if (formatType === "rank" && !Number.isInteger(Number(value))) return "";
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
      options: commonOptions(chart.format, chart.direction, chart.index_axis)
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
      options: commonOptions(chart.format, chart.direction, chart.index_axis)
    });
  }

  function renderGroupedBar(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    const colorByDataset = chart.color_by === "dataset";
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: chart.labels || [],
        datasets: (chart.datasets || []).map((dataset, index) => {
          const datasetColor = colors[index % colors.length];
          return {
            label: dataset.label,
            data: dataset.values,
            backgroundColor: (dataset.values || []).map((_, labelIndex) => (
              colorByDataset
                ? `${datasetColor}c7`
                : translucentColorForLabel((chart.labels || [])[labelIndex], datasetColor, "c7")
            )),
            borderColor: (dataset.values || []).map((_, labelIndex) => (
              colorByDataset
                ? datasetColor
                : colorForLabel((chart.labels || [])[labelIndex], datasetColor)
            )),
            borderWidth: 1.2,
            borderRadius: 5
          };
        })
      },
      options: commonOptions(chart.format, chart.direction, chart.index_axis)
    });
  }

  function renderRadarChart(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    const rankMin = isNumber(chart.min) ? chart.min : 1;
    const rankMax = isNumber(chart.max) ? chart.max : 4;
    new Chart(canvas, {
      type: "radar",
      data: {
        labels: chart.labels || [],
        datasets: (chart.datasets || []).map((dataset, index) => {
          const datasetColor = colorForLabel(dataset.label, colors[index % colors.length]);
          return {
            label: dataset.label,
            data: dataset.values || [],
            borderColor: datasetColor,
            backgroundColor: `${datasetColor}30`,
            pointBackgroundColor: datasetColor,
            pointBorderColor: "#0b0b0c",
            pointHoverBackgroundColor: "#fff4e7",
            pointHoverBorderColor: datasetColor,
            borderWidth: 2.2,
            pointRadius: 3.2,
            pointHoverRadius: 5,
            fill: true,
            spanGaps: true
          };
        })
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          subtitle: {
            display: Boolean(chart.direction),
            text: chart.direction || "",
            color: "#9a9690",
            font: { size: 12, weight: "700" },
            padding: { top: 0, bottom: 4 }
          },
          legend: {
            labels: {
              color: "#d9d1c9",
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true
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
                return `${context.dataset.label}: ${format(Number(context.raw), chart.format)}`;
              }
            }
          }
        },
        scales: {
          r: {
            min: rankMin,
            max: rankMax,
            reverse: Boolean(chart.reverse_scale),
            angleLines: { color: "rgba(255, 122, 24, 0.16)" },
            grid: { color: "rgba(255,255,255,0.1)" },
            pointLabels: {
              color: "#d9d1c9",
              font: { size: 12, weight: "700" }
            },
            ticks: {
              stepSize: 1,
              precision: 0,
              color: "#a7a19a",
              backdropColor: "rgba(0,0,0,0)",
              callback: function (value) {
                if (!Number.isInteger(Number(value))) return "";
                return format(Number(value), chart.format);
              }
            }
          }
        }
      }
    });
  }

  function renderQuadrantChart(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    if (!window.Chart) return fallback(canvas);
    const xMin = isNumber(chart.x_min) ? chart.x_min : (isNumber(chart.min) ? chart.min : 0);
    const xMax = isNumber(chart.x_max) ? chart.x_max : (isNumber(chart.max) ? chart.max : 100);
    const yMin = isNumber(chart.y_min) ? chart.y_min : (isNumber(chart.min) ? chart.min : 0);
    const yMax = isNumber(chart.y_max) ? chart.y_max : (isNumber(chart.max) ? chart.max : 100);
    const xMidpoint = isNumber(chart.x_midpoint) ? chart.x_midpoint : (xMin + xMax) / 2;
    const yMidpoint = isNumber(chart.y_midpoint) ? chart.y_midpoint : (yMin + yMax) / 2;
    const quadrantPlugin = {
      id: "quadrantOverlay",
      beforeDatasetsDraw: function (chartInstance) {
        const { ctx, chartArea, scales } = chartInstance;
        if (!chartArea || !scales.x || !scales.y) return;
        const xMid = scales.x.getPixelForValue(xMidpoint);
        const yMid = scales.y.getPixelForValue(yMidpoint);
        const { left, right, top, bottom } = chartArea;
        ctx.save();
        ctx.fillStyle = "rgba(255, 177, 94, 0.032)";
        ctx.fillRect(left, top, xMid - left, yMid - top);
        ctx.fillStyle = "rgba(125, 227, 141, 0.038)";
        ctx.fillRect(xMid, top, right - xMid, yMid - top);
        ctx.fillStyle = "rgba(94, 231, 255, 0.024)";
        ctx.fillRect(xMid, yMid, right - xMid, bottom - yMid);
        ctx.fillStyle = "rgba(255, 107, 107, 0.034)";
        ctx.fillRect(left, yMid, xMid - left, bottom - yMid);
        ctx.strokeStyle = "rgba(255, 122, 24, 0.62)";
        ctx.lineWidth = 1.35;
        ctx.setLineDash([8, 7]);
        ctx.beginPath();
        ctx.moveTo(xMid, top);
        ctx.lineTo(xMid, bottom);
        ctx.moveTo(left, yMid);
        ctx.lineTo(right, yMid);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.strokeStyle = "rgba(255,255,255,0.11)";
        ctx.lineWidth = 1;
        ctx.strokeRect(left, top, right - left, bottom - top);
        ctx.restore();
      },
      afterDraw: function (chartInstance) {
        const { ctx, chartArea } = chartInstance;
        if (!chartArea) return;
        const { left, right, top, bottom } = chartArea;
        ctx.save();
        ctx.fillStyle = "rgba(217, 209, 201, 0.82)";
        ctx.font = "900 10px Inter, sans-serif";
        ctx.textBaseline = "middle";
        ctx.textAlign = "right";
        ctx.fillText("High Profit", left - 10, top + 14);
        ctx.fillText("Low Profit", left - 10, bottom - 14);
        ctx.textBaseline = "top";
        ctx.textAlign = "left";
        ctx.fillText("High Risk", left + 4, bottom + 12);
        ctx.textAlign = "right";
        ctx.fillText("Low Risk", right - 4, bottom + 12);
        ctx.restore();
      },
      afterDatasetsDraw: function (chartInstance) {
        const { ctx } = chartInstance;
        ctx.save();
        ctx.font = "900 12px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        chartInstance.data.datasets.forEach((dataset, datasetIndex) => {
          const meta = chartInstance.getDatasetMeta(datasetIndex);
          const point = meta.data && meta.data[0];
          if (!point) return;
          const text = dataset.label;
          const metrics = ctx.measureText(text);
          const rawPoint = dataset.data && dataset.data[0] ? dataset.data[0] : {};
          const radius = Number(rawPoint.r) || 18;
          const labelY = point.y - radius - 8;
          ctx.fillStyle = "rgba(5, 5, 6, 0.78)";
          ctx.strokeStyle = "rgba(255,255,255,0.12)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(point.x - metrics.width / 2 - 7, labelY - 17, metrics.width + 14, 18, 4);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = dataset.borderColor;
          ctx.fillText(text, point.x, labelY - 2);
        });
        ctx.restore();
      }
    };

    new Chart(canvas, {
      type: "bubble",
      data: {
        datasets: (chart.datasets || []).map((dataset, index) => {
          const datasetColor = colorForLabel(dataset.label, colors[index % colors.length]);
          return {
            label: dataset.label,
            data: dataset.values || [],
            backgroundColor: `${datasetColor}38`,
            borderColor: datasetColor,
            hoverBackgroundColor: `${datasetColor}66`,
            borderWidth: 2.4,
            hoverBorderWidth: 3
          };
        })
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            top: 18,
            right: 16,
            bottom: 42,
            left: 88
          }
        },
        plugins: {
          subtitle: {
            display: true,
            text: "Bubble size represents valuation attractiveness (larger = more attractive)",
            color: "#9a9690",
            font: { size: 12, weight: "700" },
            padding: { top: 0, bottom: 6 }
          },
          legend: {
            position: "top",
            labels: {
              color: "#d9d1c9",
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true
            }
          },
          tooltip: {
            enabled: false
          }
        },
        scales: {
          x: {
            min: xMin,
            max: xMax,
            title: {
              display: true,
              text: chart.x_title || "Balance Sheet Strength / Low Risk",
              color: "#d9d1c9",
              font: { size: 12, weight: "800" }
            },
            ticks: {
              display: false,
              color: "#8f8982",
              stepSize: chart.axis_format === "zscore" ? 0.5 : undefined,
              callback: function (value) {
                return format(Number(value), chart.axis_format || "number");
              }
            },
            grid: { color: "rgba(255,255,255,0.045)", drawTicks: false }
          },
          y: {
            min: yMin,
            max: yMax,
            title: {
              display: true,
              text: chart.y_title || "Profitability & Cash Generation",
              color: "#d9d1c9",
              font: { size: 12, weight: "800" }
            },
            ticks: {
              display: false,
              color: "#8f8982",
              stepSize: chart.axis_format === "zscore" ? 0.5 : undefined,
              callback: function (value) {
                return format(Number(value), chart.axis_format || "number");
              }
            },
            grid: { color: "rgba(255,255,255,0.045)", drawTicks: false }
          }
        }
      },
      plugins: [quadrantPlugin]
    });
  }

  let compsDistanceChart = null;
  const COMPS_CACHE_KEY = "ratioDashboardCompsFinderLastResult";

  function renderAllCharts() {
    (data.charts || []).forEach(renderLineChart);
    (data.line_charts || []).forEach(renderLineChart);
    (data.bar_charts || []).forEach(renderBarChart);
    (data.multiple_charts || []).forEach(renderBarChart);
    if (data.bridge_chart) renderGroupedBar(data.bridge_chart);
    if (data.rank_chart) {
      if (data.rank_chart.type === "radar") {
        renderRadarChart(data.rank_chart);
      } else if (data.rank_chart.type === "quadrant") {
        renderQuadrantChart(data.rank_chart);
      } else {
        renderGroupedBar(data.rank_chart);
      }
    }
    (data.rank_charts || []).forEach((chart) => {
      if (chart.type === "radar") {
        renderRadarChart(chart);
      } else if (chart.type === "quadrant") {
        renderQuadrantChart(chart);
      } else {
        renderGroupedBar(chart);
      }
    });
    if (data.quadrant_chart) renderQuadrantChart(data.quadrant_chart);
    renderModelEbitdaChart();
  }

  function resizeChartsIn(element) {
    if (!window.Chart || !element) return;
    element.querySelectorAll("canvas").forEach((canvas) => {
      const chart = Chart.getChart(canvas);
      if (chart) window.setTimeout(() => chart.resize(), 80);
    });
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([element]).catch(() => {});
    }
  }

  function explodedTargetElements() {
    return Array.from(document.querySelectorAll(".chart-card, .formula-box")).filter((element) => (
      element.querySelector("canvas, .math-formula, .risk-heatmap")
    ));
  }

  function closeExplodedView() {
    const active = document.querySelector(".exploded-active");
    if (active) {
      active.classList.remove("exploded-active");
      resizeChartsIn(active);
    }
    document.body.classList.remove("exploded-backdrop-active");
  }

  function toggleExplodedView(element) {
    if (!element) return;

    if (document.querySelector(".exploded-active") === element) {
      closeExplodedView();
      return;
    }

    closeExplodedView();
    element.classList.add("exploded-active");
    document.body.classList.add("exploded-backdrop-active");
    resizeChartsIn(element);
  }

  function initExplodedControls() {
    explodedTargetElements().forEach((element) => {
      if (element.querySelector(":scope > .exploded-toggle")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "exploded-toggle";
      button.setAttribute("aria-label", "Open exploded view");
      button.title = "Open exploded view";
      button.addEventListener("click", () => toggleExplodedView(element));
      element.appendChild(button);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeExplodedView();
    });

    document.addEventListener("click", (event) => {
      if (document.body.classList.contains("exploded-backdrop-active") && event.target === document.body) {
        closeExplodedView();
      }
    });
  }

  let modelEbitdaYearsChart = null;
  let modelTerminalValueChart = null;

  function modelEbitdaRows(outputs) {
    return (outputs && outputs.ebitda_projection) || [];
  }

  function modelYearRows(outputs) {
    return modelEbitdaRows(outputs).filter((row) => /^Year\s+\d+$/i.test(row.label || ""));
  }

  function modelTerminalRows(outputs) {
    return modelEbitdaRows(outputs).filter((row) => /terminal/i.test(row.label || ""));
  }

  function ebitdaDatasets(rows) {
    return [
      {
        label: "Projected",
        data: rows.map((row) => row.projected),
        backgroundColor: "rgba(255,122,24,0.72)",
        borderColor: "#ff7a18",
        borderWidth: 1.4,
        borderRadius: 5
      },
      {
        label: "Present value",
        data: rows.map((row) => row.present_value),
        backgroundColor: "rgba(94,231,255,0.48)",
        borderColor: "#5ee7ff",
        borderWidth: 1.4,
        borderRadius: 5
      }
    ];
  }

  function renderModelEbitdaChart(outputs) {
    const yearCanvas = document.getElementById("model-ebitda-years-chart");
    const terminalCanvas = document.getElementById("model-terminal-value-chart");
    if (!yearCanvas && !terminalCanvas) return;
    if (!window.Chart) {
      fallback(yearCanvas);
      fallback(terminalCanvas);
      return;
    }
    const initialModel = data.models && data.initial_company ? data.models[data.initial_company] : null;
    const modelOutputs = outputs || (initialModel && initialModel.outputs);
    const yearRows = modelYearRows(modelOutputs);
    const terminalRows = modelTerminalRows(modelOutputs);

    if (yearCanvas) {
      modelEbitdaYearsChart = new Chart(yearCanvas, {
        type: "bar",
        data: {
          labels: yearRows.map((row) => row.label),
          datasets: ebitdaDatasets(yearRows)
        },
        options: commonOptions("money_m", "Higher is Better")
      });
    }

    if (terminalCanvas) {
      modelTerminalValueChart = new Chart(terminalCanvas, {
        type: "bar",
        data: {
          labels: terminalRows.map((row) => row.label),
          datasets: ebitdaDatasets(terminalRows)
        },
        options: commonOptions("money_m", "Higher is Better")
      });
    }
  }

  function updateEbitdaChart(chart, rows) {
    if (!chart) return;
    chart.data.labels = rows.map((row) => row.label);
    chart.data.datasets[0].data = rows.map((row) => row.projected);
    chart.data.datasets[1].data = rows.map((row) => row.present_value);
    chart.update();
  }

  function updateModelEbitdaChart(outputs) {
    const yearCanvas = document.getElementById("model-ebitda-years-chart");
    const terminalCanvas = document.getElementById("model-terminal-value-chart");
    if ((!yearCanvas && !terminalCanvas) || !window.Chart) return;
    if ((yearCanvas && !modelEbitdaYearsChart) || (terminalCanvas && !modelTerminalValueChart)) {
      renderModelEbitdaChart(outputs);
      return;
    }
    updateEbitdaChart(modelEbitdaYearsChart, modelYearRows(outputs));
    updateEbitdaChart(modelTerminalValueChart, modelTerminalRows(outputs));
  }

  const valuationControls = {
    revenue_growth: {
      slider: "revenueGrowthSlider",
      input: "revenueGrowthInput",
      scale: 100,
      outputType: "percent"
    },
    exit_multiple: {
      slider: "exitMultipleSlider",
      input: "exitMultipleInput",
      scale: 1,
      outputType: "multiple"
    },
    wacc: {
      slider: "waccSlider",
      input: "waccInput",
      scale: 100,
      outputType: "percent"
    }
  };

  let valuationTimer = null;

  function controlValue(name) {
    const control = valuationControls[name];
    const input = document.getElementById(control.input);
    if (!input) return null;
    const text = String(input.value || "").trim();
    if (!text || text === "-" || text === "." || text === "-.") return null;
    const raw = Number(text);
    if (!Number.isFinite(raw)) return null;
    return raw / control.scale;
  }

  function formatControlDisplay(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) : "";
  }

  function sanitizeDecimalText(value, allowNegative) {
    let text = String(value || "").replace(",", ".");
    let sign = "";
    if (allowNegative && text.trim().startsWith("-")) {
      sign = "-";
    }
    text = text.replace(/[^\d.]/g, "");

    const dotIndex = text.indexOf(".");
    if (dotIndex === -1) {
      return `${sign}${text.slice(0, 2)}`;
    }

    const whole = text.slice(0, dotIndex).slice(0, 2);
    const decimals = text.slice(dotIndex + 1).replace(/\./g, "").slice(0, 2);
    return `${sign}${whole}.${decimals}`;
  }

  function completeDecimalText(value) {
    return /^-?\d{1,2}(\.\d{0,2})?$/.test(String(value || ""));
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
    slider.min = scaledRange.min;
    slider.max = scaledRange.max;
    slider.step = scaledRange.step;
    slider.value = formatControlDisplay(scaledValue);

    input.dataset.min = scaledRange.min;
    input.dataset.max = scaledRange.max;
    input.value = formatControlDisplay(scaledValue);
  }

  function syncControl(name, source) {
    const control = valuationControls[name];
    const slider = document.getElementById(control.slider);
    const input = document.getElementById(control.input);
    if (!slider || !input) return;
    if (source === "slider") {
      input.value = formatControlDisplay(slider.value);
    } else {
      const cleaned = sanitizeDecimalText(input.value, Number(slider.min) < 0);
      if (input.value !== cleaned) input.value = cleaned;
      if (!completeDecimalText(cleaned)) return;
      slider.value = cleaned;
    }
    scheduleValuation();
  }

  function finalizeControl(name) {
    const control = valuationControls[name];
    const slider = document.getElementById(control.slider);
    const input = document.getElementById(control.input);
    if (!slider || !input) return;
    const cleaned = sanitizeDecimalText(input.value, Number(slider.min) < 0);
    const raw = Number(cleaned);
    if (!Number.isFinite(raw)) {
      input.value = formatControlDisplay(slider.value);
      return;
    }
    input.value = formatControlDisplay(raw);
    slider.value = input.value;
    scheduleValuation(0);
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
      ["Cost of debt", assumptions.cost_of_debt, "percent"],
      ["Cost of equity", assumptions.cost_of_equity, "percent"],
      ["Tax rate", assumptions.tax_rate, "percent"],
      ["TV growth", assumptions.long_term_growth, "percent"],
      ["LTGR", assumptions.ltgr, "percent"],
      ["Risk-free rate", assumptions.risk_free_rate, "percent"],
      ["Beta", assumptions.beta, "number"]
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
      exit_multiple: controlValue("exit_multiple"),
      wacc: controlValue("wacc")
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
        setText("actualSharePrice", format(outputs.current_price, "price"));
        updateValuationSignal(outputs);
        updateModelEbitdaChart(outputs);
      })
      .catch((error) => {
        setText("impliedPrice", error.message || "n/a");
        updateValuationSignal({});
      });
  }

  function updateValuationSignal(outputs) {
    const impliedPrice = document.getElementById("impliedPrice");
    const actualCard = document.getElementById("actualPriceCard");
    const implied = outputs.implied_share_price;
    const actual = outputs.current_price;
    const hasSignal = isNumber(implied) && isNumber(actual);
    const undervalued = hasSignal && implied >= actual;
    const overvalued = hasSignal && implied < actual;

    if (impliedPrice) {
      impliedPrice.classList.toggle("positive", undervalued);
      impliedPrice.classList.toggle("negative", overvalued);
    }
    if (actualCard) {
      actualCard.classList.toggle("undervalued", undervalued);
      actualCard.classList.toggle("overvalued", overvalued);
    }
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

  function setCompareBy(value) {
    document.querySelectorAll('input[name="compare_by"]').forEach((radio) => {
      radio.checked = radio.value === value;
    });
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
          label: result.distance_column ? result.distance_column.replaceAll("_", " ") : "Distance",
          data: matches.map((match) => match.distance),
          backgroundColor: matches.map((match, index) => translucentColorForLabel(match.ticker, colors[index % colors.length], "cc")),
          borderColor: matches.map((match, index) => colorForLabel(match.ticker, colors[index % colors.length])),
          borderWidth: 1.4,
          borderRadius: 6
        }]
      },
      options: commonOptions("number", "Lower is Better")
    });
  }

  function saveComparableSearch(result) {
    if (!result || !window.sessionStorage) return;
    try {
      sessionStorage.setItem(COMPS_CACHE_KEY, JSON.stringify(result));
    } catch (error) {
      // Ignore storage failures; the live search result has already rendered.
    }
  }

  function restoreComparableSearch() {
    if (!window.sessionStorage) return;
    let result = null;
    try {
      result = JSON.parse(sessionStorage.getItem(COMPS_CACHE_KEY) || "null");
    } catch (error) {
      sessionStorage.removeItem(COMPS_CACHE_KEY);
      return;
    }
    if (!result || !Array.isArray(result.matches)) return;

    const input = document.getElementById("compsTicker");
    if (input && result.ticker) input.value = result.ticker;
    if (result.compare_by) setCompareBy(result.compare_by);

    renderCompsNameRanking(result);
    renderCompsResults(result);
    setCompsStatus(
      `${result.matches.length} closest matches shown from the last distance search.`,
      "ok"
    );
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
        saveComparableSearch(body);
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
    restoreComparableSearch();
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
      if (input) input.addEventListener("blur", () => finalizeControl(name));
    });
    loadCompanyModel(select.value);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initFastNavigation();
    renderAllCharts();
    initValuation();
    initComparables();
    initExplodedControls();
  });
})();
