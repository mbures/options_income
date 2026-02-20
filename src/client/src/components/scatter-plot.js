/**
 * Scatter plot visualization for opportunities.
 *
 * Plots sigma_distance (x) vs annualized_yield_pct (y) with dots colored
 * by direction (put/call) and sized by bias_score. Includes profile band
 * shading, tooltips, and cross-highlight support.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/** Create an SVG element with attributes. */
function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, v);
  }
  return el;
}

const PROFILE_BANDS = [
  { name: "Aggressive", min: 0.5, max: 1.0, color: "rgba(239,68,68,0.08)" },
  { name: "Moderate", min: 1.0, max: 1.5, color: "rgba(251,191,36,0.08)" },
  { name: "Conservative", min: 1.5, max: 2.0, color: "rgba(96,165,250,0.08)" },
  { name: "Defensive", min: 2.0, max: 2.5, color: "rgba(52,211,153,0.08)" },
];

const PUT_COLOR = "#ef4444";
const CALL_COLOR = "#60a5fa";
const LABEL_COLOR = "#e2e8f0";
const MUTED_COLOR = "#94a3b8";
const FONT = "'JetBrains Mono', monospace";

/**
 * Create a scatter plot SVG element.
 * @param {Array} opportunities - Array of opportunity objects.
 * @param {object} options
 * @param {Function} options.onDotClick - Called with opportunity when dot clicked.
 * @param {number} [options.width=800] - SVG width.
 * @param {number} [options.height=350] - SVG height.
 * @returns {SVGElement} SVG element with highlightDot/clearHighlight methods.
 */
