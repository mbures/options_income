import "./style.css";
import { init, registerView } from "./app.js";

// Import views
import * as dashboard from "./views/dashboard.js";
import * as recommendations from "./views/recommendations.js";
import * as opportunities from "./views/opportunities.js";
import * as trades from "./views/trades.js";
import * as performance from "./views/performance.js";

// Import and register forms
import { register as registerInitWheel } from "./forms/init-wheel.js";
import { register as registerRecordTrade } from "./forms/record-trade.js";
import { register as registerExpireTrade } from "./forms/expire-trade.js";
import { register as registerCloseTrade } from "./forms/close-trade.js";
import { register as registerEditWheel } from "./forms/edit-wheel.js";

// Register views
registerView("dashboard", dashboard);
registerView("recommend", recommendations);
registerView("opportunities", opportunities);
registerView("trades", trades);
registerView("performance", performance);

// Register panel forms
registerInitWheel();
registerRecordTrade();
registerExpireTrade();
registerCloseTrade();
registerEditWheel();

// Initialize the application when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  init();
});
