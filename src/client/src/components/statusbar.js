/**
 * Status bar component.
 *
 * Shows connection status, last refresh time, and countdown to next refresh.
 */

let countdownInterval = null;
let secondsRemaining = 0;

/**
 * Render the status bar.
 * @param {HTMLElement} container - The statusbar DOM element.
 * @param {object} state - Application state with ui.connected, ui.lastRefresh, config.refreshInterval.
 */
export function render(container, state) {
  const connected = state.ui.connected;
  const lastRefresh = state.ui.lastRefresh;
  const intervalMs = state.config.refreshInterval;

  const dotClass = connected ? "connected" : "disconnected";
  const statusText = connected ? "Connected" : "Disconnected";

  let refreshText = "";
  if (lastRefresh) {
    const time = new Date(lastRefresh).toLocaleTimeString();
    refreshText = `Last refresh: ${time}`;
  }

  let countdownText = "";
  if (connected && secondsRemaining > 0) {
    const min = Math.floor(secondsRemaining / 60);
    const sec = secondsRemaining % 60;
    countdownText = `Next: ${min}m ${sec.toString().padStart(2, "0")}s`;
  }

  container.innerHTML = `
    <span class="status-dot ${dotClass}"></span>
    <span style="margin-right: 16px;">${statusText}</span>
    <span style="margin-right: 16px;">${refreshText}</span>
    <span>${countdownText}</span>
  `;
}

/**
 * Start the countdown timer for the next refresh.
 * @param {number} intervalMs - Refresh interval in milliseconds.
 * @param {Function} onTick - Called every second with the status bar container.
 */
export function startCountdown(intervalMs, onTick) {
  stopCountdown();
  secondsRemaining = Math.floor(intervalMs / 1000);

  countdownInterval = setInterval(() => {
    secondsRemaining--;
    if (secondsRemaining <= 0) {
      secondsRemaining = Math.floor(intervalMs / 1000);
    }
    if (onTick) {
      onTick();
    }
  }, 1000);
}

/**
 * Reset the countdown to the full interval.
 * @param {number} intervalMs - Refresh interval in milliseconds.
 */
export function resetCountdown(intervalMs) {
  secondsRemaining = Math.floor(intervalMs / 1000);
}

/**
 * Stop the countdown timer.
 */
export function stopCountdown() {
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
}
