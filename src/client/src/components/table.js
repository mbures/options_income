/**
 * Sortable table component.
 *
 * Renders a data table with sortable columns, custom cell renderers,
 * and compact styling.
 */

/**
 * Create a sortable table.
 * @param {object} options
 * @param {Array<object>} options.columns - Column definitions.
 *   Each column: { key, label, sortable, align, render }
 *   - key: property name in row data
 *   - label: header text
 *   - sortable: boolean (default true)
 *   - align: "left" | "right" (default "left")
 *   - render: optional function(value, row) returning HTML string or DOM element
 * @param {Array<object>} options.data - Array of row objects.
 * @param {string} [options.sortKey] - Initial sort column key.
 * @param {string} [options.sortDir] - Initial sort direction ("asc" | "desc").
 * @param {Function} [options.onSort] - Called with (key, dir) when sort changes.
 * @returns {HTMLTableElement}
 */
export function createTable(options) {
  const {
    columns,
    data,
    sortKey = null,
    sortDir = "asc",
    onSort = null,
  } = options;

  let currentSortKey = sortKey;
  let currentSortDir = sortDir;

  const table = document.createElement("table");
  table.className = "data-table";

  // Sort data
  function getSortedData() {
    if (!currentSortKey) return data;

    const col = columns.find((c) => c.key === currentSortKey);
    if (!col || col.sortable === false) return data;

    return [...data].sort((a, b) => {
      const aVal = a[currentSortKey];
      const bVal = b[currentSortKey];

      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      let cmp;
      if (typeof aVal === "number" && typeof bVal === "number") {
        cmp = aVal - bVal;
      } else {
        cmp = String(aVal).localeCompare(String(bVal));
      }

      return currentSortDir === "desc" ? -cmp : cmp;
    });
  }

  function renderTable() {
    table.innerHTML = "";

    // Header
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    for (const col of columns) {
      const th = document.createElement("th");
      const sortable = col.sortable !== false;

      let sortIndicator = "";
      if (sortable && col.key === currentSortKey) {
        sortIndicator = currentSortDir === "asc" ? " \u25B2" : " \u25BC";
        th.classList.add("sort-active");
      }

      th.textContent = col.label + sortIndicator;

      if (col.align === "right") {
        th.classList.add("align-right");
      }

      if (sortable) {
        th.addEventListener("click", () => {
          if (currentSortKey === col.key) {
            currentSortDir = currentSortDir === "asc" ? "desc" : "asc";
          } else {
            currentSortKey = col.key;
            currentSortDir = "asc";
          }
          renderTable();
          if (onSort) onSort(currentSortKey, currentSortDir);
        });
      } else {
        th.style.cursor = "default";
      }

      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Body
    const tbody = document.createElement("tbody");
    const sorted = getSortedData();

    if (sorted.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.style.textAlign = "center";
      td.style.padding = "24px";
      td.style.color = "var(--color-muted)";
      td.textContent = "No data";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      for (const row of sorted) {
        const tr = document.createElement("tr");

        for (const col of columns) {
          const td = document.createElement("td");
          const value = row[col.key];

          if (col.align === "right") {
            td.classList.add("align-right");
          }

          if (col.render) {
            const rendered = col.render(value, row);
            if (typeof rendered === "string") {
              td.innerHTML = rendered;
            } else if (rendered instanceof HTMLElement) {
              td.appendChild(rendered);
            }
          } else {
            td.textContent = value != null ? String(value) : "\u2014";
          }

          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
    }

    table.appendChild(tbody);
  }

  renderTable();
  return table;
}
