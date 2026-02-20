/**
 * Butterfly chart visualization for a single symbol's opportunities.
 *
 * Renders puts extending left and calls extending right from a center line
 * representing the current stock price. Bar length = annualized yield,
 * color intensity = bias score.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, v);
  }
  return el;
}

const LABEL_COLOR = "#e2e8f0";
const MUTED_COLOR = "#94a3b8";
const FONT = "'JetBrains Mono', monospace";

const PROFILE_BANDS = [
  { name: "Aggressive", min: 0.5, max: 1.0 },
  { name: "Moderate", min: 1.0, max: 1.5 },
  { name: "Conservative", min: 1.5, max: 2.0 },
  { name: "Defensive", min: 2.0, max: 2.5 },
];

/**
 * Map a bias score to a color with varying intensity.
 * @param {"put"|"call"} direction
 * @param {number} score - Bias score.
 * @param {number} minScore - Minimum score in the data set.
 * @param {number} maxScore - Maximum score in the data set.
 * @returns {string} HSL color string.
 */
function barColor(direction, score, minScore, maxScore) {
  const hue = direction === "put" ? 0 : 215;
  const range = maxScore - minScore;
  // Normalize 0-1 (high score = saturated/dark)
  const t = range > 0 ? (score - minScore) / range : 0.5;
  const saturation = 50 + t * 40; // 50-90%
  const lightness = 70 - t * 30;  // 70-40%
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}

/**
 * Get the profile name for a given sigma distance.
 */
function profileForSigma(sigma) {
  for (const b of PROFILE_BANDS) {
    if (sigma >= b.min && sigma < b.max) return b.name;
  }
  if (sigma >= 2.5) return "Defensive";
  return "Aggressive";
}

/**
 * Create a butterfly chart SVG element.
 * @param {Array} opportunities - Filtered to a single symbol.
 * @param {number} currentPrice - Current stock price.
 * @param {object} options
 * @param {number} [options.width=800] - SVG width.
 * @returns {SVGElement}
 */
