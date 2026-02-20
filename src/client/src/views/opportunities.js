/**
 * Opportunities view.
 *
 * Two sections:
 * 1. Watchlist Management - add/remove symbols to scan
 * 2. Opportunity Results - scatter plot + tiered table, or butterfly chart
 */

import { createTable } from "../components/table.js";
import { createScatterPlot } from "../components/scatter-plot.js";
import { createButterflyChart } from "../components/butterfly-chart.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { formatCurrency, formatPercent, formatNumber, formatDate } from "../format.js";

let cachedOpportunities = [];
let activeView = "scatter"; // "scatter" | "butterfly"
let currentScatterSvg = null;

/** Tier definitions ordered safest-first for the tiered table. */
const TIERS = [
  { name: "Defensive", sigmaMin: 2.0, sigmaMax: 2.5, borderColor: "#34d399" },
  { name: "Conservative", sigmaMin: 1.5, sigmaMax: 2.0, borderColor: "#60a5fa" },
  { name: "Moderate", sigmaMin: 1.0, sigmaMax: 1.5, borderColor: "#fbbf24" },
  { name: "Aggressive", sigmaMin: 0.5, sigmaMax: 1.0, borderColor: "#ef4444" },
];

/**
 * Render the opportunities view.
 * @param {HTMLElement} container
 * @param {object} state
 */
