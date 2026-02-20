/**
 * Application state, routing, and initialization.
 *
 * Manages the global state, view navigation, auto-refresh loop,
 * and coordinates between components.
 */

import * as sidebar from "./components/sidebar.js";
import * as statusbar from "./components/statusbar.js";
import * as toast from "./components/toast.js";
import * as api from "./api.js";

// Application state
const state = {
  portfolioId: null,
  portfolio: null,
  portfolios: [],
  wheels: [],
  positions: [],
  config: {
    refreshInterval: 1800000, // 30 minutes
    maxDte: 14,
  },
  opportunityCount: 0,
  ui: {
    activeView: "dashboard",
    panelOpen: false,
    panelContent: null,
    lastRefresh: null,
    connected: false,
    loading: false,
  },
};

// View renderers (lazy-loaded)
const views = {};
let refreshTimer = null;

/**
 * Get current application state (read-only copy).
 * @returns {object}
 */
export function getState() {
  return state;
}

/**
 * Update state and re-render affected components.
 * @param {object} updates - Partial state to merge.
 */
export function setState(updates) {
  // Merge top-level keys
  for (const key of Object.keys(updates)) {
    if (
      typeof updates[key] === "object" &&
      !Array.isArray(updates[key]) &&
      updates[key] !== null &&
      state[key] !== null &&
      typeof state[key] === "object" &&
      !Array.isArray(state[key])
    ) {
      state[key] = { ...state[key], ...updates[key] };
    } else {
      state[key] = updates[key];
    }
  }

  // Re-render active view
  renderActiveView();

  // Always update status bar
  renderStatusBar();
}

/**
 * Navigate to a different view.
 * @param {string} viewName
 */
export function navigate(viewName) {
  state.ui.activeView = viewName;
  sidebar.setActive(viewName);
  renderActiveView();
}

/**
 * Initialize the application.
 */
export async function init() {
  const sidebarEl = document.getElementById("sidebar");

  // Render sidebar
  sidebar.render(sidebarEl, navigate);

  // Show loading state
  showLoading("Connecting to server...");

  // Check health
  try {
    await api.checkHealth();
    state.ui.connected = true;
  } catch {
    state.ui.connected = false;
    renderStatusBar();
    showDisconnected();
    return;
  }

  renderStatusBar();
  showLoading("Loading portfolio data...");

  // Load portfolio data
  try {
    const portfolios = await api.listPortfolios();
    state.portfolios = portfolios || [];

    if (state.portfolios.length > 0) {
      state.portfolioId = state.portfolios[0].id;
      state.portfolio = state.portfolios[0];

      // Render portfolio selector if multiple portfolios
      sidebar.renderPortfolioSelector(
        state.portfolios,
        state.portfolioId,
        switchPortfolio
      );

      // Load wheels and positions
      await loadPortfolioData();
    }
  } catch (err) {
    toast.error(`Failed to load data: ${err.message}`);
  }

  state.ui.lastRefresh = new Date().toISOString();

  // Render the default view
  renderActiveView();
  renderStatusBar();

  // Start auto-refresh
  startRefreshLoop();
}

/**
 * Register a view renderer.
 * @param {string} viewName
 * @param {object} viewModule - Module with render(container, state) function.
 */
export function registerView(viewName, viewModule) {
  views[viewName] = viewModule;
}

/**
 * Force a manual data refresh.
 */
export async function refresh() {
  try {
    await api.checkHealth();
    state.ui.connected = true;
  } catch {
    state.ui.connected = false;
  }

  if (state.ui.connected && state.portfolioId) {
    try {
      await loadPortfolioData();
    } catch (err) {
      toast.error(`Refresh failed: ${err.message}`);
    }
  }

  state.ui.lastRefresh = new Date().toISOString();
  statusbar.resetCountdown(state.config.refreshInterval);
  renderActiveView();
  renderStatusBar();
}

// Internal functions

/**
 * Load wheels and positions for the current portfolio.
 */
async function loadPortfolioData() {
  const wheels = await api.listWheels(state.portfolioId);
  state.wheels = wheels || [];

  try {
    const positions = await api.getPortfolioPositions(state.portfolioId);
    state.positions = positions || [];
  } catch {
    state.positions = [];
  }

  // Fetch unread opportunity count for badge
  try {
    const countData = await api.getOpportunityCount();
    state.opportunityCount = countData.unread_count || 0;
    sidebar.setBadge("opportunities", state.opportunityCount);
  } catch {
    // Non-critical, ignore errors
  }
}

/**
 * Switch to a different portfolio.
 * @param {string} portfolioId
 */
async function switchPortfolio(portfolioId) {
  state.portfolioId = portfolioId;
  state.portfolio =
    state.portfolios.find((p) => p.id === portfolioId) || null;

  showLoading("Switching portfolio...");

  try {
    await loadPortfolioData();
  } catch (err) {
    toast.error(`Failed to load portfolio: ${err.message}`);
  }

  state.ui.lastRefresh = new Date().toISOString();
  renderActiveView();
  renderStatusBar();
}

function renderActiveView() {
  const container = document.getElementById("content");
  if (!container) return;

  const viewModule = views[state.ui.activeView];
  if (viewModule && viewModule.render) {
    viewModule.render(container, state);
  } else {
    container.innerHTML = `
      <div style="padding: 40px; text-align: center; color: var(--color-muted);">
        <div style="font-size: 24px; margin-bottom: 8px;">${state.ui.activeView}</div>
        <div>View not yet implemented</div>
      </div>
    `;
  }
}

function renderStatusBar() {
  const container = document.getElementById("statusbar");
  if (container) {
    statusbar.render(container, state);
  }
}

function showLoading(message) {
  const container = document.getElementById("content");
  if (container) {
    container.innerHTML = `
      <div style="padding: 60px; text-align: center; color: var(--color-muted);">
        <div class="spinner" style="margin: 0 auto 12px;"></div>
        <div>${message}</div>
      </div>
    `;
  }
}

function showDisconnected() {
  const container = document.getElementById("content");
  if (container) {
    container.innerHTML = `
      <div style="padding: 60px; text-align: center; color: var(--color-muted);">
        <div style="font-size: 20px; margin-bottom: 8px; color: var(--color-error);">Cannot connect to server</div>
        <div>Is the API running? Start it with:</div>
        <div style="margin-top: 8px; padding: 8px 16px; background: var(--color-surface); border-radius: 4px; display: inline-block;">
          uvicorn src.server.main:app --reload
        </div>
        <div style="margin-top: 16px;">
          <button class="btn btn-sm" onclick="location.reload()">Retry</button>
        </div>
      </div>
    `;
  }
}

function startRefreshLoop() {
  // Start countdown display
  statusbar.startCountdown(state.config.refreshInterval, renderStatusBar);

  // Start data refresh timer
  refreshTimer = setInterval(async () => {
    await refresh();
  }, state.config.refreshInterval);
}
