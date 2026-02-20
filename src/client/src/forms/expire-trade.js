/**
 * Expire Trade form for the slide-out panel.
 *
 * Records the stock price at expiration to determine trade outcome.
 */

import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh } from "../app.js";

/**
 * Register the expire-trade form with the panel system.
 */
export function register() {
  panel.registerForm("expire-trade", renderForm);
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
      <label>Expiration Date</label>
      <input type="text" value="${data.expiration_date || ""}" readonly />
    </div>
    <hr style="border-color: var(--color-border); margin: 16px 0;" />
    <div class="form-group">
      <label>Stock Price at Expiration ($)</label>
      <input type="number" name="price_at_expiry" min="0" step="0.01" required autofocus />
    </div>
  `;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    panel.setLoading(true);

    const priceAtExpiry = parseFloat(
      form.querySelector('input[name="price_at_expiry"]').value
    );

    if (isNaN(priceAtExpiry) || priceAtExpiry <= 0) {
      toast.error("Price must be a positive number");
      panel.setLoading(false);
      return;
    }

    if (!data.trade_id) {
      toast.error("Trade ID not available");
      panel.setLoading(false);
      return;
    }

    try {
      const result = await api.expireTrade(data.trade_id, priceAtExpiry);
      const outcome = result.outcome || "unknown";
      const symbol = data.symbol || "";
      const direction = (data.direction || "").toLowerCase();

      let message;
      if (outcome === "expired_worthless") {
        message = `${symbol} ${direction} expired worthless`;
      } else if (outcome === "assigned") {
        message = `${symbol} ${direction} assigned at $${data.strike.toFixed(2)}`;
      } else if (outcome === "called_away") {
        message = `${symbol} shares called away at $${data.strike.toFixed(2)}`;
      } else {
        message = `${symbol} ${direction} expired: ${outcome}`;
      }

      toast.success(message);
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