export function render(container, state) {
  container.innerHTML = "";

  // Header
  const header = document.createElement("div");
  header.className = "flex items-center justify-between mb-4";
  header.innerHTML = `
    <h1 style="font-size: 18px; font-weight: 600;">Opportunities</h1>
    <div class="flex items-center gap-2">
      <button class="btn btn-sm" id="btn-mark-all-read">Mark All Read</button>
      <button class="btn btn-sm btn-primary" id="btn-scan-now">Scan Now</button>
    </div>
  `;
  container.appendChild(header);

  // Watchlist section
  const watchlistSection = document.createElement("div");
  watchlistSection.style.marginBottom = "24px";
  watchlistSection.innerHTML = `
    <h2 style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">Watchlist</h2>
    <div class="flex items-center gap-2" style="margin-bottom: 12px;">
      <input type="text" id="watchlist-input" placeholder="Symbol (e.g. AAPL)"
        style="padding: 4px 8px; border: 1px solid var(--color-border); border-radius: 4px;
        background: var(--color-bg); color: var(--color-text); font-family: inherit; font-size: 13px; width: 140px;" />
      <button class="btn btn-sm btn-primary" id="btn-add-symbol">Add</button>
    </div>
    <div id="watchlist-table"></div>
  `;
  container.appendChild(watchlistSection);

  // Opportunity filters + view toggle
  const filterSection = document.createElement("div");
  filterSection.style.marginBottom = "12px";
  filterSection.innerHTML = `
    <h2 style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">Scanned Opportunities</h2>
    <div class="flex items-center gap-2" style="margin-bottom: 12px;">
      <select id="filter-symbol" style="padding: 4px 6px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg); color: var(--color-text); font-size: 12px;">
        <option value="">All Symbols</option>
      </select>
      <select id="filter-direction" style="padding: 4px 6px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg); color: var(--color-text); font-size: 12px;">
        <option value="">All Directions</option>
        <option value="put">Put</option>
        <option value="call">Call</option>
      </select>
      <select id="filter-profile" style="padding: 4px 6px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg); color: var(--color-text); font-size: 12px;">
        <option value="">All Profiles</option>
        <option value="conservative">Conservative</option>
        <option value="aggressive">Aggressive</option>
        <option value="moderate">Moderate</option>
        <option value="defensive">Defensive</option>
      </select>
      <div style="margin-left: auto;" class="flex items-center gap-2">
        <button class="btn btn-sm btn-primary" id="btn-view-scatter">Chart + Table</button>
        <button class="btn btn-sm" id="btn-view-butterfly" disabled>Butterfly</button>
      </div>
    </div>
  `;
  container.appendChild(filterSection);

  // Opportunity results area
  const resultsDiv = document.createElement("div");
  resultsDiv.id = "opportunity-results";
  resultsDiv.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading...</div>`;
  container.appendChild(resultsDiv);

  // View toggle buttons
  const btnScatter = filterSection.querySelector("#btn-view-scatter");
  const btnButterfly = filterSection.querySelector("#btn-view-butterfly");

  function updateViewButtons() {
    if (activeView === "scatter") {
      btnScatter.className = "btn btn-sm btn-primary";
      btnButterfly.className = "btn btn-sm";
    } else {
      btnScatter.className = "btn btn-sm";
      btnButterfly.className = "btn btn-sm btn-primary";
    }
  }

  btnScatter.addEventListener("click", () => {
    activeView = "scatter";
    updateViewButtons();
    renderCurrentView(resultsDiv);
  });

  btnButterfly.addEventListener("click", () => {
    if (btnButterfly.disabled) return;
    activeView = "butterfly";
    updateViewButtons();
    renderCurrentView(resultsDiv);
  });

  // Wire up events
  header.querySelector("#btn-mark-all-read").addEventListener("click", async () => {
    try {
      await api.markAllOpportunitiesRead();
      toast.success("All opportunities marked as read");
      loadOpportunities(resultsDiv, filterSection);
    } catch (err) {
      toast.error(err.message);
    }
  });

  header.querySelector("#btn-scan-now").addEventListener("click", async () => {
    const btn = header.querySelector("#btn-scan-now");
    btn.disabled = true;
    btn.textContent = "Scanning...";
    try {
      const result = await api.triggerScan();
      toast.success(`Scanned ${result.symbols_scanned} symbols, found ${result.opportunities_found} opportunities`);
      loadOpportunities(resultsDiv, filterSection);
    } catch (err) {
      toast.error(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Scan Now";
    }
  });

  watchlistSection.querySelector("#btn-add-symbol").addEventListener("click", async () => {
    const input = watchlistSection.querySelector("#watchlist-input");
    const symbol = input.value.trim().toUpperCase();
    if (!symbol) return;
    try {
      await api.addToWatchlist(symbol);
      input.value = "";
      toast.success(`Added ${symbol} to watchlist`);
      loadWatchlist(watchlistSection.querySelector("#watchlist-table"));
    } catch (err) {
      toast.error(err.message);
    }
  });

  // Allow Enter key in input
  watchlistSection.querySelector("#watchlist-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      watchlistSection.querySelector("#btn-add-symbol").click();
    }
  });

  // Filter change handlers
  const symbolFilter = filterSection.querySelector("#filter-symbol");
  const applyFilters = () => loadOpportunities(resultsDiv, filterSection);
  symbolFilter.addEventListener("change", () => {
    const hasSymbol = !!symbolFilter.value;
    btnButterfly.disabled = !hasSymbol;
    if (!hasSymbol && activeView === "butterfly") {
      activeView = "scatter";
      updateViewButtons();
    }
    applyFilters();
  });
  filterSection.querySelector("#filter-direction").addEventListener("change", applyFilters);
  filterSection.querySelector("#filter-profile").addEventListener("change", applyFilters);

  // Initial load
  loadWatchlist(watchlistSection.querySelector("#watchlist-table"));
  loadOpportunities(resultsDiv, filterSection);
}

async function loadWatchlist(container) {
  try {
    const items = await api.listWatchlist();
    if (!items || items.length === 0) {
      container.innerHTML = `<div style="padding: 8px; color: var(--color-muted); font-size: 12px;">No symbols on watchlist. Add symbols above to start scanning.</div>`;
      return;
    }

    const table = createTable({
      columns: [
        { key: "symbol", label: "Symbol", sortable: false },
        { key: "notes", label: "Notes", sortable: false, render: (v) => v || "\u2014" },
        { key: "created_at", label: "Added", sortable: false, render: (v) => formatDate(v) },
        {
          key: "actions",
          label: "",
          sortable: false,
          render: (_val, row) => {
            const btn = document.createElement("button");
            btn.className = "btn btn-sm";
            btn.textContent = "Remove";
            btn.style.color = "var(--color-error)";
            btn.addEventListener("click", async () => {
              try {
                await api.removeFromWatchlist(row.symbol);
                toast.success(`Removed ${row.symbol}`);
                loadWatchlist(container);
              } catch (err) {
                toast.error(err.message);
              }
            });
            return btn;
          },
        },
      ],
      data: items,
    });
    container.innerHTML = "";
    container.appendChild(table);

    // Click a watchlist row to highlight that symbol's dots on the scatter plot
    const rows = table.querySelectorAll("tbody tr");
    for (let i = 0; i < rows.length; i++) {
      const symbol = items[i]?.symbol;
      if (!symbol) continue;
      rows[i].style.cursor = "pointer";
      rows[i].addEventListener("click", (e) => {
        // Don't trigger if clicking the Remove button
        if (e.target.tagName === "BUTTON") return;
        if (currentScatterSvg && currentScatterSvg.highlightSymbol) {
          currentScatterSvg.highlightSymbol(symbol);
        }
      });
    }

    // Populate symbol filter dropdown
    const symbolFilter = document.getElementById("filter-symbol");
    if (symbolFilter) {
      const currentValue = symbolFilter.value;
      symbolFilter.innerHTML = `<option value="">All Symbols</option>`;
      for (const item of items) {
        const opt = document.createElement("option");
        opt.value = item.symbol;
        opt.textContent = item.symbol;
        if (item.symbol === currentValue) opt.selected = true;
        symbolFilter.appendChild(opt);
      }
    }
  } catch (err) {
    container.innerHTML = `<div style="color: var(--color-error);">${err.message}</div>`;
  }
}

async function loadOpportunities(container, filterSection) {
  container.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading...</div>`;

  const symbol = filterSection.querySelector("#filter-symbol").value || undefined;
  const direction = filterSection.querySelector("#filter-direction").value || undefined;
  const profile = filterSection.querySelector("#filter-profile").value || undefined;

  try {
    const opportunities = await api.listOpportunities({ symbol, direction, profile });
    cachedOpportunities = opportunities || [];
    renderCurrentView(container);
  } catch (err) {
    container.innerHTML = `<div style="padding: 16px; color: var(--color-error);">${err.message}</div>`;
  }
}

