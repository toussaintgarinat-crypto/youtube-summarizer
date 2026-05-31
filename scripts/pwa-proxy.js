/**
 * PWA reverse proxy — serves static PWA files + proxies to Streamlit (HTTP + WebSocket).
 * Injects PWA <link>/<meta> tags into HTML on-the-fly.
 * Usage:  node scripts/pwa-proxy.js
 * Then access:  http://localhost:8500
 */
const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");

const PORT = parseInt(process.env.PWA_PORT || "8500", 10);
const TARGET_PORT = parseInt(process.env.STREAMLIT_PORT || "8501", 10);
const TARGET_HOST = process.env.STREAMLIT_HOST || "localhost";
const PWA_DIR = path.resolve(__dirname, "..", "pwa");

const MIME = {
  ".json": "application/json",
  ".js": "application/javascript",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".css": "text/css",
  ".html": "text/html",
};

const PWA_INJECT =
  '<link rel="manifest" href="/pwa/manifest.json">' +
  '<link rel="apple-touch-icon" href="/pwa/icon-192.png">' +
  '<meta name="apple-mobile-web-app-capable" content="yes">' +
  '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">' +
  '<script>if("serviceWorker" in navigator){navigator.serviceWorker.register("/pwa/sw.js");}</script>';

function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const filePath = path.join(PWA_DIR, url.pathname.replace("/pwa/", ""));

  if (
    url.pathname.startsWith("/pwa/") &&
    filePath.startsWith(PWA_DIR) &&
    fs.existsSync(filePath) &&
    fs.statSync(filePath).isFile()
  ) {
    const ext = path.extname(filePath);
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
    });
    fs.createReadStream(filePath).pipe(res);
    return true;
  }
  return false;
}

function proxyRequest(req, res) {
  const options = {
    hostname: TARGET_HOST,
    port: TARGET_PORT,
    path: req.url,
    method: req.method,
    headers: { ...req.headers },
  };
  delete options.headers["proxy-connection"];

  const proxyReq = http.request(options, (proxyRes) => {
    const headers = { ...proxyRes.headers };

    const ct = (headers["content-type"] || "").toLowerCase();
    const isHtml = ct.includes("text/html");

    if (isHtml && proxyRes.statusCode === 200) {
      delete headers["content-length"];
      delete headers["transfer-encoding"];
      res.writeHead(proxyRes.statusCode, headers);

      const chunks = [];
      proxyRes.on("data", (chunk) => chunks.push(chunk));
      proxyRes.on("end", () => {
        let body = Buffer.concat(chunks).toString("utf-8");
        body = body.replace("</title>", "</title>" + PWA_INJECT);
        res.end(body);
      });
    } else {
      delete headers["transfer-encoding"];
      res.writeHead(proxyRes.statusCode, headers);
      proxyRes.pipe(res);
    }
  });

  proxyReq.on("error", () => {
    res.writeHead(502, { "Content-Type": "text/plain" });
    res.end("Streamlit server is not available on port " + TARGET_PORT);
  });

  req.pipe(proxyReq);
}

const server = http.createServer((req, res) => {
  if (!serveStatic(req, res)) {
    proxyRequest(req, res);
  }
});

server.on("upgrade", (req, clientSocket, head) => {
  if (serveStatic(req, clientSocket)) return;

  const serverSocket = net.connect(TARGET_PORT, TARGET_HOST, () => {
    const lines = [
      `${req.method} ${req.url} HTTP/1.1`,
      ...Object.entries(req.headers).map(([k, v]) => `${k}: ${v}`),
      "",
      "",
    ];
    serverSocket.write(lines.join("\r\n"));
    serverSocket.write(head);
    serverSocket.pipe(clientSocket);
    clientSocket.pipe(serverSocket);
  });

  serverSocket.on("error", () => clientSocket.end());
  clientSocket.on("error", () => serverSocket.end());
});

server.listen(PORT, () => {
  console.log("");
  console.log("  YouTube Summarizer \u2013 PWA mode");
  console.log("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500");
  console.log(`  App  : http://localhost:${PORT}`);
  console.log(`  Proxy: ${PORT} \u2192  Streamlit : ${TARGET_PORT}`);
  console.log("");
  console.log("  Ajoutez \u00e0 l'\u00e9cran d'accueil du t\u00e9l\u00e9phone :");
  console.log("    iOS   \u2192 Safari > Partager > Sur l'\u00e9cran d'accueil");
  console.log("    Android \u2192 Chrome > Menu > Installer l'application");
  console.log("");
});
