/**
 * Init Wheel form for the slide-out panel.
 *
 * Creates a new wheel position with symbol, capital/shares, and profile.
 */

import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh, getState } from "../app.js";

/**
 * Register the init-wheel form with the panel system.
 */
export function register() {
  panel.registerForm("init-wheel", renderForm);
}

function renderForm(container, prefillData, onSubmit, onCancel) {
  const form = document.createElement("form");
  form.innerHTML = `
    <div class="form-group">
      <label>Symbol</label>
      <input type="text" name="symbol" required placeholder="AAPL" style="text-transform: uppercase;" />
    </div>
    <div class="form-group">
      <label>Start With</label>
      <div class="radio-group">
        <label>
          <input type="radio" name="start_state" value="cash" checked />
          Cash — Sell Puts
        </label>
        <label>
          <input type="radio" name="start_state" value="shares" />
          Shares — Sell Calls
        </label>
      </div>
    </div>
    <div class="form-group" id="fg-capital">
      <label>Capital ($)</label>
      <input type="number" name="capital" min="0" step="0.01" required placeholder="10000" />
    </div>
    <div class="form-group" id="fg-shares" style="display: none;">
      <label>Number of Shares</label>
      <input type="number" name="shares" min="1" step="1" placeholder="100" />
    </div>
    <div class="form-group" id="fg-cost-basis" style="display: none;">
      <label>Cost Basis (per share)</label>
      <input type="number" name="cost_basis" min="0" step="0.01" placeholder="150.00" />
    </div>
    <div class="form-group">
      <label>Profile</label>
      <select name="profile">
        <option value="conservative">Conservative</option>
        <option value="moderate">Moderate</option>
        <option value="aggressive">Aggressive</option>
        <option value="defensive">Defensive</option>
      </select>
    </div>
  `;

  // Toggle cash/shares fields
  const radios = form.querySelectorAll('input[name="start_state"]');
  const capitalGroup = form.querySelector("#fg-capital");
  const sharesGroup = form.querySelector("#fg-shares");
  const costBasisGroup = form.querySelector("#fg-cost-basis");
  const capitalInput = form.querySelector('input[name="capital"]');
  const sharesInput = form.querySelector('input[name="shares"]');
  const costBasisInput = form.querySelector('input[name="cost_basis"]');

  for (const radio of radios) {
    radio.addEventListener("change", () => {
      const isCash = form.querySelector('input[name="start_state"]:checked').value === "cash";
      capitalGroup.style.display = isCash ? "" : "none";
      sharesGroup.style.display = isCash ? "none" : "";
      costBasisGroup.style.display = isCash ? "none" : "";
      capitalInput.required = isCash;
      sharesInput.required = !isCash;
      costBasisInput.required = !isCash;
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    panel.setLoading(true);

    const state = getState();
    const portfolioId = state.portfolioId;
    const formData = new FormData(form);
    const symbol = formData.get("symbol").toUpperCase().trim();
    const startState = formData.get("start_state");
    const profile = formData.get("profile");

    if (!symbol) {
      toast.error("Symbol is required");
      panel.setLoading(false);
      return;
    }

    const payload = { symbol, profile };

    if (startState === "cash") {
      const capital = parseFloat(formData.get("capital"));
      if (isNaN(capital) || capital <= 0) {
        toast.error("Capital must be a positive number");
        panel.setLoading(false);
        return;
      }
      payload.capital_allocated = capital;
    } else {
      const shares = parseInt(formData.get("shares"), 10);
      const costBasis = parseFloat(formData.get("cost_basis"));
      if (isNaN(shares) || shares <= 0) {
        toast.error("Shares must be a positive number");
        panel.setLoading(false);
        return;
      }
      if (isNaN(costBasis) || costBasis <= 0) {
        toast.error("Cost basis must be a positive number");
        panel.setLoading(false);
        return;
      }
      payload.shares = shares;
      payload.cost_basis = costBasis;
      payload.state = "shares";
    }

    try {
      await api.createWheel(portfolioId, payload);
      toast.success(`${symbol} wheel created`);
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
