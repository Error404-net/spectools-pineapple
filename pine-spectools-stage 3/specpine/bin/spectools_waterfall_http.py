#!/usr/bin/env python3
"""Lightweight HTTP + SSE server for the SpecPine live graphical waterfall.

Serves an HTML/Canvas waterfall page at GET / and streams sweep events as
Server-Sent Events at GET /events.  No external dependencies — stdlib only.

Usage (auto-started by payload during Text Waterfall scan):
  python3 spectools_waterfall_http.py --events-file /tmp/specpine_events.jsonl
Then open http://<device-ip>:8080/ in a browser.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_stop_event = threading.Event()
_events_file = "/tmp/specpine_events.jsonl"

_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpecPine — Spectrum Waterfall</title>
<style>
:root {
  --bg:      #050d18;
  --panel:   #0a1628;
  --border:  #0f2540;
  --teal:    #00c8a0;
  --teal2:   #00e8c0;
  --cyan:    #00c8dc;
  --amber:   #ffb830;
  --red:     #ff4040;
  --gray:    #3a5060;
  --white:   #d8eef8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--white);
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  padding: 12px;
  min-height: 100vh;
}

/* ── header ── */
header {
  display: flex;
  align-items: center;
  gap: 18px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
  margin-bottom: 10px;
}
.logo {
  font-size: 15px;
  font-weight: bold;
  letter-spacing: 4px;
  color: var(--teal2);
  text-shadow: 0 0 12px rgba(0,232,192,0.5);
}
.device-tag {
  color: var(--gray);
  font-size: 11px;
  letter-spacing: 2px;
}
.conn-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--gray);
  box-shadow: 0 0 0 2px var(--bg);
  flex-shrink: 0;
  transition: background 0.3s, box-shadow 0.3s;
}
.conn-dot.live { background: var(--teal); box-shadow: 0 0 8px rgba(0,200,160,0.8); }
.conn-dot.error { background: var(--red); box-shadow: 0 0 8px rgba(255,64,64,0.8); }

/* ── stats bar ── */
#stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 12px;
  margin-bottom: 8px;
}
.stat-item { display: flex; flex-direction: column; gap: 1px; }
.stat-label { color: var(--gray); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; }
.stat-val   { color: var(--teal2); font-size: 13px; font-weight: bold; }
.stat-val.amber { color: var(--amber); }
.stat-val.red   { color: var(--red); }

/* ── canvas wrap ── */
#wrap {
  position: relative;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  line-height: 0;
}
canvas { display: block; }
#cv-main    { position: relative; }
#cv-overlay { position: absolute; top: 0; left: 0; pointer-events: none; }
#cv-ui      { position: absolute; top: 0; left: 0; pointer-events: none; }

/* ── frequency axis ── */
#freq-axis {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 10px;
  color: var(--gray);
  border-top: 1px solid var(--border);
}

/* ── legend ── */
#legend {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--gray);
}
#lbar { border: 1px solid var(--border); border-radius: 2px; }

/* ── peak-hold toggle ── */
#controls {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 10px;
  font-size: 11px;
  color: var(--gray);
}
button {
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--teal);
  padding: 3px 10px;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  border-radius: 3px;
  letter-spacing: 1px;
}
button:hover { border-color: var(--teal); background: #0d1e30; }
button.active { border-color: var(--teal2); color: var(--teal2); background: #0a2030; }
</style>
</head>
<body>

<header>
  <div class="logo">&#9632; SPECPINE</div>
  <div class="device-tag">WI-SPY DBx &bull; RF WATERFALL</div>
  <div style="flex:1"></div>
  <div id="conn-dot" class="conn-dot"></div>
  <div id="conn-label" style="color:var(--gray);font-size:10px;letter-spacing:1px">CONNECTING</div>
</header>

<div id="stats">
  <div class="stat-item"><div class="stat-label">Sweeps</div><div class="stat-val" id="s-sweeps">—</div></div>
  <div class="stat-item"><div class="stat-label">Peak</div><div class="stat-val amber" id="s-peak">—</div></div>
  <div class="stat-item"><div class="stat-label">Average</div><div class="stat-val" id="s-avg">—</div></div>
  <div class="stat-item"><div class="stat-label">Sweep/s</div><div class="stat-val" id="s-rate">—</div></div>
  <div class="stat-item"><div class="stat-label">Range</div><div class="stat-val" id="s-range">—</div></div>
  <div class="stat-item"><div class="stat-label">Resolution</div><div class="stat-val" id="s-res">—</div></div>
</div>

<div id="wrap">
  <canvas id="cv-main"></canvas>
  <canvas id="cv-overlay"></canvas>
  <canvas id="cv-ui"></canvas>
</div>

<div id="freq-axis">
  <span id="ax-start">—</span>
  <span id="ax-ch1"></span>
  <span id="ax-ch6"></span>
  <span id="ax-ch11"></span>
  <span id="ax-end">—</span>
</div>

<div id="legend">
  <span>-100 dBm</span>
  <canvas id="lbar" width="200" height="10"></canvas>
  <span>0 dBm</span>
</div>

<div id="controls">
  <button id="btn-peak" class="active" onclick="togglePeak()">PEAK HOLD</button>
  <button id="btn-clear" onclick="clearPeak()">CLEAR PEAK</button>
  <span id="hover-freq" style="margin-left:10px"></span>
</div>

<script>
// ── constants ────────────────────────────────────────────────────────────────
var ROWS = 200;
var W    = Math.min(window.innerWidth - 26, 1000);
var H    = Math.round(W * 0.38);
W = Math.max(W, 400);
H = Math.max(H, 160);

// ── canvas setup ─────────────────────────────────────────────────────────────
var wrap = document.getElementById("wrap");
wrap.style.width = W + "px";

var cvMain    = document.getElementById("cv-main");
var cvOverlay = document.getElementById("cv-overlay");
var cvUI      = document.getElementById("cv-ui");
[cvMain, cvOverlay, cvUI].forEach(function(c) { c.width = W; c.height = H; });

var ctx  = cvMain.getContext("2d");
var octx = cvOverlay.getContext("2d");
var uctx = cvUI.getContext("2d");

// ── state ────────────────────────────────────────────────────────────────────
var history     = [];
var peakRow     = null;
var showPeak    = true;
var freqStart   = 2400000;
var freqEnd     = 2495000;
var sweepCount  = 0;
var rateCount   = 0;
var rateTs      = Date.now();
var sweepRate   = 0;
var redrawFlag  = false;
var ROW_H       = H / ROWS;

// ── gradient LUT ─────────────────────────────────────────────────────────────
// Matches the RGB565 LUT in spectools_waterfall_fb.py
var GRADIENT = [
  [-100, [0,   0,   0  ]],
  [ -88, [0,   0,   160]],
  [ -78, [0,   120, 220]],
  [ -70, [0,   220, 80 ]],
  [ -60, [200, 220, 0  ]],
  [ -50, [255, 140, 0  ]],
  [ -38, [255, 20,  0  ]],
  [   0, [255, 180, 220]],
];

function dbmToRgb(dbm) {
  var g = GRADIENT;
  if (dbm <= g[0][0])              return g[0][1];
  if (dbm >= g[g.length-1][0])    return g[g.length-1][1];
  for (var i = 0; i < g.length-1; i++) {
    var lo = g[i], hi = g[i+1];
    if (dbm >= lo[0] && dbm <= hi[0]) {
      var t  = (dbm - lo[0]) / (hi[0] - lo[0]);
      var lc = lo[1], hc = hi[1];
      return [
        (lc[0] + t*(hc[0]-lc[0]))|0,
        (lc[1] + t*(hc[1]-lc[1]))|0,
        (lc[2] + t*(hc[2]-lc[2]))|0
      ];
    }
  }
  return [0,0,0];
}

function resample(bins, width) {
  var n = bins.length, out = new Array(width);
  var chunk = n / width;
  for (var i = 0; i < width; i++) {
    var s = (i*chunk)|0, e = Math.max(((i+1)*chunk)|0, s+1), mx = -200;
    for (var j = s; j < e && j < n; j++) { if (bins[j] > mx) mx = bins[j]; }
    out[i] = mx;
  }
  return out;
}

// ── legend bar ───────────────────────────────────────────────────────────────
(function() {
  var lb = document.getElementById("lbar");
  var lc = lb.getContext("2d");
  var id = lc.createImageData(lb.width, lb.height);
  var d  = id.data;
  for (var x = 0; x < lb.width; x++) {
    var dbm = -100 + x / lb.width * 100;
    var c   = dbmToRgb(dbm);
    for (var y = 0; y < lb.height; y++) {
      var idx = (y*lb.width + x)*4;
      d[idx]=c[0]; d[idx+1]=c[1]; d[idx+2]=c[2]; d[idx+3]=255;
    }
  }
  lc.putImageData(id, 0, 0);
})();

// ── sweep intake ─────────────────────────────────────────────────────────────
function addSweep(bins) {
  var resampled = resample(bins, W);
  var colors    = resampled.map(dbmToRgb);
  if (history.length >= ROWS) history.shift();
  history.push({ colors: colors, raw: resampled });

  // update peak row (per-bin maximum)
  if (!peakRow) peakRow = resampled.slice();
  else for (var i = 0; i < W; i++) { if (resampled[i] > peakRow[i]) peakRow[i] = resampled[i]; }

  redrawFlag = true;
  sweepCount++;
  rateCount++;
}

// ── canvas render ─────────────────────────────────────────────────────────────
function redraw() {
  if (!redrawFlag) return;
  redrawFlag = false;

  var n      = history.length;
  var img    = ctx.createImageData(W, H);
  var d      = img.data;
  var blank  = [6, 13, 24]; // var(--bg) as rgb

  for (var row = 0; row < ROWS; row++) {
    var histIdx = n - ROWS + row;        // < 0 means empty (blank)
    var yTop = (row * ROW_H)|0;
    var yBot = ((row+1) * ROW_H)|0;
    if (yBot <= yTop) yBot = yTop + 1;
    for (var y = yTop; y < yBot && y < H; y++) {
      var base = y * W * 4;
      if (histIdx < 0) {
        for (var x = 0; x < W; x++) {
          var p = base + x*4;
          d[p]=blank[0]; d[p+1]=blank[1]; d[p+2]=blank[2]; d[p+3]=255;
        }
      } else {
        var colors = history[histIdx].colors;
        for (var x = 0; x < W; x++) {
          var c = colors[x], p = base + x*4;
          d[p]=c[0]; d[p+1]=c[1]; d[p+2]=c[2]; d[p+3]=255;
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  drawUI();
}

// ── UI overlays (channel markers, peak hold, dBm scale) ──────────────────────
function freqToX(freq) {
  return ((freq - freqStart) / (freqEnd - freqStart) * W)|0;
}

var WIFI_CHANNELS_24 = [[1,2412],[6,2437],[11,2462]];

function drawUI() {
  uctx.clearRect(0, 0, W, H);

  // Wi-Fi channel markers
  if (freqEnd - freqStart < 200000) {  // 2.4 GHz range
    WIFI_CHANNELS_24.forEach(function(ch) {
      var x = freqToX(ch[1] * 1000);
      if (x < 0 || x >= W) return;
      uctx.strokeStyle = "rgba(0,200,160,0.4)";
      uctx.lineWidth = 1;
      uctx.setLineDash([3, 4]);
      uctx.beginPath(); uctx.moveTo(x, 0); uctx.lineTo(x, H); uctx.stroke();
      uctx.setLineDash([]);
      uctx.fillStyle = "rgba(0,200,160,0.9)";
      uctx.font = "10px monospace";
      uctx.fillText("Ch" + ch[0], x + 3, 13);
    });
  }

  // dBm scale on right edge
  var dbmTicks = [-100, -80, -60, -40, -20];
  dbmTicks.forEach(function(dbm) {
    var frac = (dbm - (-100)) / 100;
    var c    = dbmToRgb(dbm);
    var yy   = (H * 0.05)|0;   // scale bar at top 5% of height
    var x    = (frac * (W - 40) + 5)|0;
    uctx.fillStyle = "rgba(" + c[0] + "," + c[1] + "," + c[2] + ",0.9)";
    uctx.font = "9px monospace";
    uctx.fillText(dbm, x, H - 5);
  });

  // Peak hold line
  if (showPeak && peakRow) {
    var peakImg = uctx.createImageData(W, 2);
    var pd = peakImg.data;
    for (var x = 0; x < W; x++) {
      var c   = dbmToRgb(peakRow[x]);
      var b   = 200;
      var idx = x * 4;
      pd[idx]=255; pd[idx+1]=b; pd[idx+2]=0; pd[idx+3]=200;
      var idx2 = W*4 + x*4;
      pd[idx2]=255; pd[idx2+1]=b; pd[idx2+2]=0; pd[idx2+3]=100;
    }
    uctx.putImageData(peakImg, 0, H - 4);
    // label
    uctx.fillStyle = "rgba(255,180,0,0.8)";
    uctx.font = "9px monospace";
    uctx.fillText("PEAK", W - 36, H - 7);
  }
}

// ── stats update ──────────────────────────────────────────────────────────────
setInterval(function() {
  var now = Date.now();
  var dt  = (now - rateTs) / 1000;
  if (dt >= 1) {
    sweepRate = (rateCount / dt).toFixed(1);
    rateCount = 0;
    rateTs    = now;
  }
  if (sweepCount > 0) {
    document.getElementById("s-sweeps").textContent = sweepCount;
    document.getElementById("s-rate").textContent   = sweepRate + "/s";
  }
}, 500);

setInterval(redraw, 80);   // ~12fps max

// ── crosshair on hover ────────────────────────────────────────────────────────
cvOverlay.addEventListener("mousemove", function(e) {
  var r    = cvOverlay.getBoundingClientRect();
  var x    = ((e.clientX - r.left) * W / r.width)|0;
  var freq = freqStart + (freqEnd - freqStart) * x / W;
  var mhz  = (freq / 1000).toFixed(2);

  octx.clearRect(0, 0, W, H);
  octx.strokeStyle = "rgba(255,255,255,0.25)";
  octx.lineWidth   = 1;
  octx.beginPath(); octx.moveTo(x, 0); octx.lineTo(x, H); octx.stroke();

  // dBm at cursor from most recent sweep
  var dbmStr = "";
  if (history.length > 0) {
    var last = history[history.length-1].raw;
    if (x >= 0 && x < last.length) dbmStr = " · " + last[x].toFixed(0) + " dBm";
  }

  var lbl = mhz + " MHz" + dbmStr;
  octx.font = "11px monospace";
  var tw  = octx.measureText(lbl).width + 10;
  var lx  = x + 8;
  if (lx + tw > W) lx = x - tw - 4;
  octx.fillStyle   = "rgba(5,13,24,0.85)";
  octx.fillRect(lx - 3, 4, tw, 17);
  octx.strokeStyle = "rgba(0,200,160,0.4)";
  octx.lineWidth   = 1;
  octx.strokeRect(lx - 3, 4, tw, 17);
  octx.fillStyle   = "#00e8c0";
  octx.fillText(lbl, lx, 17);

  document.getElementById("hover-freq").textContent = mhz + " MHz" + dbmStr;
});
cvOverlay.addEventListener("mouseleave", function() {
  octx.clearRect(0, 0, W, H);
  document.getElementById("hover-freq").textContent = "";
});

// ── freq axis ────────────────────────────────────────────────────────────────
function updateFreqAxis(fs, fe) {
  freqStart = fs; freqEnd = fe;
  document.getElementById("ax-start").textContent = (fs/1000).toFixed(0) + " MHz";
  document.getElementById("ax-end").textContent   = (fe/1000).toFixed(0) + " MHz";
  document.getElementById("s-range").textContent  =
    (fs/1000).toFixed(0) + "–" + (fe/1000).toFixed(0) + " MHz";
  if (fe - fs < 200000) {
    document.getElementById("ax-ch1").textContent  = "Ch 1";
    document.getElementById("ax-ch6").textContent  = "Ch 6";
    document.getElementById("ax-ch11").textContent = "Ch 11";
  } else {
    document.getElementById("ax-ch1").textContent  = "";
    document.getElementById("ax-ch6").textContent  = "";
    document.getElementById("ax-ch11").textContent = "";
  }
}

// ── peak hold controls ────────────────────────────────────────────────────────
function togglePeak() {
  showPeak = !showPeak;
  document.getElementById("btn-peak").classList.toggle("active", showPeak);
  redrawFlag = true;
}
function clearPeak() {
  peakRow = null;
  redrawFlag = true;
}

// ── SSE connection ────────────────────────────────────────────────────────────
var dot   = document.getElementById("conn-dot");
var clbl  = document.getElementById("conn-label");
var es;

function setConn(state) {
  dot.className  = "conn-dot" + (state === "live" ? " live" : state === "error" ? " error" : "");
  clbl.textContent = state === "live" ? "LIVE" : state === "error" ? "OFFLINE" : "CONNECTING";
  clbl.style.color = state === "live" ? "var(--teal)" : state === "error" ? "var(--red)" : "var(--gray)";
}

function connect() {
  if (es) { try { es.close(); } catch(e) {} }
  setConn("connecting");
  es = new EventSource("/events");
  es.onopen = function() { setConn("live"); };
  es.onmessage = function(e) {
    try {
      var data = JSON.parse(e.data);
      if (data.type === "device_config") {
        updateFreqAxis(data.freq_start_khz, data.freq_end_khz);
        if (data.res_hz) {
          document.getElementById("s-res").textContent = (data.res_hz/1000).toFixed(0) + " kHz";
        }
      } else if (data.type === "sweep") {
        if (data.freq_start_khz) updateFreqAxis(data.freq_start_khz, data.freq_end_khz);
        if (data.rssi_bins && data.rssi_bins.length) {
          addSweep(data.rssi_bins);
          if (data.stats) {
            var pk = data.stats.max, av = data.stats.avg;
            if (pk != null) {
              var el = document.getElementById("s-peak");
              el.textContent = pk.toFixed(0) + " dBm";
              el.className   = "stat-val " + (pk > -60 ? "red" : pk > -75 ? "amber" : "");
            }
            if (av != null) {
              document.getElementById("s-avg").textContent = av.toFixed(0) + " dBm";
            }
          }
        }
      }
    } catch(ex) {}
  };
  es.onerror = function() {
    setConn("error");
    es.close();
    setTimeout(connect, 3000);
  };
}
connect();
</script>
</body>
</html>'''


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access log noise in device logs

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._serve_index()
        elif self.path == '/events':
            self._serve_sse()
        else:
            self.send_error(404)

    def _serve_index(self):
        body = _HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _serve_sse(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        path = Path(_events_file)
        deadline = time.monotonic() + 30
        while not path.exists():
            if _stop_event.is_set() or time.monotonic() > deadline:
                return
            time.sleep(0.3)

        try:
            with path.open('r', encoding='utf-8', errors='replace') as fh:
                while not _stop_event.is_set():
                    raw = fh.readline()
                    if not raw:
                        time.sleep(0.05)
                        continue
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    try:
                        evt = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if evt.get('type') in ('sweep', 'device_config', 'status', 'error'):
                        try:
                            msg = 'data: ' + json.dumps(evt) + '\n\n'
                            self.wfile.write(msg.encode('utf-8'))
                            self.wfile.flush()
                        except OSError:
                            return
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    global _events_file

    p = argparse.ArgumentParser(description='SpecPine HTTP waterfall server')
    p.add_argument('--events-file', default='/tmp/specpine_events.jsonl')
    p.add_argument('--port', type=int, default=8080)
    p.add_argument('--host', default='0.0.0.0')
    args = p.parse_args(argv)

    _events_file = args.events_file

    server = _ThreadingHTTPServer((args.host, args.port), _Handler)

    def _shutdown(signum, frame):
        _stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    sys.stderr.write(f'SpecPine waterfall HTTP server listening on :{args.port}\n')
    sys.stderr.flush()
    server.serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
