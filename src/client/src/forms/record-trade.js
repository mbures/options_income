/**
 * Record Trade form for the slide-out panel.
 *
 * Records a new option trade (put or call) against a wheel position.
 * Supports pre-filling from recommendation data.
 */

import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh, getState } from "../app.js";
import { formatCurrency, formatPercent } from "../format.js";

/**
 * Register the record-trade form with the panel system.
 */
export function register() {
  panel.registerForm("record-trade", renderForm);
}

function renderForm(container, prefillData, onSubmit, onCancel) {
  const data = prefillData || {};

  // Store prefill-only data for metrics
  const currentPrice = data.current_price || null;
  const pItm = data.p_itm || null;

  const form = document.createElement("form");
  form.innerHTML = `
    <div class="form-group">
      <label>Symbol</label>
      <input type="text" name="symbol" value="${data.symbol || ""}" ${data.symbol ? "readonly" : ""} required style="text-transform: uppercase;" />
    </div>
    <div class="form-group">
      <label>Direction</label>
      <div class="radio-group">
        <label>
          <input type="radio" name="direction" value="put" ${data.direction === "call" ? "" : "checked"} />
          Put
        </label>
        <label>
          <input type="radio" name="direction" value="call" ${data.direction === "call" ? "checked" : ""} />
          Call
        </label>
      </div>
    </div>
    <div class="form-group">
      <label>Strike Price ($)</label>
      <input type="number" name="strike" min="0" step="0.01" required value="${data.strike || ""}" />
    </div>
    <div class="form-group">
      <label>Expiration Date</label>
      <input type="date" name="expiration_date" required value="${data.expiration_date || data.expiration || ""}" />
    </div>
    <div class="form-group">
      <label>Premium per Share ($)</label>
      <input type="number" name="premium_per_share" min="0" step="0.01" required value="${data.premium_per_share || ""}" />
    </div>
    <div class="form-group">
      <label>Contracts</label>
      <input type="number" name="contracts" min="1" step="1" required value="${data.contracts || 1}" />
    </div>
    <hr style="border-color: var(--color-border); margin: 16px 0;" />
    <div id="trade-metrics" style="display: none;">
      <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--color-text);">Trade Metrics</div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; font-size: 12px;">
        <div style="color: var(--color-muted);">Total Premium</div>
        <div style="text-align: right; font-weight: 500;" id="metric-total-premium">\u2014</div>
        <div style="color: var(--color-muted);">Collateral Required</div>
        <div style="text-align: right; font-weight: 500;" id="metric-collateral">\u2014</div>
        <div style="color: var(--color-muted);">Breakeven Price</div>
        <div style="text-align: right; font-weight: 500;" id="metric-breakeven">\u2014</div>
        <div style="color: var(--color-muted);">DTE</div>
        <div style="text-align: right; font-weight: 500;" id="metric-dte">\u2014</div>
        <div style="color: var(--color-muted);">Moneyness</div>
        <div style="text-align: right; font-weight: 500;" id="metric-moneyness">\u2014</div>
        <div style="color: var(--color-muted);">Annualized Return</div>
        <div style="text-align: right; font-weight: 500;" id="metric-annualized">\u2014</div>
        <div style="color: var(--color-muted);">P(ITM)</div>
        <div style="text-align: right; font-weight: 500;" id="metric-pitm">\u2014</div>
      </div>
    </div>
  `;

  function updateMetrics() {
    const metricsDiv = form.querySelector("#trade-metrics");
    const strike = parseFloat(form.querySelector('input[name="strike"]').value);
    const premium = parseFloat(form.querySelector('input[name="premium_per_share"]').value);
    const contracts = parseInt(form.querySelector('input[name="contracts"]').value, 10);
    const expDate = form.querySelector('input[name="expiration_date"]').value;
    const direction = form.querySelector('input[name="direction"]:checked')?.value || "put";

    // Show metrics section once minimum fields are filled
    const hasMinimum = !isNaN(strike) && strike > 0 && !isNaN(premium) && premium > 0 && !isNaN(contracts) && contracts >= 1;
    metricsDiv.style.display = hasMinimum ? "block" : "none";
    if (!hasMinimum) return;

    // Total Premium
    const totalPremium = premium * contracts * 100;
    form.querySelector("#metric-total-premium").textContent = formatCurrency(totalPremium);

    // Collateral Required
    if (direction === "put") {
      const collateral = strike * contracts * 100;
      form.querySelector("#metric-collateral").textContent = formatCurrency(collateral);
    } else {
      form.querySelector("#metric-collateral").textContent = "Covered";
    }

    // Breakeven Price
    const breakeven = direction === "put" ? strike - premium : strike + premium;
    form.querySelector("#metric-breakeven").textContent = formatCurrency(breakeven);

    // DTE
    if (expDate) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const exp = new Date(expDate + "T00:00:00");
      const diffMs = exp - today;
      const dte = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
      form.querySelector("#metric-dte").textContent = dte >= 0 ? String(dte) : "Expired";

      // Annualized Return (only for puts with valid DTE)
      if (direction === "put" && dte > 0) {
        const collateral = strike * contracts * 100;
        const annualized = (totalPremium / collateral) * (365 / dte) * 100;
        form.querySelector("#metric-annualized").textContent = formatPercent(annualized, true);
      } else {
        form.querySelector("#metric-annualized").textContent = "\u2014";
      }
    } else {
      form.querySelector("#metric-dte").textContent = "\u2014";
      form.querySelector("#metric-annualized").textContent = "\u2014";
    }

    // Moneyness (requires current_price from prefill)
    if (currentPrice != null && currentPrice > 0) {
      const moneyness = direction === "put"
        ? ((strike - currentPrice) / currentPrice) * 100
        : ((currentPrice - strike) / currentPrice) * 100;
      form.querySelector("#metric-moneyness").textContent = formatPercent(moneyness, true);
    } else {
      form.querySelector("#metric-moneyness").textContent = "\u2014";
    }

    // P(ITM) (direct pass-through from prefill)
    if (pItm != null) {
      form.querySelector("#metric-pitm").textContent = formatPercent(pItm, true);
    } else {
      form.querySelector("#metric-pitm").textContent = "\u2014";
    }
  }

  // Wire up reactive listeners
  const inputFields = ["strike", "premium_per_share", "contracts", "expiration_date"];
  for (const name of inputFields) {
    const el = form.querySelector(`input[name="${name}"]`);
    if (el) el.addEventListener("input", updateMetrics);
  }
  const radios = form.querySelectorAll('input[name="direction"]');
  for (const radio of radios) {
    radio.addEventListener("change", updateMetrics);
  }

  // Initial metrics calculation if prefilled
  updateMetrics();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    panel.setLoading(true);

    const formData = new FormData(form);
    const symbol = formData.get("symbol").toUpperCase().trim();
    const direction = formData.get("direction");
    const strike = parseFloat(formData.get("strike"));
    const expirationDate = formData.get("expiration_date");
    const premiumPerShare = parseFloat(formData.get("premium_per_share"));
    const contracts = parseInt(formData.get("contracts"), 10);

    // Validation
    if (!symbol) {
      toast.error("Symbol is required");
      panel.setLoading(false);
      return;
    }
    if (isNaN(strike) || strike <= 0) {
      toast.error("Strike must be a positive number");
      panel.setLoading(false);
      return;
    }
    if (!expirationDate) {
      toast.error("Expiration date is required");
      panel.setLoading(false);
      return;
    }
    if (isNaN(premiumPerShare) || premiumPerShare <= 0) {
      toast.error("Premium must be a positive number");
      panel.setLoading(false);
      return;
    }
    if (isNaN(contracts) || contracts < 1) {
      toast.error("Contracts must be at least 1");
      panel.setLoading(false);
      return;
    }

    // Resolve wheel ID
    let wheelId = data.wheel_id;
    if (!wheelId) {
      const state = getState();
      const wheel = (state.wheels || []).find(
        (w) => w.symbol === symbol && w.is_active
      );
      if (!wheel) {
        toast.error(`No active wheel found for ${symbol}`);
        panel.setLoading(false);
        return;
      }
      wheelId = wheel.id;
    }

    const payload = {
      direction,
      strike,
      expiration_date: expirationDate,
      premium_per_share: premiumPerShare,
      contracts,
    };

    try {
      await api.recordTrade(wheelId, payload);
      toast.success(
        `Recorded: SELL ${direction.toUpperCase()} ${symbol} $${strike.toFixed(2)} exp ${expirationDate} @ $${premiumPerShare.toFixed(2)}`
      );
      panel.close();
      await refresh();
    } catch (err) {
      toast.error(err.message);
    } finally {
      panel.setLoading(false);
    }
  });

  container.appendChild(form);
}