export function createScatterPlot(opportunities, { onDotClick, width = 800, height = 350 }) {
  const pad = { top: 30, right: 30, bottom: 50, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const xMin = 0.5;
  const xMax = 2.5;

  // Y-axis: 0 to max yield rounded up to nearest 10
  const maxYield = opportunities.reduce((m, o) => Math.max(m, o.annualized_yield_pct || 0), 0);
  const yMax = Math.max(10, Math.ceil(maxYield / 10) * 10);

  function xScale(v) {
    return pad.left + ((v - xMin) / (xMax - xMin)) * plotW;
  }
  function yScale(v) {
    return pad.top + plotH - (v / yMax) * plotH;
  }

  // Bias score range for radius scaling
  const scores = opportunities.map((o) => o.bias_score || 0);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const allSameScore = minScore === maxScore;

  function radiusForScore(score) {
    if (allSameScore) return 8;
    return 4 + ((score - minScore) / (maxScore - minScore)) * 8;
  }

  const svg = svgEl("svg", { width, height, viewBox: `0 0 ${width} ${height}` });
  svg.style.display = "block";

  // Profile band shading
  for (const band of PROFILE_BANDS) {
    const bx = xScale(band.min);
    const bw = xScale(band.max) - bx;
    svg.appendChild(svgEl("rect", {
      x: bx, y: pad.top, width: bw, height: plotH,
      fill: band.color,
    }));
    // Band label at top
    const label = svgEl("text", {
      x: bx + bw / 2, y: pad.top - 8,
      "text-anchor": "middle", fill: MUTED_COLOR,
      "font-family": FONT, "font-size": "10",
    });
    label.textContent = band.name;
    svg.appendChild(label);
  }

  // Axes
  // X-axis line
  svg.appendChild(svgEl("line", {
    x1: pad.left, y1: pad.top + plotH, x2: pad.left + plotW, y2: pad.top + plotH,
    stroke: MUTED_COLOR, "stroke-width": "1",
  }));
  // Y-axis line
  svg.appendChild(svgEl("line", {
    x1: pad.left, y1: pad.top, x2: pad.left, y2: pad.top + plotH,
    stroke: MUTED_COLOR, "stroke-width": "1",
  }));

  // X-axis ticks
  for (let v = 0.5; v <= 2.5; v += 0.5) {
    const x = xScale(v);
    svg.appendChild(svgEl("line", {
      x1: x, y1: pad.top + plotH, x2: x, y2: pad.top + plotH + 5,
      stroke: MUTED_COLOR, "stroke-width": "1",
    }));
    const tick = svgEl("text", {
      x, y: pad.top + plotH + 18,
      "text-anchor": "middle", fill: LABEL_COLOR,
      "font-family": FONT, "font-size": "11",
    });
    tick.textContent = v.toFixed(1);
    svg.appendChild(tick);
  }
  // X-axis label
  const xLabel = svgEl("text", {
    x: pad.left + plotW / 2, y: height - 6,
    "text-anchor": "middle", fill: LABEL_COLOR,
    "font-family": FONT, "font-size": "11",
  });
  xLabel.textContent = "Sigma Distance";
  svg.appendChild(xLabel);

  // Y-axis ticks
  const yTickCount = Math.min(yMax / 10, 8);
  const yStep = yMax / yTickCount;
  for (let i = 0; i <= yTickCount; i++) {
    const v = i * yStep;
    const y = yScale(v);
    svg.appendChild(svgEl("line", {
      x1: pad.left - 5, y1: y, x2: pad.left, y2: y,
      stroke: MUTED_COLOR, "stroke-width": "1",
    }));
    // Horizontal grid line
    if (i > 0) {
      svg.appendChild(svgEl("line", {
        x1: pad.left, y1: y, x2: pad.left + plotW, y2: y,
        stroke: MUTED_COLOR, "stroke-width": "0.3",
      }));
    }
    const tick = svgEl("text", {
      x: pad.left - 10, y: y + 4,
      "text-anchor": "end", fill: LABEL_COLOR,
      "font-family": FONT, "font-size": "11",
    });
    tick.textContent = v.toFixed(0) + "%";
    svg.appendChild(tick);
  }
  // Y-axis label (rotated)
  const yLabel = svgEl("text", {
    x: 14, y: pad.top + plotH / 2,
    "text-anchor": "middle", fill: LABEL_COLOR,
    "font-family": FONT, "font-size": "11",
    transform: `rotate(-90, 14, ${pad.top + plotH / 2})`,
  });
  yLabel.textContent = "Ann. Yield %";
  svg.appendChild(yLabel);

  // Tooltip group (initially hidden)
  const tooltip = svgEl("g", { visibility: "hidden" });
  const tooltipBg = svgEl("rect", {
    rx: "4", ry: "4", fill: "#1e293b", stroke: "#475569",
    "stroke-width": "1", opacity: "0.95",
  });
  tooltip.appendChild(tooltipBg);
  const tooltipLines = [];
  for (let i = 0; i < 6; i++) {
    const t = svgEl("text", {
      fill: LABEL_COLOR, "font-family": FONT, "font-size": "11",
    });
    tooltipLines.push(t);
    tooltip.appendChild(t);
  }

  function showTooltip(opp, cx, cy) {
    const lines = [
      `${opp.symbol} ${opp.direction.toUpperCase()}`,
      `Strike: $${opp.strike}`,
      `DTE: ${opp.dte}`,
      `Yield: ${(opp.annualized_yield_pct || 0).toFixed(1)}%`,
      `P(ITM): ${(opp.p_itm || 0).toFixed(1)}%`,
      `Sigma: ${(opp.sigma_distance || 0).toFixed(2)}`,
    ];
    const lineH = 15;
    const tipW = 150;
    const tipH = lines.length * lineH + 12;

    // Flip if near right or bottom edge
    let tx = cx + 12;
    let ty = cy - tipH / 2;
    if (tx + tipW > width - 10) tx = cx - tipW - 12;
    if (ty < 5) ty = 5;
    if (ty + tipH > height - 5) ty = height - tipH - 5;

    tooltipBg.setAttribute("x", tx);
    tooltipBg.setAttribute("y", ty);
    tooltipBg.setAttribute("width", tipW);
    tooltipBg.setAttribute("height", tipH);

    for (let i = 0; i < lines.length; i++) {
      tooltipLines[i].setAttribute("x", tx + 8);
      tooltipLines[i].setAttribute("y", ty + 16 + i * lineH);
      tooltipLines[i].textContent = lines[i];
    }
    tooltip.setAttribute("visibility", "visible");
  }

  function hideTooltip() {
    tooltip.setAttribute("visibility", "hidden");
  }

  // Dots
  const dotMap = {};
  for (const opp of opportunities) {
    const sx = opp.sigma_distance || 0;
    const sy = opp.annualized_yield_pct || 0;
    if (sx < xMin || sx > xMax) continue;

    const cx = xScale(sx);
    const cy = yScale(Math.min(sy, yMax));
    const r = radiusForScore(opp.bias_score || 0);
    const color = opp.direction === "put" ? PUT_COLOR : CALL_COLOR;

    const dot = svgEl("circle", {
      cx, cy, r,
      fill: color, "fill-opacity": "0.7",
      stroke: color, "stroke-width": "1", "stroke-opacity": "0.9",
      "data-id": opp.id,
      style: "cursor: pointer; transition: r 0.15s, stroke-width 0.15s;",
    });

    dot.addEventListener("mouseenter", () => {
      dot.setAttribute("r", r + 3);
      dot.setAttribute("stroke-width", "2");
      showTooltip(opp, cx, cy);
    });
    dot.addEventListener("mouseleave", () => {
      dot.setAttribute("r", r);
      dot.setAttribute("stroke-width", "1");
      hideTooltip();
    });
    dot.addEventListener("click", () => {
      if (onDotClick) onDotClick(opp);
    });

    svg.appendChild(dot);
    dotMap[opp.id] = { dot, r, symbol: opp.symbol };
  }

  // Add tooltip on top of dots
  svg.appendChild(tooltip);

  // Legend
  const legendY = height - 6;
  const legendX = width - 160;
  const putDot = svgEl("circle", { cx: legendX, cy: legendY - 3, r: 5, fill: PUT_COLOR, "fill-opacity": "0.7" });
  svg.appendChild(putDot);
  const putLabel = svgEl("text", {
    x: legendX + 10, y: legendY, fill: LABEL_COLOR, "font-family": FONT, "font-size": "10",
  });
  putLabel.textContent = "Put";
  svg.appendChild(putLabel);

  const callDot = svgEl("circle", { cx: legendX + 50, cy: legendY - 3, r: 5, fill: CALL_COLOR, "fill-opacity": "0.7" });
  svg.appendChild(callDot);
  const callLabel = svgEl("text", {
    x: legendX + 60, y: legendY, fill: LABEL_COLOR, "font-family": FONT, "font-size": "10",
  });
  callLabel.textContent = "Call";
  svg.appendChild(callLabel);

  // Highlight methods for cross-linking
  let highlightTimer = null;

  svg.highlightDot = function (id) {
    svg.clearHighlight();
    const entry = dotMap[id];
    if (!entry) return;
    entry.dot.setAttribute("r", entry.r + 4);
    entry.dot.setAttribute("stroke-width", "3");
    entry.dot.setAttribute("stroke", "#ffffff");
    highlightTimer = setTimeout(() => svg.clearHighlight(), 2000);
  };

  svg.highlightSymbol = function (symbol) {
    svg.clearHighlight();
    for (const entry of Object.values(dotMap)) {
      if (entry.symbol === symbol) {
        entry.dot.setAttribute("r", entry.r + 4);
        entry.dot.setAttribute("stroke-width", "3");
        entry.dot.setAttribute("stroke", "#ffffff");
      } else {
        entry.dot.setAttribute("fill-opacity", "0.15");
        entry.dot.setAttribute("stroke-opacity", "0.2");
      }
    }
    highlightTimer = setTimeout(() => svg.clearHighlight(), 3000);
  };

  svg.clearHighlight = function () {
    if (highlightTimer) {
      clearTimeout(highlightTimer);
      highlightTimer = null;
    }
    for (const entry of Object.values(dotMap)) {
      entry.dot.setAttribute("r", entry.r);
      entry.dot.setAttribute("stroke-width", "1");
      entry.dot.setAttribute("fill-opacity", "0.7");
      entry.dot.setAttribute("stroke-opacity", "0.9");
      const color = entry.dot.getAttribute("fill");
      entry.dot.setAttribute("stroke", color);
    }
  };

  return svg;
}