function renderCurrentView(container) {
  if (cachedOpportunities.length === 0) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-muted);">No opportunities found. Add symbols to watchlist and run a scan.</div>`;
    return;
  }

  if (activeView === "butterfly") {
    renderButterflyView(container, cachedOpportunities);
  } else {
    renderScatterView(container, cachedOpportunities);
  }
}

/**
 * Render scatter plot + tiered table view.
 */
function renderScatterView(container, opportunities) {
  container.innerHTML = "";
  clearSelectedRow();
  const containerWidth = container.offsetWidth || 800;

  // Scatter plot
  let scatterSvg;
  try {
    scatterSvg = createScatterPlot(opportunities, {
      onDotClick: (opp) => handleDotClick(opp),
      width: containerWidth,
      height: 350,
    });
  } catch (err) {
    container.innerHTML = `<div style="padding: 16px; color: var(--color-error);">Chart error: ${err.message}</div>`;
    return;
  }

  currentScatterSvg = scatterSvg;

  const chartWrapper = document.createElement("div");
  chartWrapper.style.marginBottom = "16px";
  chartWrapper.appendChild(scatterSvg);
  container.appendChild(chartWrapper);

  // Tiered table
  const tableWrapper = document.createElement("div");
  tableWrapper.id = "tiered-table";
  container.appendChild(tableWrapper);

  buildTieredTable(tableWrapper, opportunities, scatterSvg);
}

/**
 * Build a tiered table grouped by profile band.
 */
