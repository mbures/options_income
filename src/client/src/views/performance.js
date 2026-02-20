/**
 * Performance view.
 *
 * Displays per-symbol P&L metrics from the server-side performance endpoint,
 * with all-time summary and trended 1W/1M/1Q table.
 */

import * as api from "../api.js";
import { formatCurrency, formatPercent, formatDate } from "../format.js";

let selectedWheelId = null;

/**
 * Render the performance view.
 * @param {HTMLElement} container
 * @param {object} state
 */
export function render(container, state) {
  container.innerHTML = "";

  const wheels = (state.wheels || []).filter((w) => w.is_active);

  // Header
  const header = document.createElement("div");
  header.className = "flex items-center justify-between mb-4";

  const title = document.createElement("h1");
  title.style.fontSize = "18px";
  title.style.fontWeight = "600";
  title.textContent = "Performance";

  // Symbol filter
  const select = document.createElement("select");
  select.className = "btn";
  select.style.minWidth = "120px";

  const allOpt = document.createElement("option");
  allOpt.value = "all";
  allOpt.textContent = "All Symbols";
  select.appendChild(allOpt);

  for (const w of wheels) {
    const opt = document.createElement("option");
    opt.value = w.id;
    opt.textContent = w.symbol;
    if (selectedWheelId === w.id) opt.selected = true;
    select.appendChild(opt);
  }

  header.appendChild(title);
  header.appendChild(select);
  container.appendChild(header);

  if (wheels.length === 0) {
    container.innerHTML += `
      <div style="padding: 40px; text-align: center; color: var(--color-muted);">
        No wheels configured. Create positions from the Dashboard to see performance.
      </div>
    `;
    return;
  }

  const cardsContainer = document.createElement("div");
  cardsContainer.id = "perf-cards";
  container.appendChild(cardsContainer);

  // Load performance - aggregate by default, per-wheel when a symbol is selected
  if (selectedWheelId && selectedWheelId !== "all") {
    const wheel = wheels.find((w) => w.id === selectedWheelId);
    if (wheel) loadWheelPerformance(cardsContainer, wheel);
  } else {
    loadAggregatePerformance(cardsContainer);
  }

  select.addEventListener("change", (e) => {
    const val = e.target.value;
    selectedWheelId = val === "all" ? null : parseInt(val, 10);
    if (selectedWheelId != null) {
      const wheel = wheels.find((w) => w.id === selectedWheelId);
      if (wheel) loadWheelPerformance(cardsContainer, wheel);
    } else {
      loadAggregatePerformance(cardsContainer);
    }
  });
}

async function loadAggregatePerformance(container) {
  container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading performance data...</div>`;

  try {
    const perf = await api.getPerformance();
    container.innerHTML = "";
    container.appendChild(renderCard({ wheel: { symbol: "All Symbols" }, perf }));
  } catch (err) {
    container.innerHTML = `<div style="padding: 40px; text-align: center; color: var(--color-error);">${err.message}</div>`;
  }
}

async function loadWheelPerformance(container, wheel) {
  container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading performance data...</div>`;

  try {
    const perf = await api.getWheelPerformance(wheel.id);
    container.innerHTML = "";
    container.appendChild(renderCard({ wheel, perf }));
  } catch (err) {
    container.innerHTML = "";
    container.appendChild(renderCard({ wheel, error: err.message, perf: null }));
  }
}

/**
 * Color a P&L value green (positive) or red (negative).
 * @param {number} value
 * @returns {string} CSS color value
 */
function pnlColor(value) {
  if (value > 0) return "var(--color-success, #22c55e)";
  if (value < 0) return "var(--color-error, #ef4444)";
  return "inherit";
}

/**
 * Format a P&L value with color styling.
 * @param {number} value
 * @returns {string} HTML string
 */
function coloredPnl(value) {
  return `<span style="color: ${pnlColor(value)}">${formatCurrency(value)}</span>`;
}

