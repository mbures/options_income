/**
 * Sidebar navigation component.
 *
 * Renders the navigation sidebar with view links and portfolio selector.
 * Highlights the active view and dispatches navigation events.
 */

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: "\u25A1" },
  { id: "recommend", label: "Recommend", icon: "\u25CE" },
  { id: "opportunities", label: "Opportunities", icon: "\u25C9" },
  { id: "trades", label: "Trades", icon: "\u2191" },
  { id: "performance", label: "Performance", icon: "\u25A3" },
];

let activeView = "dashboard";
let onNavigate = null;
let onPortfolioChange = null;
let badgeCounts = {};

/**
 * Render the sidebar into the given container.
 * @param {HTMLElement} container - The sidebar DOM element.
 * @param {Function} navigateFn - Callback when a nav item is clicked.
 */
export function render(container, navigateFn) {
  onNavigate = navigateFn;

  const logo = document.createElement("div");
  logo.style.padding = "16px";
  logo.style.fontSize = "15px";
  logo.style.fontWeight = "600";
  logo.style.color = "var(--color-text)";
  logo.style.borderBottom = "1px solid var(--color-border)";
  logo.style.marginBottom = "8px";
  logo.textContent = "Options Income";

  container.innerHTML = "";
  container.appendChild(logo);

  // Portfolio selector placeholder (populated later via renderPortfolioSelector)
  const selectorDiv = document.createElement("div");
  selectorDiv.id = "portfolio-selector";
  container.appendChild(selectorDiv);

  const nav = document.createElement("div");
  nav.id = "nav-items";
  container.appendChild(nav);

  renderItems(nav);
}

/**
 * Set the active navigation item and re-render.
 * @param {string} viewName - The view ID to activate.
 */
export function setActive(viewName) {
  activeView = viewName;
  const nav = document.getElementById("nav-items");
  if (nav) {
    renderItems(nav);
  }
}

/**
 * Render the portfolio selector dropdown.
 * Only shown when multiple portfolios exist.
 * @param {Array} portfolios - List of portfolio objects.
 * @param {string} selectedId - Currently selected portfolio ID.
 * @param {Function} changeFn - Callback when selection changes.
 */
export function renderPortfolioSelector(portfolios, selectedId, changeFn) {
  onPortfolioChange = changeFn;
  const container = document.getElementById("portfolio-selector");
  if (!container) return;

  container.innerHTML = "";

  // Only show selector if multiple portfolios exist
  if (!portfolios || portfolios.length <= 1) return;

  const wrapper = document.createElement("div");
  wrapper.style.padding = "8px 16px 12px";
  wrapper.style.borderBottom = "1px solid var(--color-border)";
  wrapper.style.marginBottom = "4px";

  const label = document.createElement("div");
  label.style.fontSize = "10px";
  label.style.color = "var(--color-muted)";
  label.style.textTransform = "uppercase";
  label.style.letterSpacing = "0.5px";
  label.style.marginBottom = "4px";
  label.textContent = "Portfolio";

  const select = document.createElement("select");
  select.style.width = "100%";
  select.style.padding = "4px 6px";
  select.style.backgroundColor = "var(--color-bg)";
  select.style.border = "1px solid var(--color-border)";
  select.style.borderRadius = "4px";
  select.style.color = "var(--color-text)";
  select.style.fontFamily = "inherit";
  select.style.fontSize = "12px";

  for (const p of portfolios) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name || `Portfolio ${p.id}`;
    if (p.id === selectedId) opt.selected = true;
    select.appendChild(opt);
  }

  select.addEventListener("change", (e) => {
    if (onPortfolioChange) {
      onPortfolioChange(e.target.value);
    }
  });

  wrapper.appendChild(label);
  wrapper.appendChild(select);
  container.appendChild(wrapper);
}

/**
 * Update badge count for a nav item.
 * @param {string} itemId - Nav item ID (e.g., "opportunities").
 * @param {number} count - Badge count (0 hides badge).
 */
export function setBadge(itemId, count) {
  badgeCounts[itemId] = count;
  const nav = document.getElementById("nav-items");
  if (nav) {
    renderItems(nav);
  }
}

function renderItems(container) {
  container.innerHTML = "";

  for (const item of NAV_ITEMS) {
    const el = document.createElement("div");
    el.className = "nav-item" + (item.id === activeView ? " active" : "");

    let badgeHtml = "";
    const count = badgeCounts[item.id] || 0;
    if (count > 0) {
      badgeHtml = `<span style="background: var(--color-error, #e53e3e); color: #fff; font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 8px; margin-left: auto;">${count > 99 ? "99+" : count}</span>`;
    }

    el.innerHTML = `<span class="nav-icon">${item.icon}</span><span>${item.label}</span>${badgeHtml}`;
    el.addEventListener("click", () => {
      if (onNavigate) {
        onNavigate(item.id);
      }
    });
    container.appendChild(el);
  }
}
