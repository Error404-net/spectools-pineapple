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

_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpecPine Waterfall</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#060e18;color:#00e8a0;font-family:monospace;padding:12px}
h1{font-size:13px;letter-spacing:3px;margin-bottom:6px;color:#00ffc8}
#meta{font-size:11px;color:#4a7090;margin-bottom:8px;height:16px}
#wrap{position:relative;display:inline-block}
canvas{display:block;border:1px solid #1a3050}
#overlay{position:absolute;top:0;left:0;pointer-events:none}
#axis{display:flex;justify-content:space-between;font-size:10px;color:#3a6080;
      margin-top:3px;width:600px}
#legend{display:flex;align-items:center;margin-top:8px;font-size:10px;
        color:#3a6080;gap:8px}
#lbar{width:200px;height:10px;border:1px solid #1a3050}
</style>
</head>
<body>
<h1>&#x25a0; SPECPINE WATERFALL &#x25a0;</h1>
<div id="meta">Connecting to device...</div>
<div id="wrap">
  <canvas id="wf" width="600" height="300"></canvas>
  <canvas id="overlay" width="600" height="300"></canvas>
</div>
<div id="axis">
  <span id="a-start">&#8212;</span>
  <span id="a-ch1"></span>
  <span id="a-ch6"></span>
  <span id="a-ch11"></span>
  <span id="a-end">&#8212;</span>
</div>
<div id="legend">
  <span>-100</span><canvas id="lbar"></canvas><span>0 dBm</span>
</div>

<script>
var WF  = document.getElementById("wf");
var OV  = document.getElementById("overlay");
var ctx = WF.getContext("2d");
var octx= OV.getContext("2d");
var W   = WF.width, H = WF.height;
var ROWS = 150;
var ROW_H = H / ROWS;
var history = [];
var freqStart = 2400000, freqEnd = 2495000;
var sweepCount = 0;
var redrawNeeded = false;

// Draw color legend bar
(function(){
  var lb = document.getElementById("lbar");
  var lc = lb.getContext("2d");
  var g  = lc.createLinearGradient(0,0,lb.width,0);
  g.addColorStop(0,    "rgb(0,0,0)");
  g.addColorStop(0.15, "rgb(0,0,180)");
  g.addColorStop(0.35, "rgb(0,200,180)");
  g.addColorStop(0.55, "rgb(0,200,0)");
  g.addColorStop(0.70, "rgb(255,200,0)");
  g.addColorStop(0.85, "rgb(255,100,0)");
  g.addColorStop(1.0,  "rgb(255,255,255)");
  lc.fillStyle = g;
  lc.fillRect(0,0,lb.width,lb.height);
})();

function dbmToRgb(dbm) {
  var t = Math.max(0, Math.min(1, (dbm + 100) / 100));
  var s;
  if (t < 0.15) {
    s = t / 0.15;
    return [0, 0, (s*180)|0];
  } else if (t < 0.35) {
    s = (t-0.15)/0.20;
    return [0, (s*200)|0, 180];
  } else if (t < 0.55) {
    s = (t-0.35)/0.20;
    return [0, 200, ((1-s)*180)|0];
  } else if (t < 0.70) {
    s = (t-0.55)/0.15;
    return [(s*255)|0, 200, 0];
  } else if (t < 0.85) {
    s = (t-0.70)/0.15;
    return [255, ((1-s*0.5)*200)|0, 0];
  } else {
    s = (t-0.85)/0.15;
    return [255, (s*255)|0, (s*255)|0];
  }
}

function resample(bins, width) {
  var out = [];
  var chunk = bins.length / width;
  for (var i = 0; i < width; i++) {
    var s = (i*chunk)|0;
    var e = Math.max(((i+1)*chunk)|0, s+1);
    var mx = -200;
    for (var j = s; j < e && j < bins.length; j++) {
      if (bins[j] > mx) mx = bins[j];
    }
    out.push(mx);
  }
  return out;
}

function addSweep(bins) {
  if (history.length >= ROWS) history.shift();
  history.push(resample(bins, W).map(dbmToRgb));
  redrawNeeded = true;
}

function updateFreqAxis(fs, fe) {
  freqStart = fs; freqEnd = fe;
  document.getElementById("a-start").textContent = ((fs/1000)|0) + " MHz";
  document.getElementById("a-end").textContent   = ((fe/1000)|0) + " MHz";
  if (fs < 3000000) {
    var span = fe - fs;
    document.getElementById("a-ch1").textContent  = "Ch1";
    document.getElementById("a-ch6").textContent  = "Ch6";
    document.getElementById("a-ch11").textContent = "Ch11";
  }
}

function redraw() {
  if (!redrawNeeded) return;
  redrawNeeded = false;
  var img = ctx.createImageData(W, H);
  var d   = img.data;
  var n   = history.length;
  var startRow = ROWS - n;
  for (var i = 0; i < n; i++) {
    var colors = history[i];
    var yTop = ((startRow + i)     * ROW_H)|0;
    var yBot = ((startRow + i + 1) * ROW_H)|0;
    if (yBot <= yTop) yBot = yTop + 1;
    for (var y = yTop; y < yBot && y < H; y++) {
      for (var x = 0; x < W; x++) {
        var c   = colors[x];
        var idx = (y*W + x)*4;
        d[idx]   = c[0];
        d[idx+1] = c[1];
        d[idx+2] = c[2];
        d[idx+3] = 255;
      }
    }
  }
  ctx.putImageData(img, 0, 0);
}

setInterval(redraw, 100);

// Crosshair on hover
OV.addEventListener("mousemove", function(e) {
  var r = OV.getBoundingClientRect();
  var x = ((e.clientX - r.left) / r.width * W)|0;
  var freq = freqStart + (freqEnd - freqStart) * (x / W);
  var mhz  = (freq / 1000).toFixed(1);
  octx.clearRect(0,0,W,H);
  octx.strokeStyle = "rgba(255,255,255,0.35)";
  octx.lineWidth = 1;
  octx.beginPath(); octx.moveTo(x,0); octx.lineTo(x,H); octx.stroke();
  octx.fillStyle  = "rgba(0,0,0,0.6)";
  var lbl = mhz + " MHz";
  octx.font = "11px monospace";
  var lx = x + 5;
  if (lx + 75 > W) lx = x - 75;
  octx.fillRect(lx-2, 4, 74, 16);
  octx.fillStyle = "#00ffc8";
  octx.fillText(lbl, lx, 16);
});
OV.addEventListener("mouseleave", function() { octx.clearRect(0,0,W,H); });

// SSE connection with auto-reconnect
var es;
function connect() {
  if (es) { try { es.close(); } catch(e) {} }
  es = new EventSource("/events");
  es.onopen = function() {
    document.getElementById("meta").textContent = "Connected - waiting for sweeps...";
  };
  es.onmessage = function(e) {
    try {
      var data = JSON.parse(e.data);
      if (data.type === "sweep") {
        sweepCount++;
        var pk = (data.stats && data.stats.max != null) ? data.stats.max : "?";
        var av = (data.stats && data.stats.avg != null) ? data.stats.avg : "?";
        document.getElementById("meta").textContent =
          "Sweep #" + sweepCount + "  |  Peak: " + pk + " dBm  |  Avg: " + av + " dBm";
        if (data.freq_start_khz) updateFreqAxis(data.freq_start_khz, data.freq_end_khz);
        addSweep(data.rssi_bins);
      } else if (data.type === "device_config") {
        updateFreqAxis(data.freq_start_khz, data.freq_end_khz);
      }
    } catch(ex) {}
  };
  es.onerror = function() {
    document.getElementById("meta").textContent = "Connection lost - retrying in 3s...";
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
