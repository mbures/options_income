Take a screenshot of the running UI and save it to the tests/screenshots directory.

## Instructions

1. Run the screenshot script using the Bash tool:

```
node /workspaces/options_income/tests/screenshots/take_screenshot.js <url> <output_path>
```

- **URL**: Use the first argument if provided (e.g., `/screenshot http://localhost:8000/docs`). Default to `http://localhost:5173`.
- **Output path**: Always save to `/workspaces/options_income/tests/screenshots/` with filename format `YYYYMMDDHHMMSS_<name>.png` where:
  - The timestamp uses 24-hour time and is generated via: `date +%Y%m%d%H%M%S`
  - `<name>` is a short descriptive label (e.g., `dashboard`, `trades`, `opportunities`). Use the second argument if provided, otherwise infer from the URL path, or default to `screenshot`.

Example:
```bash
TIMESTAMP=$(date +%Y%m%d%H%M%S)
node /workspaces/options_income/tests/screenshots/take_screenshot.js http://localhost:5173 /workspaces/options_income/tests/screenshots/${TIMESTAMP}_dashboard.png
```

2. After capturing, read the screenshot PNG file using the Read tool to display it to the user.

3. If the screenshot script fails with "No headless Chrome found", start one first:
```bash
/opt/google/chrome/chrome --no-sandbox --headless --disable-gpu --remote-debugging-port=9222 &
sleep 2
```
Then retry the screenshot.

4. Report the saved file path to the user.
