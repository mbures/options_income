#!/usr/bin/env node
/**
 * Takes a screenshot of a running web UI via CDP (Chrome DevTools Protocol).
 * Connects to an existing headless Chrome on port 9222.
 *
 * Usage: node take_screenshot.js [url] [output_path]
 *   url         - URL to screenshot (default: http://localhost:5173)
 *   output_path - Full path for the output PNG file
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const CDP_PORT = 9222;
const DEFAULT_URL = 'http://localhost:5173';
const LOAD_WAIT_MS = 3000;

const targetUrl = process.argv[2] || DEFAULT_URL;
const outputPath = process.argv[3];

if (!outputPath) {
  console.error('Usage: node take_screenshot.js [url] <output_path>');
  process.exit(1);
}

function getCdpWebSocketUrl() {
  return new Promise((resolve, reject) => {
    http.get(`http://localhost:${CDP_PORT}/json/version`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data).webSocketDebuggerUrl);
        } catch (e) {
          reject(new Error('Failed to parse CDP version response'));
        }
      });
    }).on('error', () => {
      reject(new Error(
        `No headless Chrome found on port ${CDP_PORT}. ` +
        `Start one with: google-chrome --no-sandbox --headless --disable-gpu --remote-debugging-port=${CDP_PORT}`
      ));
    });
  });
}

async function takeScreenshot() {
  const wsUrl = await getCdpWebSocketUrl();
  const ws = new WebSocket(wsUrl);
  let msgId = 1;

  function send(method, params = {}, sessionId = null) {
    const id = msgId++;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        ws.removeListener('message', handler);
        reject(new Error(`Timeout waiting for response to ${method}`));
      }, 15000);

      function handler(raw) {
        const msg = JSON.parse(raw);
        if (msg.id === id) {
          clearTimeout(timeout);
          ws.removeListener('message', handler);
          if (msg.error) {
            reject(new Error(`${method} failed: ${msg.error.message}`));
          } else {
            resolve(msg.result);
          }
        }
      }
      ws.on('message', handler);

      const payload = { id, method, params };
      if (sessionId) payload.sessionId = sessionId;
      ws.send(JSON.stringify(payload));
    });
  }

  await new Promise((resolve, reject) => {
    ws.on('open', resolve);
    ws.on('error', reject);
  });

  let targetId;
  try {
    // Create a new tab and navigate to the target URL
    const result = await send('Target.createTarget', { url: targetUrl });
    targetId = result.targetId;

    // Attach to the tab
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });

    // Wait for page to render
    await new Promise(r => setTimeout(r, LOAD_WAIT_MS));

    // Capture screenshot
    const { data } = await send('Page.captureScreenshot', { format: 'png' }, sessionId);

    // Ensure output directory exists
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, Buffer.from(data, 'base64'));
    console.log(outputPath);
  } finally {
    // Clean up the tab
    if (targetId) {
      await send('Target.closeTarget', { targetId }).catch(() => {});
    }
    ws.close();
  }
}

takeScreenshot().catch(e => {
  console.error(`Screenshot failed: ${e.message}`);
  process.exit(1);
});
