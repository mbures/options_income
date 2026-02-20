/**
 * Dashboard view.
 *
 * Renders portfolio summary cards and positions table with
 * context-sensitive action buttons per wheel state.
 */

import { createTable } from "../components/table.js";
import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh, navigate, getState } from "../app.js";
import { formatCurrency, formatDate } from "../format.js";

/**
 * Render the dashboard view.
 * @param {HTMLElement} container
 * @param {object} state
 */
export function render(container, state) {
  container.innerHTML = "";

  // Header row: title + action buttons
  const header = document.createElement("div");
  header.className = "flex items-center justify-between mb-4";
  header.innerHTML = `
    <h1 style="font-size: 18px; font-weight: 600;">Dashboard</h1>
    <div class="flex gap-2">
      <button class="btn btn-sm" id="btn-refresh"><span class="spinner" id="refresh-spinner" style="display:none;"></span> Refresh</button>
      <button class="btn btn-sm btn-primary" id="btn-new-wheel">+ New Wheel</button>
    </div>
  `;
  container.appendChild(header);

  // Wire header buttons
  header.querySelector("#btn-refresh").addEventListener("click", async (e) => {
    const spinner = header.querySelector("#refresh-spinner");
    const btn = e.currentTarget;
    btn.disabled = true;
    spinner.style.display = "inline-block";
    await refresh();
    spinner.style.display = "none";
    btn.disabled = false;
  });

  header.querySelector("#btn-new-wheel").addEventListener("click", () => {
    panel.open("init-wheel", {}, "New Wheel Position");
  });

  // Summary cards
  const cards = renderSummaryCards(state);
  container.appendChild(cards);

  // Positions table
  const tableSection = renderPositionsTable(state);
  container.appendChild(tableSection);
}

/**
 * Render portfolio summary cards.
 */
function renderSummaryCards(state) {
  const wheels = state.wheels || [];
  const positions = state.positions || [];

  const activeWheels = wheels.filter((w) => w.is_active);
  const openStates = ["cash_put_open", "shares_call_open"];
  const openPositions = activeWheels.filter((w) =>
    openStates.includes(w.state)
  );
  const totalCapital = activeWheels.reduce(
    (sum, w) => sum + (w.capital_allocated || 0),
    0
  );

  // Total premium from positions data (premium_collected)
  const positionsList = Array.isArray(positions)
    ? positions
    : positions.positions || [];
  const totalPremium = positionsList.reduce(
    (sum, p) => sum + (p.premium_collected || 0),
    0
  );

  const cardData = [
    { label: "Total Capital", value: formatCurrency(totalCapital) },
    { label: "Open Premium", value: formatCurrency(totalPremium) },
    { label: "Open Positions", value: openPositions.length },
    { label: "Active Wheels", value: activeWheels.length },
  ];

  const div = document.createElement("div");
  div.className = "summary-cards";

  for (const card of cardData) {
    const el = document.createElement("div");
    el.className = "summary-card";
    el.innerHTML = `
      <div class="label">${card.label}</div>
      <div class="value">${card.value}</div>
    `;
    div.appendChild(el);
  }

  return div;
}

/**
 * Render the positions table.
 */