function buildTieredTable(container, opportunities, scatterSvg) {
  const table = document.createElement("table");
  table.className = "data-table";
  table.style.width = "100%";

  // Header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const cols = ["Symbol", "Dir", "Strike", "DTE", "Prem/Sh", "Ann. Yield", "P(ITM)", "Sigma", "Bias Score"];
  for (const label of cols) {
    const th = document.createElement("th");
    th.textContent = label;
    if (["Strike", "DTE", "Prem/Sh", "Ann. Yield", "P(ITM)", "Sigma", "Bias Score"].includes(label)) {
      th.classList.add("align-right");
    }
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");

  // Group opportunities into tiers
  for (const tier of TIERS) {
    const tierOpps = opportunities.filter((o) => {
      const s = o.sigma_distance || 0;
      return s >= tier.sigmaMin && s < tier.sigmaMax;
    }).sort((a, b) => (b.bias_score || 0) - (a.bias_score || 0));

    if (tierOpps.length === 0) continue;

    // Tier header row
    const tierRow = document.createElement("tr");
    const tierCell = document.createElement("td");
    tierCell.colSpan = cols.length;
    tierCell.style.cssText = `
      border-left: 4px solid ${tier.borderColor};
      padding: 6px 10px;
      font-weight: 600;
      font-size: 12px;
      color: ${tier.borderColor};
      background: ${tier.borderColor}11;
    `;
    tierCell.textContent = `${tier.name} (${tier.sigmaMin}\u2013${tier.sigmaMax}\u03C3)`;
    tierRow.appendChild(tierCell);
    tbody.appendChild(tierRow);

    // Data rows
    for (const opp of tierOpps) {
      const tr = document.createElement("tr");
      tr.setAttribute("data-opp-id", opp.id);
      tr.style.cursor = "pointer";

      const cells = [
        opp.symbol,
        (opp.direction || "").toUpperCase(),
        formatCurrency(opp.strike),
        opp.dte,
        formatCurrency(opp.premium_per_share),
        formatPercent(opp.annualized_yield_pct, true),
        formatPercent(opp.p_itm, true),
        formatNumber(opp.sigma_distance),
        formatNumber(opp.bias_score),
      ];

      for (let i = 0; i < cells.length; i++) {
        const td = document.createElement("td");
        td.textContent = cells[i] != null ? String(cells[i]) : "\u2014";
        if (i >= 2) td.classList.add("align-right");
        tr.appendChild(td);
      }

      // Row click → highlight dot on scatter
      tr.addEventListener("click", () => {
        if (scatterSvg && scatterSvg.highlightDot) {
          scatterSvg.highlightDot(opp.id);
        }
        flashRow(tr);
      });

      tbody.appendChild(tr);
    }
  }

  // Handle opportunities outside defined tiers (sigma < 0.5 or >= 2.5)
  const outsideTier = opportunities.filter((o) => {
    const s = o.sigma_distance || 0;
    return s < 0.5 || s >= 2.5;
  });
  if (outsideTier.length > 0) {
    const tierRow = document.createElement("tr");
    const tierCell = document.createElement("td");
    tierCell.colSpan = cols.length;
    tierCell.style.cssText = `
      border-left: 4px solid #94a3b8;
      padding: 6px 10px;
      font-weight: 600;
      font-size: 12px;
      color: var(--color-muted);
    `;
    tierCell.textContent = "Other";
    tierRow.appendChild(tierCell);
    tbody.appendChild(tierRow);

    for (const opp of outsideTier) {
      const tr = document.createElement("tr");
      tr.setAttribute("data-opp-id", opp.id);
      tr.style.cursor = "pointer";
      const cells = [
        opp.symbol,
        (opp.direction || "").toUpperCase(),
        formatCurrency(opp.strike),
        opp.dte,
        formatCurrency(opp.premium_per_share),
        formatPercent(opp.annualized_yield_pct, true),
        formatPercent(opp.p_itm, true),
        formatNumber(opp.sigma_distance),
        formatNumber(opp.bias_score),
      ];
      for (let i = 0; i < cells.length; i++) {
        const td = document.createElement("td");
        td.textContent = cells[i] != null ? String(cells[i]) : "\u2014";
        if (i >= 2) td.classList.add("align-right");
        tr.appendChild(td);
      }
      tr.addEventListener("click", () => {
        if (scatterSvg && scatterSvg.highlightDot) {
          scatterSvg.highlightDot(opp.id);
        }
        flashRow(tr);
      });
      tbody.appendChild(tr);
    }
  }

  table.appendChild(tbody);
  container.appendChild(table);
}

/**
 * Handle dot click from scatter plot — scroll to and highlight the matching table row.
 */
function handleDotClick(opp) {
  const row = document.querySelector(`tr[data-opp-id="${opp.id}"]`);
  if (!row) return;

  // Clear any previous selection, then mark this row as selected
  clearSelectedRow();
  row.classList.add("selected-row");
  row.style.backgroundColor = "rgba(96, 165, 250, 0.25)";
  row.style.outline = "2px solid rgba(96, 165, 250, 0.6)";
  row.style.outlineOffset = "-2px";
  selectedRow = row;

  row.scrollIntoView({ behavior: "smooth", block: "center" });
}

let selectedRow = null;

/** Clear the currently selected table row highlight. */
function clearSelectedRow() {
  if (selectedRow) {
    selectedRow.classList.remove("selected-row");
    selectedRow.style.backgroundColor = "";
    selectedRow.style.outline = "";
    selectedRow.style.outlineOffset = "";
    selectedRow = null;
  }
}

/**
 * Flash a table row with a brief highlight background.
 */
function flashRow(row) {
  row.style.transition = "background-color 0.3s";
  row.style.backgroundColor = "rgba(96, 165, 250, 0.2)";
  setTimeout(() => {
    row.style.backgroundColor = "";
  }, 1500);
}

/**
 * Render butterfly chart view for a single symbol.
 */
function renderButterflyView(container, opportunities) {
  container.innerHTML = "";
  currentScatterSvg = null;
  clearSelectedRow();

  const currentPrice = opportunities[0]?.current_price;
  if (!currentPrice) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-muted);">No price data available for butterfly chart.</div>`;
    return;
  }

  const containerWidth = container.offsetWidth || 800;

  let butterflySvg;
  try {
    butterflySvg = createButterflyChart(opportunities, currentPrice, {
      width: containerWidth,
    });
  } catch (err) {
    container.innerHTML = `<div style="padding: 16px; color: var(--color-error);">Chart error: ${err.message}</div>`;
    return;
  }

  const chartWrapper = document.createElement("div");
  chartWrapper.style.marginBottom = "16px";
  chartWrapper.appendChild(butterflySvg);
  container.appendChild(chartWrapper);

  // Compact reference table below
  const refTable = document.createElement("table");
  refTable.className = "data-table";
  refTable.style.width = "100%";

  const thead = document.createElement("thead");
  const hRow = document.createElement("tr");
  for (const label of ["Dir", "Strike", "DTE", "Ann. Yield", "P(ITM)", "Sigma", "Bias"]) {
    const th = document.createElement("th");
    th.textContent = label;
    if (label !== "Dir") th.classList.add("align-right");
    hRow.appendChild(th);
  }
  thead.appendChild(hRow);
  refTable.appendChild(thead);

  const tbody = document.createElement("tbody");
  const sorted = [...opportunities].sort((a, b) => a.strike - b.strike);
  for (const opp of sorted) {
    const tr = document.createElement("tr");
    const cells = [
      (opp.direction || "").toUpperCase(),
      formatCurrency(opp.strike),
      opp.dte,
      formatPercent(opp.annualized_yield_pct, true),
      formatPercent(opp.p_itm, true),
      formatNumber(opp.sigma_distance),
      formatNumber(opp.bias_score),
    ];
    for (let i = 0; i < cells.length; i++) {
      const td = document.createElement("td");
      td.textContent = cells[i] != null ? String(cells[i]) : "\u2014";
      if (i >= 1) td.classList.add("align-right");
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  refTable.appendChild(tbody);
  container.appendChild(refTable);
}
