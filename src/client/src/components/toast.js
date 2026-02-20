/**
 * Toast notification system.
 *
 * Provides success, error, and warning notifications that appear
 * in the top-right corner and auto-dismiss (except errors).
 */

const AUTO_DISMISS_MS = 5000;

/**
 * Show a success toast. Auto-dismisses after 5 seconds.
 * @param {string} message
 */
export function success(message) {
  show(message, "toast-success", true);
}

/**
 * Show an error toast. Persists until manually dismissed.
 * @param {string} message
 */
export function error(message) {
  show(message, "toast-error", false);
}

/**
 * Show a warning toast. Auto-dismisses after 5 seconds.
 * @param {string} message
 */
export function warning(message) {
  show(message, "toast-warning", true);
}

function show(message, className, autoDismiss) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${className}`;

  const text = document.createElement("span");
  text.textContent = message;

  const closeBtn = document.createElement("button");
  closeBtn.className = "close-btn";
  closeBtn.textContent = "\u00D7";
  closeBtn.addEventListener("click", () => dismiss(toast));

  toast.appendChild(text);
  toast.appendChild(closeBtn);
  container.appendChild(toast);

  if (autoDismiss) {
    setTimeout(() => dismiss(toast), AUTO_DISMISS_MS);
  }
}

function dismiss(toast) {
  toast.style.animation = "toast-out 0.2s ease-in forwards";
  setTimeout(() => {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 200);
}