export function createButterflyChart(opportunities, currentPrice, { width = 800 } = {}) {
  const puts = opportunities
    .filter((o) => o.direction === "put")
    .sort((a, b) => b.strike - a.strike); // descending strike (furthest OTM at left)
  const calls = opportunities
    .filter((o) => o.direction === "call")
    .sort((a, b) => a.strike - b.strike); // ascending strike (furthest OTM at right)

  const barH = 20;
  const gap = 6;
  const topPad = 50;
  const bottomPad = 60;
  const sidePad = 80;
  const totalBars = puts.length + calls.length;
  const height = Math.max(200, totalBars * (barH + gap) + topPad + bottomPad);

  const halfW = (width - 2 * sidePad) / 2;
  const centerX = sidePad + halfW;

  const svg = svgEl("svg", { width, height, viewBox: `0 0 ${width} ${height}` });
  svg.style.display = "block";

  // Max yield for scaling
  const maxYield = opportunities.reduce((m, o) => Math.max(m, o.annualized_yield_pct || 0), 1);

  // Bias score range
  const scores = opportunities.map((o) => o.bias_score || 0);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);

  // Center line
  svg.appendChild(svgEl("line", {
    x1: centerX, y1: topPad - 10, x2: centerX, y2: height - bottomPad + 10,
    stroke: LABEL_COLOR, "stroke-width": "1", "stroke-dasharray": "4,3",
  }));

  // Current price label at top
  const priceLabel = svgEl("text", {
    x: centerX, y: topPad - 20,
    "text-anchor": "middle", fill: LABEL_COLOR,
    "font-family": FONT, "font-size": "12", "font-weight": "bold",
  });
  priceLabel.textContent = `$${currentPrice.toFixed(2)}`;
  svg.appendChild(priceLabel);

  const priceSubLabel = svgEl("text", {
    x: centerX, y: topPad - 8,
    "text-anchor": "middle", fill: MUTED_COLOR,
    "font-family": FONT, "font-size": "9",
  });
  priceSubLabel.textContent = "Current Price";
  svg.appendChild(priceSubLabel);

  // Profile zone labels along top
  // Collect unique profiles from the data
  const profilesUsed = new Set(opportunities.map((o) => profileForSigma(o.sigma_distance)));
  let profileLabelX = sidePad;
  for (const band of PROFILE_BANDS) {
    if (!profilesUsed.has(band.name)) continue;
    const label = svgEl("text", {
      x: profileLabelX, y: 14,
      "text-anchor": "start", fill: MUTED_COLOR,
      "font-family": FONT, "font-size": "9",
    });
    label.textContent = `${band.name} (${band.min}-${band.max}σ)`;
    svg.appendChild(label);
    profileLabelX += 170;
  }

  // Draw put bars (left side)
  let y = topPad;
  for (const opp of puts) {
    const barLen = (opp.annualized_yield_pct / maxYield) * halfW;
    const color = barColor("put", opp.bias_score || 0, minScore, maxScore);

    // Bar extends leftward from center
    svg.appendChild(svgEl("rect", {
      x: centerX - barLen, y, width: barLen, height: barH,
      fill: color, rx: "2",
    }));

    // Strike label on the bar
    const strikeLabel = svgEl("text", {
      x: centerX - barLen - 4, y: y + barH / 2 + 4,
      "text-anchor": "end", fill: LABEL_COLOR,
      "font-family": FONT, "font-size": "10",
    });
    strikeLabel.textContent = `$${opp.strike}`;
    svg.appendChild(strikeLabel);

    // DTE + yield inside bar (if bar long enough)
    if (barLen > 60) {
      const infoLabel = svgEl("text", {
        x: centerX - 6, y: y + barH / 2 + 4,
        "text-anchor": "end", fill: "#1e293b",
        "font-family": FONT, "font-size": "9",
      });
      infoLabel.textContent = `${opp.dte}d  ${opp.annualized_yield_pct.toFixed(1)}%`;
      svg.appendChild(infoLabel);
    }

    y += barH + gap;
  }

  // Draw call bars (right side)
  for (const opp of calls) {
    const barLen = (opp.annualized_yield_pct / maxYield) * halfW;
    const color = barColor("call", opp.bias_score || 0, minScore, maxScore);

    // Bar extends rightward from center
    svg.appendChild(svgEl("rect", {
      x: centerX, y, width: barLen, height: barH,
      fill: color, rx: "2",
    }));

    // Strike label on the bar
    const strikeLabel = svgEl("text", {
      x: centerX + barLen + 4, y: y + barH / 2 + 4,
      "text-anchor": "start", fill: LABEL_COLOR,
      "font-family": FONT, "font-size": "10",
    });
    strikeLabel.textContent = `$${opp.strike}`;
    svg.appendChild(strikeLabel);

    // DTE + yield inside bar (if bar long enough)
    if (barLen > 60) {
      const infoLabel = svgEl("text", {
        x: centerX + 6, y: y + barH / 2 + 4,
        "text-anchor": "start", fill: "#1e293b",
        "font-family": FONT, "font-size": "9",
      });
      infoLabel.textContent = `${opp.dte}d  ${opp.annualized_yield_pct.toFixed(1)}%`;
      svg.appendChild(infoLabel);
    }

    y += barH + gap;
  }

  // Side labels: "PUTS" and "CALLS"
  if (puts.length > 0) {
    const putsLabel = svgEl("text", {
      x: sidePad, y: topPad - 8,
      "text-anchor": "start", fill: "hsl(0, 70%, 60%)",
      "font-family": FONT, "font-size": "11", "font-weight": "bold",
    });
    putsLabel.textContent = "PUTS";
    svg.appendChild(putsLabel);
  }
  if (calls.length > 0) {
    const callsLabel = svgEl("text", {
      x: width - sidePad, y: topPad - 8,
      "text-anchor": "end", fill: "hsl(215, 70%, 60%)",
      "font-family": FONT, "font-size": "11", "font-weight": "bold",
    });
    callsLabel.textContent = "CALLS";
    svg.appendChild(callsLabel);
  }

  // Legend at bottom
  const legY = height - 30;
  // Color intensity key
  const intensityLabel = svgEl("text", {
    x: sidePad, y: legY,
    fill: MUTED_COLOR, "font-family": FONT, "font-size": "10",
  });
  intensityLabel.textContent = "Color intensity = Bias Score (darker = higher)";
  svg.appendChild(intensityLabel);

  // Put/call color key
  const putRect = svgEl("rect", { x: sidePad, y: legY + 10, width: 12, height: 10, fill: "hsl(0, 70%, 55%)", rx: "1" });
  svg.appendChild(putRect);
  const putLegLabel = svgEl("text", {
    x: sidePad + 16, y: legY + 19,
    fill: LABEL_COLOR, "font-family": FONT, "font-size": "10",
  });
  putLegLabel.textContent = "Put";
  svg.appendChild(putLegLabel);

  const callRect = svgEl("rect", { x: sidePad + 50, y: legY + 10, width: 12, height: 10, fill: "hsl(215, 70%, 55%)", rx: "1" });
  svg.appendChild(callRect);
  const callLegLabel = svgEl("text", {
    x: sidePad + 66, y: legY + 19,
    fill: LABEL_COLOR, "font-family": FONT, "font-size": "10",
  });
  callLegLabel.textContent = "Call";
  svg.appendChild(callLegLabel);

  // Bar length key
  const barLenLabel = svgEl("text", {
    x: sidePad + 120, y: legY + 19,
    fill: MUTED_COLOR, "font-family": FONT, "font-size": "10",
  });
  barLenLabel.textContent = "Bar length = Annualized Yield %";
  svg.appendChild(barLenLabel);

  return svg;
}
