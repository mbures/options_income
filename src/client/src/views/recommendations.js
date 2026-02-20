/**
 * Recommendations view.
 *
 * Displays top candidates per eligible wheel position with
 * one-click trade recording.
 */

import { createTable } from "../components/table.js";
import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { getState } from "../app.js";
import { formatCurrency, formatPercent, formatNumber, formatDate } from "../format.js";

/**
 * Render the recommendations view.
 * @param {HTMLElement} container
 * @param {object} state
 */
export function render(container, state) {
  container.innerHTML = "";

  const wheels = (state.wheels || []).filter((w) => w.is_active);
  const eligibleStates = ["cash", "shares"];
  const eligible = wheels.filter((w) => eligibleStates.includes(w.state));

  // Header
  const header = document.createElement("div");
  header.className = "flex items-center justify-between mb-4";
  header.innerHTML = `
    <h1 style="font-size: 18px; font-weight: 600;">Recommendations</h1>
    <button class="btn btn-sm" id="btn-refresh-all">Refresh All</button>
  `;
  container.appendChild(header);

  // Empty states
  if (wheels.length === 0) {
    container.innerHTML += `
      <div style="padding: 40px; text-align: center; color: var(--color-muted);">
        No wheels configured. Create a position from the Dashboard.
      </div>
    `;
    return;
  }

  if (eligible.length === 0) {
    container.innerHTML += `
      <div style="padding: 40px; text-align: center; color: var(--color-muted);">
        All positions have open trades. No recommendations available.
      </div>
    `;
    return;
  }

  // Recommendation blocks container
  const blocksContainer = document.createElement("div");
  blocksContainer.id = "rec-blocks";
  container.appendChild(blocksContainer);

  // Load recommendations for each eligible wheel
  for (const wheel of eligible) {
    const block = createBlock(wheel);
    blocksContainer.appendChild(block);
    loadRecommendation(block, wheel, state.config.maxDte);
  }

  // Refresh All button
  header.querySelector("#btn-refresh-all").addEventListener("click", () => {
    const blocks = blocksContainer.querySelectorAll(".rec-block");
    let i = 0;
    for (const wheel of eligible) {
      const block = blocks[i];
      if (block) loadRecommendation(block, wheel, state.config.maxDte);
      i++;
    }
  });
}

function createBlock(wheel) {
  const block = document.createElement("div");
  block.className = "rec-block";
  block.style.marginBottom = "24px";
  block.style.backgroundColor = "var(--color-surface)";
  block.style.border = "1px solid var(--color-border)";
  block.style.borderRadius = "6px";
  block.style.padding = "16px";

  const stateLabel = wheel.state === "cash" ? "CASH" : "SHARES";
  const stateCls = wheel.state === "cash" ? "badge-blue" : "badge-green";

  block.innerHTML = `
    <div class="flex items-center justify-between" style="margin-bottom: 12px;">
      <div class="flex items-center gap-2">
        <span style="font-size: 15px; font-weight: 600;">${wheel.symbol}</span>
        <span class="badge ${stateCls}">${stateLabel}</span>
        <span class="text-muted" style="font-size: 12px;">${wheel.profile}</span>
      </div>
      <button class="btn btn-sm rec-refresh-btn">Refresh</button>
    </div>
    <div class="rec-content">
      <div style="padding: 16px; text-align: center; color: var(--color-muted);">
        <span class="spinner"></span> Loading...
      </div>
    </div>
  `;

  block.querySelector(".rec-refresh-btn").addEventListener("click", () => {
    const state = getState();
    loadRecommendation(block, wheel, state.config.maxDte);
  });

  return block;
}

async function loadRecommendation(block, wheel, maxDte) {
  const content = block.querySelector(".rec-content");
  content.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--color-muted);"><span class="spinner"></span> Loading...</div>`;

  try {
    const rec = await api.getRecommendation(wheel.id, maxDte);
    renderRecommendation(content, rec, wheel);
  } catch (err) {
    content.innerHTML = `<div style="padding: 16px; color: var(--color-error);">${err.message}</div>`;
  }
}

function renderRecommendation(container, rec, wheel) {
  container.innerHTML = "";

  // The API may return a single recommendation or candidates array
  const candidates = rec.candidates || [rec];

  if (candidates.length === 0) {
    container.innerHTML = `<div style="padding: 16px; color: var(--color-muted);">No candidates found.</div>`;
    return;
  }

  const tableData = candidates.map((c, i) => ({
    rank: i + 1,
    strike: c.strike,
    expiration: c.expiration_date,
    dte: c.dte,
    premium_per_share: c.premium_per_share,
    total_premium: c.total_premium,
    contracts: c.contracts,
    p_itm: c.p_itm,
    sigma: c.sigma_distance,
    annualized_yield: c.annualized_yield_pct,
    bias_score: c.bias_score,
    _candidate: c,
  }));

  const columns = [
    { key: "rank", label: "#", sortable: false },
    {
      key: "strike",
      label: "Strike",
      sortable: false,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    {
      key: "expiration",
      label: "Exp",
      sortable: false,
      render: (val) => formatDate(val),
    },
    { key: "dte", label: "DTE", sortable: false, align: "right" },
    {
      key: "premium_per_share",
      label: "Prem/Sh",
      sortable: false,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    {
      key: "total_premium",
      label: "Total",
      sortable: false,
      align: "right",
      render: (val) => formatCurrency(val),
    },
    { key: "contracts", label: "Ct", sortable: false, align: "right" },
    {
      key: "p_itm",
      label: "P(ITM)",
      sortable: false,
      align: "right",
      render: (val) => formatPercent(val, true),
    },
    {
      key: "sigma",
      label: "Sigma",
      sortable: false,
      align: "right",
      render: (val) => formatNumber(val),
    },
    {
      key: "annualized_yield",
      label: "Yield",
      sortable: false,
      align: "right",
      render: (val) => formatPercent(val, true),
    },
    {
      key: "bias_score",
      label: "Bias",
      sortable: false,
      align: "right",
      render: (val) => formatNumber(val),
    },
    {
      key: "actions",
      label: "",
      sortable: false,
      render: (_val, row) => {
        const btn = document.createElement("button");
        btn.className = "btn btn-sm btn-primary";
        btn.textContent = "Record";
        btn.addEventListener("click", () => {
          const c = row._candidate;
          panel.open(
            "record-trade",
            {
              symbol: c.symbol || wheel.symbol,
              direction: c.direction || (wheel.state === "cash" ? "put" : "call"),
              strike: c.strike,
              expiration_date: c.expiration_date,
              premium_per_share: c.premium_per_share,
              contracts: c.contracts,
              wheel_id: wheel.id,
              current_price: rec.current_price,
              p_itm: c.p_itm,
            },
            "Record Trade"
          );
        });
        return btn;
      },
    },
  ];

  const table = createTable({ columns, data: tableData });
  container.appendChild(table);

  // Warnings
  const warnings = rec.warnings || (candidates[0] && candidates[0].warnings) || [];
  if (warnings.length > 0) {
    const warningDiv = document.createElement("div");
    warningDiv.style.marginTop = "8px";
    warningDiv.style.fontSize = "12px";
    warningDiv.style.color = "var(--color-warning)";
    warningDiv.innerHTML = warnings.map((w) => `&#9888; ${w}`).join("<br/>");
    container.appendChild(warningDiv);
  }
}
