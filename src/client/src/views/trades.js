/**
 * Trades view.
 *
 * Shows trade history for a selected symbol with outcome badges
 * and inline actions for open trades.
 */

import { createTable } from "../components/table.js";
import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { formatCurrency, formatDate } from "../format.js";

let selectedWheelId = null;
let tradesCache = [];

/**
 * Render the trades view.
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
  title.textContent = "Trade History";

  // Symbol selector
  const selectorDiv = document.createElement("div");
  selectorDiv.className = "flex items-center gap-2";

  const select = document.createElement("select");
  select.className = "btn";
  select.style.minWidth = "120px";

  if (wheels.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "No wheels";
    opt.disabled = true;
    select.appendChild(opt);
  } else {
    for (const w of wheels) {
      const opt = document.createElement("option");
      opt.value = w.id;
      opt.textContent = w.symbol;
      if (selectedWheelId === w.id) opt.selected = true;
      select.appendChild(opt);
    }
    // Default to first if none selected
    if (!selectedWheelId && wheels.length > 0) {
      selectedWheelId = wheels[0].id;
    }
  }

  selectorDiv.appendChild(select);
  header.appendChild(title);
  header.appendChild(selectorDiv);
  container.appendChild(header);

  // Table container
  const tableContainer = document.createElement("div");
  tableContainer.id = "trades-table-container";
  container.appendChild(tableContainer);

  // Load trades for selected wheel
  if (selectedWheelId) {
    loadTrades(tableContainer, selectedWheelId);
  }

  // On symbol change
  select.addEventListener("change", (e) => {
    selectedWheelId = parseInt(e.target.value, 10);
    loadTrades(tableContainer, selectedWheelId);
  });
}

async function loadTrades(container, wheelId) {
  container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading trades...</div>`;

  try {
    const trades = await api.listTrades(wheelId);
    tradesCache = trades || [];
    renderTradesTable(container, tradesCache);
  } catch (err) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--color-error);">Failed to load trades: ${err.message}</div>`;
  }
}

function renderTradesTable(container, trades) {
  container.innerHTML = "";

  if (trades.length === 0) {
    container.innerHTML = `<div style="padding: 40px; text-align: center; color: var(--color-muted);">No trades recorded for this symbol.</div>`;
    return;
  }

  const columns = [
    {
      key: "opened_at",
      label: "Date",
      sortable: true,
      render: (val) => formatDate(val),
    },
    {
      key: "direction",
      label: "Direction",
      sortable: true,
      render: (val) => (val || "").toUpperCase(),
    },
    {
      key: "strike",
      label: "Strike",
      sortable: true,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    {
      key: "expiration_date",
      label: "Expiration",
      sortable: true,
      render: (val) => formatDate(val),
    },
    {
      key: "total_premium",
      label: "Premium",
      sortable: true,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    {
      key: "outcome",
      label: "Outcome",
      sortable: true,
      render: (val) => renderOutcomeBadge(val),
    },
    {
      key: "close_price",
      label: "Net",
      sortable: false,
      align: "right",
      render: (val, row) => {
        if (row.outcome === "open") return "\u2014";
        if (row.close_price != null) {
          const net =
            row.total_premium - row.close_price * row.contracts * 100;
          return formatCurrency(net);
        }
        return formatCurrency(row.total_premium);
      },
    },
    {
      key: "actions",
      label: "",
      sortable: false,
      render: (_val, row) => {
        if (row.outcome !== "open") return "";
        return renderTradeActions(row);
      },
    },
  ];

  const table = createTable({
    columns,
    data: trades,
    sortKey: "opened_at",
    sortDir: "desc",
  });

  container.appendChild(table);
}

function renderOutcomeBadge(outcome) {
  const badges = {
    open: { label: "OPEN", cls: "badge-blue" },
    expired_worthless: { label: "WIN", cls: "badge-green" },
    assigned: { label: "ASSIGNED", cls: "badge-yellow" },
    called_away: { label: "CALLED", cls: "badge-blue" },
    closed: { label: "CLOSED", cls: "badge-gray" },
  };

  const badge = badges[outcome] || { label: outcome || "?", cls: "badge-gray" };
  return `<span class="badge ${badge.cls}">${badge.label}</span>`;
}

function renderTradeActions(row) {
  const div = document.createElement("div");
  div.className = "flex gap-2";

  const expireBtn = document.createElement("button");
  expireBtn.className = "btn btn-sm";
  expireBtn.textContent = "Expire";
  expireBtn.addEventListener("click", () => {
    panel.open(
      "expire-trade",
      {
        symbol: row.symbol,
        direction: row.direction,
        strike: row.strike,
        expiration_date: row.expiration_date,
        trade_id: row.id,
        wheel_id: row.wheel_id,
      },
      "Record Expiration"
    );
  });

  const closeBtn = document.createElement("button");
  closeBtn.className = "btn btn-sm";
  closeBtn.textContent = "Close";
  closeBtn.addEventListener("click", () => {
    panel.open(
      "close-trade",
      {
        symbol: row.symbol,
        direction: row.direction,
        strike: row.strike,
        premium_collected: row.total_premium,
        trade_id: row.id,
        wheel_id: row.wheel_id,
      },
      "Close Trade Early"
    );
  });

  div.appendChild(expireBtn);
  div.appendChild(closeBtn);
  return div;
}
