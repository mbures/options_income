/**
 * API service layer.
 *
 * Wraps fetch() with consistent error handling, JSON parsing, and timeout.
 * All API calls go through this module.
 */

const TIMEOUT_MS = 30000;

/**
 * Core fetch wrapper with error handling and timeout.
 * @param {string} method - HTTP method.
 * @param {string} path - URL path (relative).
 * @param {object} [options] - Optional body, params.
 * @returns {Promise<any>} Parsed JSON response.
 */
async function request(method, path, options = {}) {
  const { body, params } = options;

  let url = path;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value != null) {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) {
      url += `?${qs}`;
    }
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const fetchOptions = {
    method,
    headers: {},
    signal: controller.signal,
  };

  if (body != null) {
    fetchOptions.headers["Content-Type"] = "application/json";
    fetchOptions.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, fetchOptions);
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw new Error("Server unavailable");
  } finally {
    clearTimeout(timeoutId);
  }

  // Parse response (skip for 204 No Content)
  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (response.status !== 204 && contentType.includes("application/json")) {
    data = await response.json();
  }

  if (!response.ok) {
    const message =
      (data && (data.message || data.detail)) ||
      (response.status >= 500
        ? "Server error"
        : `Request failed (${response.status})`);
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

// Health
export async function checkHealth() {
  return request("GET", "/health");
}

// Portfolios
export async function listPortfolios() {
  return request("GET", "/api/v1/portfolios/");
}

export async function getPortfolio(id) {
  return request("GET", `/api/v1/portfolios/${id}`);
}

export async function getPortfolioSummary(id) {
  return request("GET", `/api/v1/portfolios/${id}/summary`);
}

// Wheels
export async function createWheel(portfolioId, data) {
  return request("POST", `/api/v1/portfolios/${portfolioId}/wheels`, { body: data });
}

export async function listWheels(portfolioId, activeOnly = true) {
  return request("GET", `/api/v1/portfolios/${portfolioId}/wheels`, {
    params: { active_only: activeOnly },
  });
}

export async function getWheel(id) {
  return request("GET", `/api/v1/wheels/${id}`);
}

export async function updateWheel(id, data) {
  return request("PUT", `/api/v1/wheels/${id}`, { body: data });
}

export async function deleteWheel(id) {
  return request("DELETE", `/api/v1/wheels/${id}`);
}

// Trades
export async function recordTrade(wheelId, data) {
  return request("POST", `/api/v1/wheels/${wheelId}/trades`, { body: data });
}

export async function listTrades(wheelId) {
  return request("GET", `/api/v1/wheels/${wheelId}/trades`);
}

export async function getTrade(id) {
  return request("GET", `/api/v1/trades/${id}`);
}

export async function expireTrade(tradeId, priceAtExpiry) {
  return request("POST", `/api/v1/trades/${tradeId}/expire`, {
    body: { price_at_expiry: priceAtExpiry },
  });
}

export async function closeTrade(tradeId, closePrice) {
  return request("POST", `/api/v1/trades/${tradeId}/close`, {
    body: { close_price: closePrice },
  });
}

// Recommendations
export async function getRecommendation(wheelId, maxDte = 14) {
  return request("GET", `/api/v1/wheels/${wheelId}/recommend`, {
    params: { max_dte: maxDte },
  });
}

export async function getBatchRecommendations(wheelIds, maxDte = 14) {
  return request("POST", "/api/v1/wheels/recommend/batch", {
    body: { wheel_ids: wheelIds, max_dte: maxDte },
  });
}

// Positions
export async function getPositionStatus(wheelId) {
  return request("GET", `/api/v1/wheels/${wheelId}/position`);
}

export async function getPortfolioPositions(portfolioId) {
  return request("GET", `/api/v1/portfolios/${portfolioId}/positions`);
}

export async function getOpenPositions() {
  return request("GET", "/api/v1/positions/open");
}

// Watchlist
export async function listWatchlist() {
  return request("GET", "/api/v1/watchlist");
}

export async function addToWatchlist(symbol, notes) {
  return request("POST", "/api/v1/watchlist", { body: { symbol, notes } });
}

export async function removeFromWatchlist(symbol) {
  return request("DELETE", `/api/v1/watchlist/${symbol}`);
}

// Opportunities
export async function listOpportunities({ symbol, direction, profile, unread_only, limit } = {}) {
  return request("GET", "/api/v1/opportunities", {
    params: { symbol, direction, profile, unread_only, limit },
  });
}

export async function getOpportunityCount() {
  return request("GET", "/api/v1/opportunities/count");
}

export async function markOpportunityRead(id) {
  return request("POST", `/api/v1/opportunities/${id}/read`);
}

export async function markAllOpportunitiesRead() {
  return request("POST", "/api/v1/opportunities/read-all");
}

export async function triggerScan() {
  return request("POST", "/api/v1/watchlist/scan");
}

// Performance
export async function getPerformance() {
  return request("GET", "/api/v1/performance");
}

export async function getWheelPerformance(wheelId) {
  return request("GET", `/api/v1/wheels/${wheelId}/performance`);
}