function renderPositionsTable(state) {
  const wheels = state.wheels || [];
  const positions = state.positions || [];

  // Build position lookup by wheel_id
  const positionsList = Array.isArray(positions)
    ? positions
    : positions.positions || [];
  const posMap = {};
  for (const p of positionsList) {
    posMap[p.wheel_id] = p;
  }

  // Build table data from active wheels merged with position data
  const activeWheels = wheels.filter((w) => w.is_active);
  const tableData = activeWheels.map((w) => {
    const pos = posMap[w.id];
    return {
      id: w.id,
      symbol: w.symbol,
      state: w.state,
      profile: w.profile,
      capital_allocated: w.capital_allocated,
      trade_id: pos ? pos.trade_id : null,
      open_trade: pos
        ? `${pos.direction.toUpperCase()} $${pos.strike.toFixed(2)} exp ${pos.expiration_date}`
        : null,
      current_price: pos ? pos.current_price : null,
      market_open: pos ? pos.market_open : false,
      close_price: pos ? pos.close_price : null,
      day_range: pos && pos.low_price != null && pos.high_price != null
        ? { low: pos.low_price, high: pos.high_price }
        : null,
      moneyness_label: pos ? pos.moneyness_label : null,
      dte: pos ? pos.dte_calendar : null,
      risk_level: pos ? pos.risk_level : null,
      // Keep full position for action handlers
      _position: pos,
      _wheel: w,
    };
  });

  const columns = [
    { key: "symbol", label: "Symbol", sortable: true },
    {
      key: "state",
      label: "State",
      sortable: true,
      render: (val) => renderStateBadge(val),
    },
    { key: "profile", label: "Profile", sortable: true },
    {
      key: "capital_allocated",
      label: "Capital",
      sortable: true,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    {
      key: "open_trade",
      label: "Open Trade",
      sortable: false,
      render: (val) => val || "\u2014",
    },
    {
      key: "current_price",
      label: "Price",
      sortable: true,
      align: "right",
      render: (_val, row) => renderPriceCell(row),
    },
    {
      key: "day_range",
      label: "Day Range",
      sortable: false,
      align: "right",
      render: (val) => renderDayRange(val),
    },
    {
      key: "moneyness_label",
      label: "Moneyness",
      sortable: false,
      render: (val) => val || "\u2014",
    },
    {
      key: "dte",
      label: "DTE",
      sortable: true,
      align: "right",
      render: (val) => (val != null ? String(val) : "\u2014"),
    },
    {
      key: "risk_level",
      label: "Risk",
      sortable: true,
      render: (val) => renderRiskBadge(val),
    },
    {
      key: "actions",
      label: "Actions",
      sortable: false,
      render: (_val, row) => renderActionButtons(row),
    },
  ];

  const div = document.createElement("div");

  if (activeWheels.length === 0) {
    div.innerHTML = `
      <div style="padding: 40px; text-align: center; color: var(--color-muted);">
        No positions yet. Click <strong>+ New Wheel</strong> to get started.
      </div>
    `;
    return div;
  }

  const table = createTable({
    columns,
    data: tableData,
    sortKey: "symbol",
    sortDir: "asc",
  });

  div.appendChild(table);
  return div;
}

/**
 * Render a state badge.
 */
function renderStateBadge(state) {
  const labels = {
    cash: "CASH",
    cash_put_open: "PUT OPEN",
    shares: "SHARES",
    shares_call_open: "CALL OPEN",
  };

  const classes = {
    cash: "badge-blue",
    cash_put_open: "badge-yellow",
    shares: "badge-green",
    shares_call_open: "badge-yellow",
  };

  const label = labels[state] || state;
  const cls = classes[state] || "badge-gray";
  return `<span class="badge ${cls}">${label}</span>`;
}

/**
 * Render a risk level badge.
 */
function renderRiskBadge(level) {
  if (!level) return "\u2014";

  const classes = {
    LOW: "badge-green",
    MEDIUM: "badge-yellow",
    HIGH: "badge-red",
  };

  const cls = classes[level] || "badge-gray";
  return `<span class="badge ${cls}">${level}</span>`;
}

/**
 * Render price cell with market-open awareness.
 *
 * When market is open, shows current_price with a green dot indicator.
 * When market is closed, shows the previous close price with a "Close" label.
 */
function renderPriceCell(row) {
  if (row.current_price == null) return "\u2014";

  if (row.market_open) {
    // Market open: show live price with green dot indicator
    return `<span style="color: var(--color-success, #38a169);" title="Market open - live price">\u25CF</span> ${formatCurrency(row.current_price)}`;
  }

  // Market closed: show close price if available, otherwise current_price
  const price = row.close_price != null ? row.close_price : row.current_price;
  return `<span style="color: var(--color-muted, #999);" title="Market closed">${formatCurrency(price)}</span>`;
}

/**
 * Render day range (low - high) for the trading day.
 */
function renderDayRange(val) {
  if (!val) return "\u2014";
  return `${formatCurrency(val.low)} - ${formatCurrency(val.high)}`;
}

/**
 * Render context-sensitive action buttons for a wheel row.
 */
function renderActionButtons(row) {
  const div = document.createElement("div");
  div.className = "flex gap-2";

  const state = row.state;

  const openStates = ["cash_put_open", "shares_call_open"];
  const hasOpenTrade = openStates.includes(state);

  if (state === "cash") {
    div.appendChild(
      makeBtn("Recommend", () => navigate("recommend"))
    );
    div.appendChild(
      makeBtn("Record Put", () =>
        panel.open(
          "record-trade",
          { symbol: row.symbol, direction: "put", wheel_id: row.id, current_price: row.current_price },
          "Record Trade"
        )
      )
    );
  } else if (state === "shares") {
    div.appendChild(
      makeBtn("Recommend", () => navigate("recommend"))
    );
    div.appendChild(
      makeBtn("Record Call", () =>
        panel.open(
          "record-trade",
          { symbol: row.symbol, direction: "call", wheel_id: row.id, current_price: row.current_price },
          "Record Trade"
        )
      )
    );
  } else if (hasOpenTrade) {
    const pos = row._position;
    if (pos) {
      div.appendChild(
        makeBtn("Expire", () =>
          panel.open(
            "expire-trade",
            {
              symbol: row.symbol,
              direction: pos.direction,
              strike: pos.strike,
              expiration_date: pos.expiration_date,
              trade_id: pos.trade_id,
              wheel_id: row.id,
            },
            "Record Expiration"
          )
        )
      );
      div.appendChild(
        makeBtn("Close", () =>
          panel.open(
            "close-trade",
            {
              symbol: row.symbol,
              direction: pos.direction,
              strike: pos.strike,
              premium_collected: pos.premium_collected,
              trade_id: pos.trade_id,
              wheel_id: row.id,
            },
            "Close Trade Early"
          )
        )
      );
    }
  }

  // Edit button
  div.appendChild(
    makeBtn("Edit", () =>
      panel.open("edit-wheel", {
        id: row.id,
        symbol: row.symbol,
        capital_allocated: row.capital_allocated,
        profile: row.profile,
        is_active: row._wheel.is_active,
      }, `Edit ${row.symbol}`)
    )
  );

  // Delete button
  const deleteBtn = document.createElement("button");
  deleteBtn.className = "btn btn-sm";
  deleteBtn.textContent = "Delete";
  deleteBtn.style.color = "var(--color-danger, #e53e3e)";
  deleteBtn.style.fontSize = "10px";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete ${row.symbol} and all its trades? This cannot be undone.`)) return;
    deleteBtn.disabled = true;
    deleteBtn.textContent = "Deleting...";
    try {
      await api.deleteWheel(row.id);
      toast.success(`${row.symbol} deleted`);
      await refresh();
    } catch (err) {
      toast.error(err.message);
      deleteBtn.disabled = false;
      deleteBtn.textContent = "Delete";
    }
  });
  div.appendChild(deleteBtn);

  return div;
}

function makeBtn(label, onClick) {
  const btn = document.createElement("button");
  btn.className = "btn btn-sm";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}
