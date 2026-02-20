/**
 * Close Trade Early form for the slide-out panel.
 *
 * Closes an open trade by entering the buy-back price.
 */

import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh } from "../app.js";
import { formatCurrency } from "../format.js";

/**
 * Register the close-trade form with the panel system.
 */
export function register() {
  panel.registerForm("close-trade", renderForm);
}

function renderForm(container, prefillData, onSubmit, onCancel) {
  const data = prefillData || {};

  const form = document.createElement("form");
  form.innerHTML = `
    <div class="form-group">
      <label>Symbol</label>
      <input type="text" value="${data.symbol || ""}" readonly />
    </div>
    <div class="form-group">
      <label>Direction</label>
      <input type="text" value="${(data.direction || "").toUpperCase()}" readonly />
    </div>
    <div class="form-group">
      <label>Strike</label>
      <input type="text" value="$${data.strike ? data.strike.toFixed(2) : ""}" readonly />
    </div>
    <div class="form-group">
      <label>Premium Collected</label>
      <input type="text" value="${formatCurrency(data.premium_collected)}" readonly />
    </div>
    <hr style="border-color: var(--color-border); margin: 16px 0;" />
    <div class="form-group">
      <label>Buy-back Price per Share ($)</label>
      <input type="number" name="close_price" min="0" step="0.01" required autofocus />
    </div>
  `;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    panel.setLoading(true);

    const closePrice = parseFloat(
      form.querySelector('input[name="close_price"]').value
    );

    if (isNaN(closePrice) || closePrice <= 0) {
      toast.error("Buy-back price must be a positive number");
      panel.setLoading(false);
      return;
    }

    if (!data.trade_id) {
      toast.error("Trade ID not available");
      panel.setLoading(false);
      return;
    }

    try {
      await api.closeTrade(data.trade_id, closePrice);
      const symbol = data.symbol || "";
      const direction = (data.direction || "").toLowerCase();
      toast.success(`Closed ${symbol} ${direction}: buy-back @ $${closePrice.toFixed(2)}`);
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
