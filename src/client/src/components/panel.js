/**
 * Slide-out panel component.
 *
 * Provides a right-edge panel for forms (init wheel, record trade, etc.).
 * Supports pre-filling fields and form registration.
 */

const forms = {};
let currentFormId = null;
let isSubmitting = false;

/**
 * Register a form renderer for a given form ID.
 * @param {string} formId - Unique form identifier (e.g., "init-wheel", "record-trade").
 * @param {Function} renderFn - Function(container, prefillData, onSubmit, onCancel).
 */
export function registerForm(formId, renderFn) {
  forms[formId] = renderFn;
}

/**
 * Open the panel with a registered form.
 * @param {string} formId - The form to render.
 * @param {object} [prefillData] - Optional data to pre-fill form fields.
 * @param {string} [title] - Panel title override.
 */
export function open(formId, prefillData = {}, title = null) {
  const form = forms[formId];
  if (!form) {
    console.error(`No form registered with id: ${formId}`);
    return;
  }

  currentFormId = formId;
  isSubmitting = false;

  const header = document.getElementById("panel-header");
  const body = document.getElementById("panel-body");
  const footer = document.getElementById("panel-footer");
  const backdrop = document.getElementById("panel-backdrop");
  const panel = document.getElementById("panel");

  // Set title
  header.innerHTML = `
    <span>${title || formId.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</span>
    <button class="close-btn" id="panel-close-btn" style="background:none;border:none;color:var(--color-muted);cursor:pointer;font-size:18px;">&times;</button>
  `;

  // Clear and render form
  body.innerHTML = "";
  form(body, prefillData, handleSubmit, close);

  // Footer buttons
  footer.innerHTML = "";
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "btn";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", close);

  const submitBtn = document.createElement("button");
  submitBtn.className = "btn btn-primary";
  submitBtn.textContent = "Submit";
  submitBtn.id = "panel-submit-btn";
  submitBtn.addEventListener("click", () => {
    const formEl = body.querySelector("form");
    if (formEl) {
      formEl.requestSubmit();
    }
  });

  footer.appendChild(cancelBtn);
  footer.appendChild(submitBtn);

  // Show panel
  backdrop.classList.add("open");
  panel.classList.add("open");

  // Close on backdrop click
  backdrop.addEventListener("click", close, { once: true });

  // Close on Escape
  document.addEventListener("keydown", handleEscape);

  // Close button
  document.getElementById("panel-close-btn").addEventListener("click", close);
}

/**
 * Close the panel.
 */
export function close() {
  const backdrop = document.getElementById("panel-backdrop");
  const panel = document.getElementById("panel");

  backdrop.classList.remove("open");
  panel.classList.remove("open");

  currentFormId = null;
  isSubmitting = false;

  document.removeEventListener("keydown", handleEscape);
}

/**
 * Set the submit button to a loading state.
 * @param {boolean} loading
 */
export function setLoading(loading) {
  isSubmitting = loading;
  const submitBtn = document.getElementById("panel-submit-btn");
  if (submitBtn) {
    submitBtn.disabled = loading;
    submitBtn.textContent = loading ? "Submitting..." : "Submit";
  }
}

function handleSubmit(data) {
  // This is a placeholder — individual forms will override the submit handler
  // by calling the onSubmit callback passed to their render function.
}

function handleEscape(e) {
  if (e.key === "Escape") {
    close();
  }
}
