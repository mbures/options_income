/**
 * Formatting utilities for currency, percentages, and dates.
 */

/**
 * Format a number as currency ($X,XXX.XX).
 * @param {number} value
 * @returns {string}
 */
export function formatCurrency(value) {
  if (value == null || isNaN(value)) return "\u2014";
  return "$" + value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Format a number as a percentage (XX.X%).
 * @param {number} value - Value as a fraction (e.g., 0.082 for 8.2%) or whole number.
 * @param {boolean} [isWhole=false] - If true, value is already a percentage (e.g., 8.2).
 * @returns {string}
 */
export function formatPercent(value, isWhole = false) {
  if (value == null || isNaN(value)) return "\u2014";
  const pct = isWhole ? value : value * 100;
  return pct.toFixed(1) + "%";
}

/**
 * Format a date string as YYYY-MM-DD.
 * @param {string|Date} value
 * @returns {string}
 */
export function formatDate(value) {
  if (!value) return "\u2014";
  if (typeof value === "string") {
    // Already YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    // ISO datetime
    return value.slice(0, 10);
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return String(value);
}

/**
 * Format a number to N decimal places.
 * @param {number} value
 * @param {number} [decimals=2]
 * @returns {string}
 */
export function formatNumber(value, decimals = 2) {
  if (value == null || isNaN(value)) return "\u2014";
  return value.toFixed(decimals);
}