function renderCard(cardData) {
  const { wheel, perf, error } = cardData;
  const card = document.createElement("div");
  card.className = "summary-card";
  card.style.marginBottom = "16px";

  if (error) {
    card.innerHTML = `
      <div style="font-size: 15px; font-weight: 600; margin-bottom: 8px;">${wheel.symbol}</div>
      <div style="color: var(--color-error);">${error}</div>
    `;
    return card;
  }

  const at = perf.all_time;

  card.innerHTML = `
    <div class="flex items-center justify-between" style="margin-bottom: 12px;">
      <span style="font-size: 15px; font-weight: 600;">${wheel.symbol}</span>
      <button class="btn btn-sm export-csv-btn">Export CSV</button>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
      <div>
        <div class="label">Total P&amp;L</div>
        <div style="font-size: 16px; font-weight: 600;">${coloredPnl(at.total_pnl)}</div>
      </div>
      <div>
        <div class="label">Option Premium</div>
        <div style="font-size: 16px; font-weight: 600;">${coloredPnl(at.option_premium_pnl)}</div>
      </div>
      <div>
        <div class="label">Stock P&amp;L</div>
        <div style="font-size: 16px; font-weight: 600;">${coloredPnl(at.stock_pnl)}</div>
      </div>
      <div>
        <div class="label">Win Rate</div>
        <div style="font-size: 16px; font-weight: 600;">${formatPercent(at.win_rate)}</div>
      </div>
    </div>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
      <thead>
        <tr style="border-bottom: 1px solid var(--color-border, #e5e7eb);">
          <th style="text-align: left; padding: 4px 8px; font-weight: 500;"></th>
          <th style="text-align: right; padding: 4px 8px; font-weight: 500;">1W</th>
          <th style="text-align: right; padding: 4px 8px; font-weight: 500;">1M</th>
          <th style="text-align: right; padding: 4px 8px; font-weight: 500;">1Q</th>
        </tr>
      </thead>
      <tbody>
        ${trendRow("Total P&L", "total_pnl", perf)}
        ${trendRow("Option Premium", "option_premium_pnl", perf)}
        ${trendRow("Stock P&L", "stock_pnl", perf)}
        ${trendRowPlain("Trades Closed", "trades_closed", perf)}
      </tbody>
    </table>
  `;

  // Export CSV - lazy-load trades on click
  card.querySelector(".export-csv-btn").addEventListener("click", async () => {
    try {
      const trades = await api.listTrades(wheel.id);
      exportCSV(wheel.symbol, trades || []);
    } catch (err) {
      alert("Failed to load trades for export: " + err.message);
    }
  });

  return card;
}

/**
 * Build a trend table row with colored P&L values.
 */
function trendRow(label, field, perf) {
  const w = perf.one_week[field];
  const m = perf.one_month[field];
  const q = perf.one_quarter[field];
  return `
    <tr>
      <td style="padding: 4px 8px;">${label}</td>
      <td style="text-align: right; padding: 4px 8px;">${coloredPnl(w)}</td>
      <td style="text-align: right; padding: 4px 8px;">${coloredPnl(m)}</td>
      <td style="text-align: right; padding: 4px 8px;">${coloredPnl(q)}</td>
    </tr>`;
}

/**
 * Build a trend table row with plain (non-currency) values.
 */
function trendRowPlain(label, field, perf) {
  return `
    <tr>
      <td style="padding: 4px 8px;">${label}</td>
      <td style="text-align: right; padding: 4px 8px;">${perf.one_week[field]}</td>
      <td style="text-align: right; padding: 4px 8px;">${perf.one_month[field]}</td>
      <td style="text-align: right; padding: 4px 8px;">${perf.one_quarter[field]}</td>
    </tr>`;
}

function exportCSV(symbol, trades) {
  const headers = [
    "Date",
    "Direction",
    "Strike",
    "Expiration",
    "Premium/Share",
    "Contracts",
    "Total Premium",
    "Outcome",
  ];

  const rows = trades.map((t) => [
    formatDate(t.opened_at),
    (t.direction || "").toUpperCase(),
    t.strike,
    t.expiration_date,
    t.premium_per_share,
    t.contracts,
    t.total_premium,
    t.outcome,
  ]);

  const csv =
    headers.join(",") +
    "\n" +
    rows.map((r) => r.join(",")).join("\n");

  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${symbol}_trades_${formatDate(new Date())}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
