/**
 * Edit Wheel form for the slide-out panel.
 *
 * Allows editing capital allocated, profile, and active status
 * for an existing wheel position.
 */

import * as panel from "../components/panel.js";
import * as toast from "../components/toast.js";
import * as api from "../api.js";
import { refresh } from "../app.js";

/**
 * Register the edit-wheel form with the panel system.
 */
export function register() {
  panel.registerForm("edit-wheel", renderForm);
}

function renderForm(container, prefillData) {
  const form = document.createElement("form");
  form.innerHTML = `
    <div class="form-group">
      <label>Symbol</label>
      <input type="text" name="symbol" value="${prefillData.symbol || ""}" disabled />
    </div>
    <div class="form-group">
      <label>Capital Allocated ($)</label>
      <input type="number" name="capital_allocated" min="0" step="0.01" required
             value="${prefillData.capital_allocated || ""}" />
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
    <div class="form-group">
      <label>
        <input type="checkbox" name="is_active" ${prefillData.is_active ? "checked" : ""} />
        Active
      </label>
    </div>
  `;

  // Pre-select current profile
  const profileSelect = form.querySelector('select[name="profile"]');
  if (prefillData.profile) {
    profileSelect.value = prefillData.profile;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    panel.setLoading(true);

    const formData = new FormData(form);
    const capital = parseFloat(formData.get("capital_allocated"));

    if (isNaN(capital) || capital <= 0) {
      toast.error("Capital must be a positive number");
      panel.setLoading(false);
      return;
    }

    const payload = {
      capital_allocated: capital,
      profile: formData.get("profile"),
      is_active: form.querySelector('input[name="is_active"]').checked,
    };

    try {
      await api.updateWheel(prefillData.id, payload);
      toast.success(`${prefillData.symbol} updated`);
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
