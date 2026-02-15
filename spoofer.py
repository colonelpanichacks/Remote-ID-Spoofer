#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
import serial, json, glob, csv, time, threading
import serial.tools.list_ports as list_ports
from datetime import datetime
import atexit

ASCII_ART = r"""
       _____                .__              ________          __                 __     
      /     \   ____   _____|  |__           \______ \   _____/  |_  ____   _____/  |_   
     /  \ /  \_/ __ \ /  ___/  |  \   ______  |    |  \_/ __ \   __\/ __ \_/ ___\   __\  
    /    Y    \  ___/ \___ \|   Y  \ /_____/  |    `   \  ___/|  | \  ___/\  \___|  |    
    \____|__  /\___  >____  >___|  /         /_______  /\___  >__|  \___  >\___  >__|    
            \/     \/     \/     \/                  \/     \/          \/     \/        
________                                 _________                     _____             
\______ \_______  ____   ____   ____    /   _____/_____   ____   _____/ ____\___________ 
 |    |  \_  __ \/  _ \ /    \_/ __ \   \_____  \\____ \ /  _ \ /  _ \   __\/ __ \_  __ \
 |    `   \  | \(  <_> )   |  \  ___/   /        \  |_> >  <_> |  <_> )  | \  ___/|  | \/
/_______  /__|   \____/|___|  /\___  > /_______  /   __/ \____/ \____/|__|  \___  >__|   
        \/                  \/     \/          \/|__|                           \/       
"""

app = Flask(__name__)

BAUD_RATE = 115200
MAX_BOARDS = 3

# multi-board state: list of dicts {port, ser, lock, label}
boards = []
boards_lock = threading.Lock()

def cleanup_boards():
    for b in boards:
        try:
            if b['ser'] and b['ser'].is_open:
                b['ser'].close()
        except Exception:
            pass
atexit.register(cleanup_boards)

PATH_CSV = "paths.csv"
try:
    with open(PATH_CSV, 'x', newline='') as f:
        csv.writer(f).writerow(['timestamp', 'path'])
except FileExistsError:
    pass

mission = {"basic_id": "", "drone_altitude": 0, "path": []}
play_active = False

PORT_SELECT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Drone Spoofer</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #000; color: #0f0;
      font-family: 'Courier New', monospace;
      min-height: 100vh; min-height: -webkit-fill-available;
      display: flex; align-items: center; justify-content: center;
      overflow-x: hidden; overflow-y: auto; padding: 20px;
    }
    html { height: -webkit-fill-available; }
    body::before {
      content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0px, rgba(0,0,0,0) 2px, rgba(0,0,0,0.15) 2px, rgba(0,0,0,0.15) 4px);
      pointer-events: none; z-index: 999;
    }
    body::after {
      content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,0.7) 100%);
      pointer-events: none; z-index: 998;
    }
    .container {
      position: relative; z-index: 10; text-align: center;
      padding: 60px 70px; border: 1px solid rgba(0,255,0,0.15); border-radius: 6px;
      background: rgba(0,20,0,0.4);
      box-shadow: 0 0 80px rgba(0,255,0,0.06), inset 0 0 80px rgba(0,255,0,0.02);
      max-width: 1100px; width: 100%;
    }
    pre {
      font-size: clamp(7px, 1.5vw, 14px); line-height: 1.2; margin-bottom: 40px;
      color: #0f0; text-shadow: 0 0 8px rgba(0,255,0,0.6), 0 0 20px rgba(0,255,0,0.2);
      animation: textFlicker 4s infinite alternate;
      white-space: pre; text-align: left; display: inline-block;
      overflow-x: auto; max-width: 100%;
    }
    @keyframes textFlicker { 0%,95%,100%{opacity:1;} 96%{opacity:0.85;} 97%{opacity:1;} 98%{opacity:0.9;} }
    .subtitle { font-size: clamp(18px,2.5vw,28px); color: #ff00ff; text-transform: uppercase; letter-spacing: 8px; margin-bottom: 12px; text-shadow: 0 0 10px rgba(255,0,255,0.5); }
    .version { font-size: clamp(16px,1.8vw,22px); color: rgba(0,255,0,0.35); margin-bottom: 40px; letter-spacing: 3px; }
    .divider { height: 1px; background: linear-gradient(90deg, transparent, #0f0, transparent); margin: 30px 0; opacity: 0.3; }
    h2 { font-size: clamp(16px,2.2vw,24px); font-weight: normal; color: #7df9ff; text-transform: uppercase; letter-spacing: 4px; margin-bottom: 24px; text-shadow: 0 0 10px rgba(125,249,255,0.3); }
    form { display: flex; flex-direction: column; align-items: center; gap: 20px; width: 100%; }
    select {
      width: 100%; max-width: 560px; background: rgba(0,20,0,0.8); color: #0f0;
      border: 1px solid rgba(0,255,0,0.3); padding: 18px 22px;
      font-family: 'Courier New', monospace; font-size: clamp(16px,1.8vw,22px);
      cursor: pointer; appearance: none; -webkit-appearance: none; outline: none; transition: all 0.2s;
    }
    select:hover, select:focus { border-color: #0f0; box-shadow: 0 0 15px rgba(0,255,0,0.15); }
    select option { background: #000; color: #0f0; }
    button {
      width: 100%; max-width: 560px; background: transparent; color: #ff00ff;
      border: 1px solid #ff00ff; padding: 18px 22px;
      font-family: 'Courier New', monospace; font-size: clamp(16px,1.8vw,22px);
      text-transform: uppercase; letter-spacing: 4px; cursor: pointer; transition: all 0.2s;
    }
    button:hover { background: rgba(255,0,255,0.1); box-shadow: 0 0 20px rgba(255,0,255,0.2); text-shadow: 0 0 8px rgba(255,0,255,0.5); }
    .status-bar { margin-top: 40px; font-size: clamp(16px,1.6vw,20px); color: rgba(0,255,0,0.25); letter-spacing: 2px; }
    .blink { animation: blink 1.2s steps(1) infinite; }
    @keyframes blink { 0%,50%{opacity:1;} 51%,100%{opacity:0;} }
    .particle { position: fixed; width: 1px; height: 1px; background: rgba(0,255,0,0.4); pointer-events: none; z-index: 1; }
    .gh-link { color: rgba(0,255,0,0.5); font-size: clamp(15px,1.6vw,20px); letter-spacing: 1.5px; text-decoration: none; border-bottom: 1px solid rgba(0,255,0,0.15); }
    .gh-link:hover { color: #0f0; border-color: rgba(0,255,0,0.4); }
    @media (max-width: 600px) {
      .container { padding: 28px 20px; }
      pre { font-size: clamp(4px, 3vw, 9px); margin-bottom: 24px; }
      .subtitle { letter-spacing: 4px; font-size: 18px; }
      h2 { letter-spacing: 2px; font-size: 16px; }
      button, select { padding: 16px 18px; font-size: 16px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <pre>{{ ascii_art }}</pre>
    <div class="subtitle"><a href="https://colonelpanic.tech" target="_blank" style="color:#ff00ff; text-decoration:none;">colonelpanic.tech</a></div>
    <div class="version">// remote id spoofing system v2.0</div>
    <div style="margin:16px 0;">
      <a href="https://github.com/colonelpanic/Remote-ID-Spoofer" target="_blank" class="gh-link">github.com/colonelpanic/Remote-ID-Spoofer</a>
    </div>
    <div style="margin:16px 0 12px;font-size:clamp(14px,1.6vw,19px);color:rgba(125,249,255,0.45);letter-spacing:1.5px;">
      inspired by <a href="https://github.com/d0tslash" target="_blank" style="color:#7DF9FF;text-decoration:none;border-bottom:1px solid rgba(125,249,255,0.25);">d0tslash</a> &amp; <span style="color:#ff00ff;">H.A.R.D</span> <span style="color:rgba(255,255,255,0.35);">// Hackers Against Remote ID</span>
    </div>
    <div class="divider"></div>
    <h2>Serial Interfaces // Up to 3 boards</h2>
    <form method="post" style="gap:14px;">
      {% for i in range(3) %}
      <div style="display:flex;gap:10px;align-items:center;width:100%;max-width:660px;">
        <span style="color:#ff00ff;font-size:clamp(14px,1.6vw,18px);white-space:nowrap;min-width:80px;text-align:right;">BOARD {{ i+1 }}</span>
        <select name="port_{{ i }}" style="flex:1;font-size:clamp(14px,1.4vw,18px);padding:14px 16px;">
          <option value="">[ NONE ]</option>
          {% for p in ports %}
            <option value="{{ p }}" {% if active_ports[i]==p %}selected{% endif %}>{{ p }}</option>
          {% endfor %}
        </select>
        <select name="label_{{ i }}" style="width:120px;font-size:clamp(12px,1.2vw,16px);padding:14px 10px;color:#7DF9FF;border-color:rgba(125,249,255,0.3);background:rgba(0,20,0,0.8);">
          <option value="S3" {% if active_labels[i]=='S3' %}selected{% endif %}>ESP32-S3</option>
          <option value="C5" {% if active_labels[i]=='C5' %}selected{% endif %}>ESP32-C5</option>
        </select>
      </div>
      {% endfor %}
      <button type="submit" style="padding:28px 60px;font-size:clamp(22px,3vw,36px);letter-spacing:6px;max-width:660px;">LAUNCH MAP</button>
    </form>
    {% if boards_connected > 0 %}
    <div class="status-bar" style="color:#0f0;">
      {{ boards_connected }} BOARD{{ 'S' if boards_connected > 1 else '' }} CONNECTED <span class="blink">_</span>
    </div>
    {% else %}
    <div class="status-bar">
      SYS.READY <span class="blink">_</span>
    </div>
    {% endif %}
  </div>
  <script>
    for (var i = 0; i < 40; i++) {
      var p = document.createElement('div');
      p.className = 'particle';
      p.style.left = Math.random()*100+'vw';
      p.style.top = Math.random()*100+'vh';
      p.style.opacity = Math.random()*0.4+0.1;
      document.body.appendChild(p);
      (function(el){
        var dur = 8000+Math.random()*12000;
        el.animate([
          {transform:'translateY(0)',opacity:0},
          {opacity:parseFloat(el.style.opacity)},
          {transform:'translateY(-100vh)',opacity:0}
        ],{duration:dur,iterations:Infinity});
      })(p);
    }
  </script>
</body>
</html>
"""

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Drone Spoofer</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap');
  *{box-sizing:border-box;margin:0;padding:0;}
  body,html{height:100%;background:#0a0a0f;color:#c0ffc0;font-family:'JetBrains Mono','Courier New',monospace;overflow:hidden;}
  #map{position:absolute;top:0;bottom:0;left:0;right:0;z-index:1;}
  .leaflet-container{background:#0a0a0f!important;}
  .leaflet-control-attribution{display:none!important;}
  .leaflet-control-zoom{border:none!important;}
  .leaflet-control-zoom a{background:rgba(10,10,15,0.9)!important;color:#7DF9FF!important;border:1px solid rgba(125,249,255,0.2)!important;font-family:'JetBrains Mono',monospace!important;}
  .leaflet-control-zoom a:hover{background:rgba(125,249,255,0.1)!important;border-color:#7DF9FF!important;}

  /* ── panels ── */
  .side-panel{
    position:absolute;top:10px;bottom:10px;width:400px;z-index:1000;
    background:rgba(6,8,16,0.95);
    border:1px solid rgba(125,249,255,0.1);border-radius:10px;
    display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 0 40px rgba(0,0,0,0.6);
    backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  }
  .side-panel.left{left:10px;}
  .side-panel.right{right:10px;}
  .panel-title{
    font-size:16px;font-weight:600;letter-spacing:5px;text-transform:uppercase;
    color:rgba(125,249,255,0.6);text-align:center;padding:14px 20px 12px;
    border-bottom:1px solid rgba(125,249,255,0.08);flex-shrink:0;
  }
  .panel-body{
    flex:1;overflow-y:auto;overflow-x:hidden;padding:14px 22px 18px;
    scrollbar-width:thin;scrollbar-color:rgba(125,249,255,0.1) transparent;
  }
  .panel-body::-webkit-scrollbar{width:4px;}
  .panel-body::-webkit-scrollbar-thumb{background:rgba(125,249,255,0.15);border-radius:4px;}

  #serialStatus{
    position:absolute;bottom:12px;left:50%;transform:translateX(-50%);
    background:rgba(6,8,16,0.92);
    padding:8px 16px;border:1px solid rgba(125,249,255,0.1);border-radius:6px;
    font-family:'JetBrains Mono',monospace;font-size:12px;z-index:1000;
    box-shadow:0 4px 20px rgba(0,0,0,0.5);backdrop-filter:blur(8px);
    display:flex;gap:14px;align-items:center;
  }
  .board-pill{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:4px;border:1px solid rgba(125,249,255,0.12);background:rgba(0,0,0,0.3);}
  .board-pill .dot{width:6px;height:6px;border-radius:50%;display:inline-block;}
  .board-pill .dot.on{background:lime;box-shadow:0 0 6px lime;}
  .board-pill .dot.off{background:#ff3333;box-shadow:0 0 6px #ff3333;}
  .board-row{display:flex;align-items:center;gap:8px;padding:6px 10px;margin-bottom:4px;border:1px solid rgba(125,249,255,0.08);border-radius:5px;background:rgba(0,0,0,0.25);}
  .board-row .b-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
  .board-row .b-dot.on{background:lime;box-shadow:0 0 8px lime;}
  .board-row .b-dot.off{background:#ff3333;box-shadow:0 0 8px #ff3333;}
  .board-row .b-label{font-size:13px;font-weight:600;letter-spacing:1px;min-width:48px;}
  .board-row .b-port{font-size:11px;color:rgba(255,255,255,0.35);flex:1;text-align:right;}

  /* ── form elements ── */
  .field-label{
    display:block;margin:8px 0 4px;font-size:14px;font-weight:500;
    letter-spacing:1px;text-transform:uppercase;color:rgba(255,0,255,0.65);
  }
  .field-input{
    display:block;width:100%;padding:12px 14px;
    background:rgba(0,0,0,0.35);color:#c0ffc0;
    border:1px solid rgba(125,249,255,0.12);border-radius:6px;
    font-family:'JetBrains Mono',monospace;font-size:17px;
    outline:none;transition:border-color 0.2s;
  }
  .field-input:focus{border-color:rgba(125,249,255,0.4);}
  .field-input::placeholder{color:rgba(125,249,255,0.18);}

  .side-panel button{
    display:block;width:100%;margin:4px 0;
    background:transparent;padding:12px;font-size:15px;font-weight:500;
    font-family:'JetBrains Mono',monospace;cursor:pointer;letter-spacing:1.5px;
    text-transform:uppercase;border-radius:6px;transition:all 0.15s ease;
  }
  .btn-pilot{background:rgba(255,0,255,0.04)!important;border:1px solid rgba(255,0,255,0.25)!important;color:#FF00FF!important;}
  .btn-pilot:hover{background:rgba(255,0,255,0.1)!important;border-color:#FF00FF!important;box-shadow:0 0 12px rgba(255,0,255,0.12)!important;}
  .btn-play{background:rgba(0,200,0,0.04)!important;border:1px solid rgba(0,200,0,0.25)!important;color:#00cc00!important;}
  .btn-play:hover{background:rgba(0,200,0,0.1)!important;border-color:#00cc00!important;box-shadow:0 0 12px rgba(0,200,0,0.12)!important;}
  .btn-pause{background:rgba(255,165,0,0.04)!important;border:1px solid rgba(255,165,0,0.25)!important;color:#ffa500!important;}
  .btn-pause:hover{background:rgba(255,165,0,0.1)!important;border-color:#ffa500!important;box-shadow:0 0 12px rgba(255,165,0,0.12)!important;}
  .btn-stop{background:rgba(255,50,50,0.04)!important;border:1px solid rgba(255,50,50,0.25)!important;color:#ff3333!important;}
  .btn-stop:hover{background:rgba(255,50,50,0.1)!important;border-color:#ff3333!important;box-shadow:0 0 12px rgba(255,50,50,0.12)!important;}
  .btn-clear{background:rgba(255,0,255,0.03)!important;border:1px solid rgba(255,0,255,0.15)!important;color:#FF00FF!important;font-size:13px;padding:9px;}
  .btn-clear:hover{background:rgba(255,0,255,0.08)!important;border-color:#FF00FF!important;}

  @keyframes flashPurple{0%{background-color:rgba(255,0,255,0.15);}100%{background-color:transparent;}}
  .flashPurple{animation:flashPurple 0.3s ease;}

  /* ── section dividers ── */
  .section-title{
    font-size:13px;font-weight:600;letter-spacing:2.5px;text-transform:uppercase;
    color:#7DF9FF;padding:8px 0 5px;margin-top:10px;
    border-top:1px solid rgba(125,249,255,0.08);
  }
  .divider{height:1px;background:rgba(125,249,255,0.06);margin:5px 0;}

  /* ── control row: label + toggle + slider + value, all on one line ── */
  .ctrl-row{
    display:flex;align-items:center;gap:10px;
    margin:8px 0;width:100%;
  }
  .ctrl-row .cr-label{
    flex:0 0 auto;font-size:15px;font-weight:400;
    color:rgba(255,255,255,0.55);white-space:nowrap;
    text-transform:uppercase;letter-spacing:0.5px;
  }
  .ctrl-row .toggle-btn{margin:0;}
  .ctrl-row input[type="range"]{
    flex:1 1 0;min-width:0;height:8px;
    -webkit-appearance:none;appearance:none;
    background:rgba(125,249,255,0.1);border:none;border-radius:4px;
    outline:none;padding:0;margin:0;
  }
  .ctrl-row input[type="range"]::-webkit-slider-thumb{
    -webkit-appearance:none;width:22px;height:22px;border-radius:50%;
    background:#7DF9FF;cursor:pointer;box-shadow:0 0 10px rgba(125,249,255,0.4);
  }
  .ctrl-row .cr-val{
    flex:0 0 48px;text-align:right;font-size:15px;
    color:rgba(0,255,0,0.6);font-weight:400;
  }

  /* ── toggle button ── */
  .toggle-btn{
    display:inline-block;padding:7px 16px;font-family:'JetBrains Mono',monospace;
    font-size:13px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
    cursor:pointer;border-radius:5px;transition:all 0.15s ease;user-select:none;flex-shrink:0;
    background:rgba(255,50,50,0.05);border:1px solid rgba(255,50,50,0.3);color:#ff4444;
    line-height:1;
  }
  .toggle-btn.on{
    background:rgba(0,255,136,0.08);border:1px solid rgba(0,255,136,0.4);color:#00ff88;
    box-shadow:0 0 10px rgba(0,255,136,0.1);
  }
  .toggle-btn:hover{filter:brightness(1.25);}
  .ch-toggle{padding:5px 10px;font-size:12px;letter-spacing:0.5px;min-width:44px;text-align:center;}

  /* ── option row (label + dropdown) ── */
  .opt-row{
    display:flex;align-items:center;justify-content:space-between;
    margin:8px 0;gap:10px;
  }
  .opt-row .cr-label{
    flex:1;font-size:15px;font-weight:400;
    color:rgba(255,255,255,0.55);white-space:nowrap;
    text-transform:uppercase;letter-spacing:0.5px;
  }
  .opt-row select{
    flex:0 1 auto;max-width:55%;padding:9px 12px;font-size:15px;
    background:rgba(0,0,0,0.35);color:#c0ffc0;
    border:1px solid rgba(125,249,255,0.12);border-radius:5px;
    font-family:'JetBrains Mono',monospace;outline:none;
  }

  /* ── telemetry feed ── */
  .telem-box{
    margin-top:10px;padding:10px 12px;
    background:rgba(0,0,0,0.3);border:1px solid rgba(0,255,0,0.1);border-radius:6px;
  }
  .telem-box .telem-title{
    font-size:10px;font-weight:600;letter-spacing:2px;text-transform:uppercase;
    color:rgba(0,255,0,0.4);margin-bottom:6px;
  }
  .telem-grid{
    display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;
  }
  .telem-item{display:flex;justify-content:space-between;align-items:center;padding:2px 0;}
  .telem-item .tl{font-size:11px;color:rgba(125,249,255,0.4);text-transform:uppercase;letter-spacing:0.5px;}
  .telem-item .tv{font-size:13px;color:#00ff88;font-weight:500;font-variant-numeric:tabular-nums;}
  .telem-item .tv.warn{color:#ffa500;}
  .telem-box.idle .tv{color:rgba(255,255,255,0.15);}

  /* ── swarm telemetry ── */
  .swarm-telem{margin-top:8px;}
  .swarm-telem-row{
    display:flex;align-items:center;gap:6px;padding:3px 0;
    font-size:11px;border-bottom:1px solid rgba(125,249,255,0.03);
  }
  .swarm-telem-row .st-id{flex:0 0 70px;color:rgba(255,0,255,0.5);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .swarm-telem-row .st-val{flex:1;color:rgba(0,255,0,0.5);font-variant-numeric:tabular-nums;text-align:right;}
  .swarm-telem-row.active .st-val{color:#00ff88;}
  .swarm-telem-row.active .st-id{color:#FF00FF;}

  /* ── swarm drone list ── */
  #swarmDroneList{margin:6px 0;overflow-y:visible;}
  .swarm-drone-row{display:flex;align-items:center;gap:8px;margin:4px 0;padding:8px 10px;background:rgba(125,249,255,0.02);border:1px solid rgba(125,249,255,0.06);border-radius:5px;transition:border-color 0.15s;}
  .swarm-drone-row:hover{border-color:rgba(125,249,255,0.15);}
  .swarm-drone-row .drone-idx{width:28px;text-align:center;flex-shrink:0;font-weight:600;font-size:14px;}
  .swarm-drone-row input{flex:1;background:rgba(0,0,0,0.3)!important;border:1px solid rgba(125,249,255,0.08)!important;border-radius:5px;color:#c0ffc0;padding:8px 10px;font-family:'JetBrains Mono',monospace;font-size:14px;min-width:0;outline:none;}
  .swarm-drone-row .drone-status{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,0.1);flex-shrink:0;transition:all 0.2s;}
  .swarm-drone-row .drone-status.active{background:#00ff88;box-shadow:0 0 10px rgba(0,255,136,0.5);}

  /* ── status ticker ── */
  #statusTicker{
    display:none;position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:999;
    background:rgba(10,0,0,0.85);
    border:1px solid rgba(255,0,0,0.35);border-radius:6px;
    padding:8px 24px;
    font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;
    letter-spacing:2px;text-transform:uppercase;
    color:#ff2222;white-space:nowrap;
    box-shadow:0 0 20px rgba(255,0,0,0.15),inset 0 0 30px rgba(255,0,0,0.03);
    backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
    animation:tickerPulse 1.5s ease-in-out infinite;
  }
  #statusTicker.paused{
    color:#ffa500;border-color:rgba(255,165,0,0.35);
    box-shadow:0 0 20px rgba(255,165,0,0.12),inset 0 0 30px rgba(255,165,0,0.02);
    animation:none;
  }
  #statusTicker .ticker-dot{
    display:inline-block;width:8px;height:8px;border-radius:50%;
    margin-right:10px;vertical-align:middle;
    background:#ff2222;box-shadow:0 0 8px rgba(255,0,0,0.5);
  }
  #statusTicker.paused .ticker-dot{
    background:#ffa500;box-shadow:0 0 8px rgba(255,165,0,0.5);
  }
  @keyframes tickerPulse{
    0%,100%{opacity:1;}
    50%{opacity:0.7;}
  }

  /* ── panel toggle (mobile) ── */
  #panelToggle{
    display:none;position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1001;
    background:rgba(6,8,16,0.95);
    border:1px solid rgba(125,249,255,0.15);color:#7DF9FF;padding:12px 24px;
    font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:500;
    letter-spacing:1.5px;cursor:pointer;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.5);
    backdrop-filter:blur(8px);
  }

  /* ── responsive ── */
  @media(max-width:1300px){.side-panel{width:350px;}}
  @media(max-width:1050px){.side-panel{width:300px;}.ctrl-row .cr-label,.opt-row .cr-label{font-size:13px;}.field-label{font-size:13px;}.field-input{font-size:15px;padding:10px 12px;}.side-panel button{font-size:13px;padding:10px;}.section-title{font-size:12px;}.toggle-btn{font-size:11px;padding:6px 13px;}.opt-row select{font-size:13px;padding:8px 10px;}.ctrl-row .cr-val{font-size:13px;}}
  @media(max-width:750px){
    #panelToggle{display:block;}
    .side-panel{position:fixed;top:0;bottom:0;width:100%;border:none;border-radius:0;transition:transform 0.3s ease;z-index:1100;}
    .side-panel.left{left:0;transform:translateX(-100%);}
    .side-panel.right{right:0;transform:translateX(100%);}
    .side-panel.mobile-open{transform:translateX(0);}
    .panel-title{font-size:16px;padding-top:50px;}
    .field-label{font-size:14px;}
    .field-input{font-size:18px;padding:14px 16px;}
    .side-panel button{font-size:16px;padding:15px;}
    .section-title{font-size:14px;}
    .ctrl-row .cr-label,.opt-row .cr-label{font-size:15px;}
    .ctrl-row .cr-val{font-size:15px;}
    .toggle-btn{font-size:13px;padding:7px 16px;}
    .opt-row select{font-size:15px;padding:10px 12px;}
    #serialStatus{font-size:12px;bottom:8px;}
  }
</style>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  function flash(id){var b=document.getElementById(id);if(!b)return;b.classList.add('flashPurple');setTimeout(function(){b.classList.remove('flashPurple');},300);}
  var mobilePanel=null;
  function togglePanel(){
    var lp=document.getElementById('leftPanel'),rp=document.getElementById('rightPanel'),btn=document.getElementById('panelToggle');
    if(mobilePanel==='left'){lp.classList.remove('mobile-open');mobilePanel='right';rp.classList.add('mobile-open');btn.textContent='[x] Close';}
    else if(mobilePanel==='right'){rp.classList.remove('mobile-open');mobilePanel=null;btn.textContent='[=] Panels';}
    else{mobilePanel='left';lp.classList.add('mobile-open');btn.textContent='SWARM >';}
  }
</script>
</head>
<body>
<div id="map"></div>
<div id="statusTicker"><span class="ticker-dot"></span>SPOOFING ACTIVE</div>
<button id="panelToggle" onclick="togglePanel()">[=] Panels</button>

<!-- LEFT PANEL -->
<div id="leftPanel" class="side-panel left">
  <div class="panel-title">Mission Control</div>
  <div class="panel-body">

    <div class="section-title" style="margin-top:0;">Connected Boards</div>
    <div id="boardRoster" style="margin-bottom:6px;"></div>
    <div id="addBoardRow" style="display:none;margin-bottom:6px;">
      <div style="display:flex;gap:4px;align-items:center;">
        <select id="addBoardPort" style="flex:1;padding:6px 8px;font-size:11px;background:rgba(0,0,0,0.4);color:#c0ffc0;border:1px solid rgba(125,249,255,0.15);font-family:inherit;"></select>
        <select id="addBoardLabel" style="width:68px;padding:6px 4px;font-size:11px;background:rgba(0,0,0,0.4);color:#7DF9FF;border:1px solid rgba(125,249,255,0.15);font-family:inherit;">
          <option value="S3">S3</option><option value="C5">C5</option>
        </select>
        <button onclick="doAddBoard()" style="padding:6px 10px;font-size:10px;background:transparent;color:lime;border:1px solid rgba(0,255,0,0.3);cursor:pointer;font-family:inherit;">ADD</button>
      </div>
    </div>
    <button id="addBoardBtn" onclick="showAddBoard()" style="width:100%;padding:6px 10px;font-size:11px;letter-spacing:2px;background:transparent;color:rgba(125,249,255,0.4);border:1px solid rgba(125,249,255,0.15);cursor:pointer;font-family:inherit;text-transform:uppercase;">+ Add Board</button>

    <span class="field-label">Remote ID</span>
    <input class="field-input" id="basicId" placeholder="Drone identifier"/>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px;">
      <div><span class="field-label">Altitude (m)</span><input class="field-input" id="alt" type="number" value="100"/></div>
      <div><span class="field-label">Speed (mph)</span><input class="field-input" id="speed" type="number" value="25"/></div>
    </div>

    <button id="setPilot" class="btn-pilot" style="margin-top:6px;">Set Pilot Location</button>
    <div style="display:flex;gap:4px;margin-top:3px;">
      <button id="play" class="btn-play" style="flex:1;margin:0;">Play</button>
      <button id="pause" class="btn-pause" style="flex:1;margin:0;">Pause</button>
      <button id="stop" class="btn-stop" style="flex:1;margin:0;">Stop</button>
    </div>
    <button id="clearPaths" class="btn-clear" style="margin-top:3px;">Clear Paths</button>

    <div class="section-title">Hardware</div>
    <div class="ctrl-row"><span class="cr-label">Buzzer</span><span class="toggle-btn on" id="buzzerToggle" onclick="flipToggle(this);toggleHw('buzzer',!this.classList.contains('on'))">ON</span><span style="width:8px"></span><span class="cr-label">LED</span><span class="toggle-btn on" id="ledToggle" onclick="flipToggle(this);toggleHw('led',!this.classList.contains('on'))">ON</span></div>

    <div class="section-title">Band Configuration</div>
    <div class="opt-row"><span class="cr-label">TX Band</span><select id="bandMode" onchange="sendBandConfig()"><option value="2">Dual Band</option><option value="0">2.4 GHz Only</option><option value="1">5 GHz Only</option></select></div>
    <div id="fiveGhzChannels" style="margin:6px 0;">
      <div style="font-size:11px;color:rgba(125,249,255,0.35);letter-spacing:1px;margin-bottom:6px;">5GHZ CHANNELS</div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;">
        <span class="toggle-btn on ch-toggle" id="ch149" onclick="flipToggle(this);sendBandConfig()">149</span>
        <span class="toggle-btn on ch-toggle" id="ch153" onclick="flipToggle(this);sendBandConfig()">153</span>
        <span class="toggle-btn on ch-toggle" id="ch157" onclick="flipToggle(this);sendBandConfig()">157</span>
        <span class="toggle-btn on ch-toggle" id="ch161" onclick="flipToggle(this);sendBandConfig()">161</span>
        <span class="toggle-btn on ch-toggle" id="ch165" onclick="flipToggle(this);sendBandConfig()">165</span>
      </div>
    </div>

    <div class="section-title">Realistic Variations</div>
    <div class="ctrl-row"><span class="cr-label" style="flex:1;color:rgba(125,249,255,0.6);">Master</span><span class="toggle-btn on" id="masterVariation" onclick="flipToggle(this);toggleMaster(this.classList.contains('on'))">ON</span></div>
    <div class="divider"></div>

    <div class="ctrl-row"><span class="cr-label">Alt Drift</span><span class="toggle-btn on" id="altVar" onclick="flipToggle(this)">ON</span><input type="range" id="altVarRange" min="1" max="30" value="5" oninput="document.getElementById('altVarVal').textContent=this.value+'m'"><span class="cr-val" id="altVarVal">5m</span></div>
    <div class="ctrl-row"><span class="cr-label">Speed</span><span class="toggle-btn on" id="speedVar" onclick="flipToggle(this)">ON</span><input type="range" id="speedVarRange" min="1" max="40" value="15" oninput="document.getElementById('speedVarVal').textContent=this.value+'%'"><span class="cr-val" id="speedVarVal">15%</span></div>
    <div class="ctrl-row"><span class="cr-label">GPS</span><span class="toggle-btn on" id="gpsVar" onclick="flipToggle(this)">ON</span><input type="range" id="gpsVarRange" min="1" max="20" value="3" oninput="document.getElementById('gpsVarVal').textContent=this.value+'m'"><span class="cr-val" id="gpsVarVal">3m</span></div>
    <div class="ctrl-row"><span class="cr-label">Heading</span><span class="toggle-btn on" id="headVar" onclick="flipToggle(this)">ON</span><input type="range" id="headVarRange" min="1" max="15" value="3" oninput="document.getElementById('headVarVal').textContent=this.value+'&deg;'"><span class="cr-val" id="headVarVal">3&deg;</span></div>
    <div class="ctrl-row"><span class="cr-label">TX Jitter</span><span class="toggle-btn on" id="txJitter" onclick="flipToggle(this)">ON</span><input type="range" id="txJitterRange" min="10" max="200" value="50" oninput="document.getElementById('txJitterVal').textContent=this.value+'ms'"><span class="cr-val" id="txJitterVal">50ms</span></div>

    <div class="opt-row"><span class="cr-label">Alt Pattern</span><select id="altPattern"><option value="perlin">Perlin</option><option value="sine">Sine</option><option value="random">Random Walk</option></select></div>

    <div class="telem-box idle" id="telemBox">
      <div class="telem-title">Live Broadcast</div>
      <div class="telem-grid">
        <div class="telem-item"><span class="tl">RID</span><span class="tv" id="tRid">--</span></div>
        <div class="telem-item"><span class="tl">Alt</span><span class="tv" id="tAlt">--</span></div>
        <div class="telem-item"><span class="tl">Lat</span><span class="tv" id="tLat">--</span></div>
        <div class="telem-item"><span class="tl">Lng</span><span class="tv" id="tLng">--</span></div>
        <div class="telem-item"><span class="tl">Pilot Lat</span><span class="tv" id="tPLat">--</span></div>
        <div class="telem-item"><span class="tl">Pilot Lng</span><span class="tv" id="tPLng">--</span></div>
        <div class="telem-item"><span class="tl">TX #</span><span class="tv" id="tTxCount">0</span></div>
        <div class="telem-item"><span class="tl">Band</span><span class="tv" id="tBand">--</span></div>
        <div class="telem-item"><span class="tl">State</span><span class="tv" id="tState">IDLE</span></div>
      </div>
    </div>
  </div>
</div>

<!-- RIGHT PANEL -->
<div id="rightPanel" class="side-panel right">
  <div class="panel-title">Swarm Mode</div>
  <div class="panel-body">

    <div class="ctrl-row"><span class="cr-label" style="flex:1;color:rgba(255,0,255,0.6);font-weight:500;">Enable Swarm</span><span class="toggle-btn" id="swarmEnabled" onclick="flipToggle(this);onSwarmToggle()">OFF</span></div>

    <div class="ctrl-row" style="margin-top:4px;">
      <span class="cr-label">Count</span>
      <input class="field-input" type="number" id="swarmCount" min="2" max="20" value="5" oninput="rebuildSwarmList()" style="width:60px;padding:6px 8px;text-align:center;font-size:13px;">
      <button onclick="rebuildSwarmList()" style="width:auto!important;padding:5px 12px!important;font-size:9px;border:1px solid rgba(125,249,255,0.2)!important;color:rgba(125,249,255,0.5)!important;margin:0;">APPLY</button>
    </div>

    <div class="opt-row"><span class="cr-label">ID Mode</span><select id="swarmIdMode" onchange="rebuildSwarmList()"><option value="random">Random</option><option value="prefix">Prefix</option><option value="manual">Manual</option></select></div>
    <div id="swarmPrefixRow" class="ctrl-row" style="display:none;"><span class="cr-label">Prefix</span><input class="field-input" id="swarmPrefix" value="DRONE-" style="flex:1;padding:6px 8px;font-size:12px;" onchange="rebuildSwarmList()"></div>

    <div class="section-title">Spread</div>
    <div class="ctrl-row"><span class="cr-label">Lateral</span><input type="range" id="swarmSpread" min="10" max="500" value="100" oninput="document.getElementById('swarmSpreadVal').textContent=this.value+'m'"><span class="cr-val" id="swarmSpreadVal">100m</span></div>
    <div class="ctrl-row"><span class="cr-label">Alt</span><input type="range" id="swarmAltSpread" min="0" max="100" value="20" oninput="document.getElementById('swarmAltSpreadVal').textContent=this.value+'m'"><span class="cr-val" id="swarmAltSpreadVal">20m</span></div>
    <div class="ctrl-row"><span class="cr-label">Speed</span><input type="range" id="swarmSpeedSpread" min="0" max="50" value="20" oninput="document.getElementById('swarmSpeedSpreadVal').textContent=this.value+'%'"><span class="cr-val" id="swarmSpeedSpreadVal">20%</span></div>

    <div class="opt-row"><span class="cr-label">Formation</span><select id="swarmFormation"><option value="scatter">Scatter</option><option value="line">Line</option><option value="circle">Circle</option><option value="vee">V-Formation</option></select></div>

    <div class="section-title">Flight Paths</div>
    <div class="opt-row"><span class="cr-label" style="color:rgba(255,0,255,0.55);">Mode</span><select id="swarmPathMode" style="color:#FF00FF;border-color:rgba(255,0,255,0.2);"><option value="formation">Formation Lock</option><option value="offset">Offset Paths</option><option value="random">Random Routes</option></select></div>
    <div style="font-size:9px;color:rgba(125,249,255,0.2);margin:0 0 2px;height:12px;"><span id="pathModeDesc">Drones hold formation offset from lead.</span></div>
    <div id="randomPathSettings" style="display:none;">
      <div class="ctrl-row"><span class="cr-label">Radius</span><input type="range" id="randomRouteRadius" min="50" max="2000" value="500" oninput="document.getElementById('randomRouteRadiusVal').textContent=this.value+'m'"><span class="cr-val" id="randomRouteRadiusVal">500m</span></div>
      <div class="ctrl-row"><span class="cr-label">Waypoints</span><input type="range" id="randomWaypointCount" min="3" max="15" value="6" oninput="document.getElementById('randomWaypointCountVal').textContent=this.value"><span class="cr-val" id="randomWaypointCountVal">6</span></div>
      <div class="ctrl-row"><span class="cr-label">Loop</span><span class="toggle-btn on" id="randomLoop" onclick="flipToggle(this)">ON</span></div>
    </div>
    <div class="ctrl-row"><span class="cr-label">Stagger Start</span><span class="toggle-btn on" id="swarmStagger" onclick="flipToggle(this)">ON</span></div>

    <div id="swarmDroneList"></div>

    <div class="telem-box idle" id="swarmTelemBox">
      <div class="telem-title">Swarm Feed</div>
      <div id="swarmTelemFeed" class="swarm-telem"><div style="font-size:11px;color:rgba(255,255,255,0.15);">No active drones</div></div>
    </div>
  </div>
</div>

<div id="serialStatus"></div>
<script>
var map=L.map('map',{attributionControl:false}).setView([39.8,-98.6],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(map);

var waypointMarkers=[],path=[],poly=L.polyline(path,{color:'lime'}).addTo(map);
var loopLine=null,pilotSetMode=false,pilotMarker,droneMarker,simIndex=null;
var statusCircle=null,playing=false,firstHighlight=null,lastHighlight=null,segmentOffset=0;

// ── toggle helpers ──

function flipToggle(el){
  var on=el.classList.toggle('on');
  el.textContent=on?'ON':'OFF';
}
function isOn(id){return document.getElementById(id).classList.contains('on');}

// ── status ticker ──
var tickerEl=null,tickerCount=0,tickerInterval=null;
function updateTicker(state){
  if(!tickerEl)tickerEl=document.getElementById('statusTicker');
  if(state==='playing'){
    tickerCount=0;
    tickerEl.className='';tickerEl.style.display='block';
    var bm=parseInt(document.getElementById('bandMode').value);
    var bstr=bm===0?'2.4G':bm===1?'5G':'DUAL';
    tickerEl.innerHTML='<span class="ticker-dot"></span>SPOOFING ACTIVE ['+bstr+'] -- TX 0';
    if(tickerInterval)clearInterval(tickerInterval);
    tickerInterval=setInterval(function(){var bm2=parseInt(document.getElementById('bandMode').value);var bs=bm2===0?'2.4G':bm2===1?'5G':'DUAL';tickerEl.innerHTML='<span class="ticker-dot"></span>SPOOFING ACTIVE ['+bs+'] -- TX '+tickerCount;},500);
  }else if(state==='paused'){
    if(tickerInterval){clearInterval(tickerInterval);tickerInterval=null;}
    tickerEl.className='paused';tickerEl.style.display='block';
    tickerEl.innerHTML='<span class="ticker-dot"></span>PAUSED -- TX '+tickerCount;
  }else{
    if(tickerInterval){clearInterval(tickerInterval);tickerInterval=null;}
    tickerEl.style.display='none';tickerCount=0;
  }
}
function tickerIncrement(){tickerCount++;}

// ── variation engine ──

var _noiseState={},_rwState={},_sineT=0;

function toggleMaster(on){['altVar','speedVar','gpsVar','headVar','txJitter'].forEach(function(id){var el=document.getElementById(id);if(on){el.classList.add('on');el.textContent='ON';}else{el.classList.remove('on');el.textContent='OFF';}});}

function smoothNoise(key,speed){
  if(!_noiseState[key])_noiseState[key]={v:0,target:(Math.random()-0.5)*2,t:0};
  var s=_noiseState[key];
  s.t+=speed||0.02;
  if(s.t>=1){s.v=s.target;s.target=(Math.random()-0.5)*2;s.t=0;}
  var f=(1-Math.cos(s.t*Math.PI))/2;
  return s.v*(1-f)+s.target*f;
}

function randomWalk(key,stepSize){
  if(_rwState[key]===undefined)_rwState[key]=0;
  _rwState[key]+=(Math.random()-0.5)*stepSize*2;
  _rwState[key]=Math.max(-1,Math.min(1,_rwState[key]));
  return _rwState[key];
}

function getAltVariation(){
  if(!isOn('altVar'))return 0;
  var r=parseFloat(document.getElementById('altVarRange').value);
  var p=document.getElementById('altPattern').value;
  if(p==='perlin')return smoothNoise('alt',0.03)*r;
  if(p==='sine'){_sineT+=0.05;return Math.sin(_sineT)*r;}
  if(p==='random')return randomWalk('alt',0.15)*r;
  return 0;
}

function getSpeedMultiplier(){
  if(!isOn('speedVar'))return 1.0;
  return 1.0+smoothNoise('speed',0.02)*(parseFloat(document.getElementById('speedVarRange').value)/100);
}

function getGpsJitter(){
  if(!isOn('gpsVar'))return{lat:0,lng:0};
  var m=parseFloat(document.getElementById('gpsVarRange').value);
  return{lat:smoothNoise('gpsLat',0.04)*m/111111,lng:smoothNoise('gpsLng',0.04)*m/111111};
}

function getHeadingDrift(){
  if(!isOn('headVar'))return 0;
  return smoothNoise('head',0.03)*parseFloat(document.getElementById('headVarRange').value);
}

function applyVariations(lat,lng,alt){
  var gps=getGpsJitter();
  return{lat:lat+gps.lat,lng:lng+gps.lng,alt:alt+getAltVariation()};
}

function getTxInterval(){
  var base=500;
  if(!isOn('txJitter'))return base;
  var j=parseFloat(document.getElementById('txJitterRange').value);
  return base+(Math.random()-0.5)*2*j;
}

// ── swarm engine ──

var swarmDrones=[],swarmTxIndex=0,swarmMarkers=[],swarmPolylines=[],swarmAnimFrame=null,swarmInitialized=false;
var SWARM_COLORS=['#FF00FF','#00FFFF','#FFFF00','#FF6600','#66FF00','#FF0066','#6600FF','#00FF66','#FF3399','#33FFCC','#CC33FF','#FFCC33','#3399FF','#FF9933','#33FF99','#9933FF','#FF3333','#33FF33','#3333FF','#FF33FF'];

function onSwarmToggle(){
  if(isOn('swarmEnabled')&&!swarmInitialized){rebuildSwarmList();swarmInitialized=true;}
  if(isOn('swarmEnabled')&&missionState==='playing'&&path.length>=2){
    buildSwarmPaths();stopSwarmAnimation();animateSwarmDrones();
  }
  if(!isOn('swarmEnabled')){stopSwarmAnimation();clearSwarmMarkers();clearSwarmPolylines();}
}
function getLiveSpeed(){return(parseFloat(document.getElementById('speed').value)||25)*0.44704;}

document.getElementById('swarmPathMode').addEventListener('change',function(){
  var m=this.value,d=document.getElementById('pathModeDesc'),r=document.getElementById('randomPathSettings');
  d.textContent=m==='formation'?'Drones hold formation offset from lead drone.':m==='offset'?'Each drone flies a parallel copy of the main path, offset by formation.':'Each drone gets its own random route. Looks like independent aircraft.';
  r.style.display=m==='random'?'block':'none';
});

function generateRandomDroneId(){
  var fns=[
    function(){var l='ABCDEFGHJKLMNPQRSTUVWXYZ',s='';for(var i=0;i<3;i++)s+=l[Math.floor(Math.random()*l.length)];return s+Math.floor(10000+Math.random()*90000);},
    function(){var p=['1SS','2BK','3QW','4NE','1WD','3RM','4SS','2NF'];return p[Math.floor(Math.random()*p.length)]+'D'+Math.floor(100000+Math.random()*900000);},
    function(){var h='';for(var i=0;i<12;i++)h+='0123456789ABCDEF'[Math.floor(Math.random()*16)];return h;},
    function(){return'RID-'+Math.floor(100000+Math.random()*900000)+'-'+String.fromCharCode(65+Math.floor(Math.random()*26))+String.fromCharCode(65+Math.floor(Math.random()*26));}
  ];
  return fns[Math.floor(Math.random()*fns.length)]();
}

function rebuildSwarmList(){
  var count=Math.max(2,Math.min(20,parseInt(document.getElementById('swarmCount').value)||5));
  var idMode=document.getElementById('swarmIdMode').value;
  var prefix=document.getElementById('swarmPrefix').value||'DRONE-';
  document.getElementById('swarmPrefixRow').style.display=idMode==='prefix'?'flex':'none';
  var spreadM=parseFloat(document.getElementById('swarmSpread').value)||100;
  var altSpreadM=parseFloat(document.getElementById('swarmAltSpread').value)||20;
  var speedPct=(parseFloat(document.getElementById('swarmSpeedSpread').value)||20)/100;
  var formation=document.getElementById('swarmFormation').value;
  var oldDrones={};
  swarmDrones.forEach(function(d){oldDrones[d.idx]=d;});
  var newDrones=[];
  for(var i=0;i<count;i++){
    var old=oldDrones[i];
    var id;
    if(idMode==='random')id=old?old.id:generateRandomDroneId();
    else if(idMode==='prefix')id=prefix+String(i+1).padStart(2,'0');
    else id=old?old.id:('DRONE-'+String(i+1).padStart(2,'0'));
    var off=getFormationOffset(i,count,spreadM,formation);
    newDrones.push({idx:i,id:id,offsetLat:off.lat,offsetLng:off.lng,
      altOffset:old?old.altOffset:(Math.random()-0.5)*2*altSpreadM,
      speedMult:old?old.speedMult:1.0+(Math.random()-0.5)*2*speedPct,
      noiseSeed:old?old.noiseSeed:Math.random()*10000,
      active:old?old.active:false,
      flightPath:old?old.flightPath:null,
      simIndex:old?old.simIndex:0,
      segmentOffset:old?old.segmentOffset:0,
      currentLat:old?old.currentLat:0,
      currentLng:old?old.currentLng:0});
  }
  swarmDrones=newDrones;
  renderSwarmList();
  if(missionState==='playing'&&isOn('swarmEnabled')&&swarmDrones.length>0){
    buildSwarmPaths();stopSwarmAnimation();animateSwarmDrones();
  }
}

function getFormationOffset(idx,total,spreadM,formation){
  var m=1.0/111111;
  if(formation==='scatter'){var a=Math.random()*Math.PI*2,r=Math.sqrt(Math.random())*spreadM;return{lat:Math.cos(a)*r*m,lng:Math.sin(a)*r*m};}
  if(formation==='line'){var p=(idx/Math.max(total-1,1)-0.5)*spreadM*2;return{lat:p*m,lng:0};}
  if(formation==='circle'){var a2=(idx/total)*Math.PI*2;return{lat:Math.cos(a2)*spreadM*m,lng:Math.sin(a2)*spreadM*m};}
  if(formation==='vee'){
    if(idx===0)return{lat:0,lng:0};
    var side=(idx%2===0)?1:-1,rank=Math.ceil(idx/2),sp=spreadM/Math.max(Math.ceil(total/2),1);
    return{lat:-rank*sp*m,lng:side*rank*sp*0.7*m};
  }
  return{lat:0,lng:0};
}

function generateOffsetPath(i){var d=swarmDrones[i];return path.map(function(wp){return[wp[0]+d.offsetLat,wp[1]+d.offsetLng];});}

function generateRandomPath(){
  var radiusM=parseFloat(document.getElementById('randomRouteRadius').value)||500;
  var wpCount=parseInt(document.getElementById('randomWaypointCount').value)||6;
  var m=1.0/111111,cLat=0,cLng=0;
  path.forEach(function(wp){cLat+=wp[0];cLng+=wp[1];});
  cLat/=path.length;cLng/=path.length;
  var route=[];
  for(var i=0;i<wpCount;i++){var a=Math.random()*Math.PI*2,r=Math.sqrt(Math.random())*radiusM;route.push([cLat+Math.cos(a)*r*m,cLng+Math.sin(a)*r*m]);}
  var ordered=[route[0]],remaining=route.slice(1);
  while(remaining.length>0){
    var last=ordered[ordered.length-1],bestIdx=0,bestDist=Infinity;
    remaining.forEach(function(wp,ri){var dx=wp[0]-last[0],dy=wp[1]-last[1],d=dx*dx+dy*dy;if(d<bestDist){bestDist=d;bestIdx=ri;}});
    ordered.push(remaining[bestIdx]);remaining.splice(bestIdx,1);
  }
  return ordered;
}

function buildSwarmPaths(){
  var mode=document.getElementById('swarmPathMode').value;
  clearSwarmPolylines();
  swarmDrones.forEach(function(d,i){
    if(mode==='formation'){d.flightPath=null;d.currentLat=path[0][0]+d.offsetLat;d.currentLng=path[0][1]+d.offsetLng;}
    else if(mode==='offset'){d.flightPath=generateOffsetPath(i);d.currentLat=d.flightPath[0][0];d.currentLng=d.flightPath[0][1];}
    else if(mode==='random'){d.flightPath=generateRandomPath();d.currentLat=d.flightPath[0][0];d.currentLng=d.flightPath[0][1];}
    d.simIndex=0;d.segmentOffset=0;
  });
  swarmDrones.forEach(function(d,i){
    if(d.flightPath&&d.flightPath.length>1){
      var pl=L.polyline(d.flightPath.concat([d.flightPath[0]]),{color:SWARM_COLORS[i%SWARM_COLORS.length],weight:1.5,opacity:0.4,dashArray:'4,6'}).addTo(map);
      swarmPolylines.push(pl);
    }
  });
}

function getLiveFormationOffset(idx){
  var count=swarmDrones.length;
  var spreadM=parseFloat(document.getElementById('swarmSpread').value)||100;
  var formation=document.getElementById('swarmFormation').value;
  return getFormationOffset(idx,count,spreadM,formation);
}

function animateSwarmDrones(){
  if(missionState!=='playing')return;
  var liveSpeed=getLiveSpeed();
  var mode=document.getElementById('swarmPathMode').value;
  swarmDrones.forEach(function(d){
    if(mode==='formation'){
      if(droneMarker){
        var dl=droneMarker.getLatLng();
        var off=getLiveFormationOffset(d.idx);
        d.offsetLat=off.lat;d.offsetLng=off.lng;
        d.currentLat=dl.lat+off.lat;d.currentLng=dl.lng+off.lng;
      }
    }else if(d.flightPath&&d.flightPath.length>1){
      var fp=d.flightPath,from=fp[d.simIndex],to=fp[(d.simIndex+1)%fp.length];
      var dx=to[0]-from[0],dy=to[1]-from[1],distM=Math.sqrt(dx*dx+dy*dy)*111111;
      var advance=(liveSpeed*d.speedMult*0.016)/Math.max(distM,0.1);
      d.segmentOffset+=advance;
      if(d.segmentOffset>=1){d.segmentOffset=0;d.simIndex=(d.simIndex+1)%fp.length;from=fp[d.simIndex];to=fp[(d.simIndex+1)%fp.length];}
      var t=d.segmentOffset;
      d.currentLat=from[0]+(to[0]-from[0])*t;
      d.currentLng=from[1]+(to[1]-from[1])*t;
    }
  });
  updateSwarmMarkers();
  swarmAnimFrame=requestAnimationFrame(animateSwarmDrones);
}

function stopSwarmAnimation(){if(swarmAnimFrame){cancelAnimationFrame(swarmAnimFrame);swarmAnimFrame=null;}}

function renderSwarmList(){
  var container=document.getElementById('swarmDroneList');
  var idMode=document.getElementById('swarmIdMode').value;
  var html='';
  swarmDrones.forEach(function(d,i){
    var ro=idMode!=='manual'?'readonly':'';
    var sc=d.active?'drone-status active':'drone-status';
    var c=SWARM_COLORS[i%SWARM_COLORS.length];
    html+='<div class="swarm-drone-row"><span class="drone-idx" style="color:'+c+';">#'+(i+1)+'</span><input id="swarmId_'+i+'" value="'+d.id+'" '+ro+' onchange="swarmDrones['+i+'].id=this.value" style="'+(idMode==='manual'?'border-color:#7DF9FF;':'')+'"><span class="'+sc+'" id="swarmStatus_'+i+'"></span></div>';
  });
  container.innerHTML=html;
}

function getSwarmDronePayload(idx,baseLat,baseLng,baseAlt,pLat,pLng){
  var d=swarmDrones[idx];
  if(!d)return null;
  var lat=d.currentLat,lng=d.currentLng,alt=baseAlt+d.altOffset;
  if(isOn('masterVariation')){
    if(isOn('gpsVar')){var gm=parseFloat(document.getElementById('gpsVarRange').value);lat+=smoothNoise('sg_lat_'+idx,0.03+idx*0.002)*gm/111111;lng+=smoothNoise('sg_lng_'+idx,0.03+idx*0.002)*gm/111111;}
    if(isOn('altVar')){var ar=parseFloat(document.getElementById('altVarRange').value);alt+=smoothNoise('sg_alt_'+idx,0.025+idx*0.003)*ar;}
  }
  return{basic_id:d.id,drone_altitude:Math.round(alt),drone_lat:lat,drone_long:lng,pilot_lat:pLat,pilot_long:pLng};
}

function updateSwarmMarkers(){
  if(!isOn('swarmEnabled'))return;
  while(swarmMarkers.length<swarmDrones.length){
    var idx=swarmMarkers.length,c=SWARM_COLORS[idx%SWARM_COLORS.length];
    swarmMarkers.push(L.circleMarker([0,0],{radius:5,color:c,fillColor:c,fillOpacity:0.7,weight:1.5}).addTo(map));
  }
  while(swarmMarkers.length>swarmDrones.length)map.removeLayer(swarmMarkers.pop());
  swarmDrones.forEach(function(d,i){swarmMarkers[i].setLatLng([d.currentLat,d.currentLng]);});
}
function clearSwarmMarkers(){swarmMarkers.forEach(function(m){map.removeLayer(m);});swarmMarkers=[];}
function clearSwarmPolylines(){swarmPolylines.forEach(function(p){map.removeLayer(p);});swarmPolylines=[];}

rebuildSwarmList();

// ── live-update hooks: sliders/toggles instantly affect active flight ──

['swarmSpread','swarmFormation','swarmAltSpread','swarmSpeedSpread'].forEach(function(id){
  document.getElementById(id).addEventListener('input',function(){
    if(missionState!=='idle'&&isOn('swarmEnabled')&&swarmDrones.length>0){
      var spreadM=parseFloat(document.getElementById('swarmSpread').value)||100;
      var formation=document.getElementById('swarmFormation').value;
      swarmDrones.forEach(function(d){
        var off=getFormationOffset(d.idx,swarmDrones.length,spreadM,formation);
        d.offsetLat=off.lat;d.offsetLng=off.lng;
      });
    }
  });
});

document.getElementById('swarmFormation').addEventListener('change',function(){
  if(missionState!=='idle'&&isOn('swarmEnabled')&&swarmDrones.length>0){
    var spreadM=parseFloat(document.getElementById('swarmSpread').value)||100;
    var formation=this.value;
    swarmDrones.forEach(function(d){
      var off=getFormationOffset(d.idx,swarmDrones.length,spreadM,formation);
      d.offsetLat=off.lat;d.offsetLng=off.lng;
    });
    var mode=document.getElementById('swarmPathMode').value;
    if(mode==='offset'){buildSwarmPaths();stopSwarmAnimation();animateSwarmDrones();}
  }
});

document.getElementById('swarmPathMode').addEventListener('change',function(){
  if(missionState==='playing'&&isOn('swarmEnabled')&&swarmDrones.length>0&&path.length>=2){
    buildSwarmPaths();stopSwarmAnimation();animateSwarmDrones();
  }
});

// force immediate telemetry refresh on any variation slider move
['altVarRange','gpsVarRange','speedVarRange','headVarRange','txJitterRange','alt','speed'].forEach(function(id){
  var el=document.getElementById(id);
  if(el)el.addEventListener('input',function(){
    if(missionState!=='idle'&&droneMarker&&pilotMarker){
      var d=droneMarker.getLatLng(),p=pilotMarker.getLatLng();
      var baseAlt=parseInt(document.getElementById('alt').value)||0;
      var v=applyVariations(d.lat,d.lng,baseAlt);
      updateTelemetry({basic_id:document.getElementById('basicId').value,drone_altitude:Math.round(v.alt),drone_lat:v.lat,drone_long:v.lng,pilot_lat:p.lat,pilot_long:p.lng});
    }
  });
});

// ── map interaction ──

document.getElementById('setPilot').onclick=function(){flash('setPilot');pilotSetMode=true;document.getElementById('setPilot').style.backgroundColor='#FF00FF';};

map.on('click',function(e){
  if(pilotSetMode){
    var ll=[e.latlng.lat,e.latlng.lng];
    if(pilotMarker)pilotMarker.setLatLng(ll);
    else pilotMarker=L.marker(ll,{icon:createIcon('PILOT')}).addTo(map);
    pilotSetMode=false;document.getElementById('setPilot').style.backgroundColor='';
  }else{
    path.push([e.latlng.lat,e.latlng.lng]);
    poly.setLatLngs(path);
    waypointMarkers.push(L.circleMarker([e.latlng.lat,e.latlng.lng],{radius:6,color:'#FF00FF',fillColor:'#FF00FF',fillOpacity:1}).addTo(map));
    if(firstHighlight)map.removeLayer(firstHighlight);
    firstHighlight=L.circle(path[0],{radius:12,color:'lime',fill:false,weight:3}).addTo(map);
  }
});

function createIcon(label){
  var c=label==='PILOT'?'#FF00FF':'lime';
  return L.divIcon({html:'<div style="width:24px;height:24px;border:2px solid '+c+';border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:bold;color:'+c+';background:rgba(0,0,0,0.7);font-family:monospace;">'+label+'</div>',className:'',iconSize:[24,24],iconAnchor:[12,12]});
}

// ── state machine: idle | playing | paused ──

var missionState='idle',txTimerId=null,txRunning=false;

function killTxLoop(){txRunning=false;if(txTimerId){clearTimeout(txTimerId);txTimerId=null;}}

function txSend(){
  if(!txRunning)return;
  if(!droneMarker||!pilotMarker)return;
  var d=droneMarker.getLatLng(),p=pilotMarker.getLatLng();
  var baseAlt=parseInt(document.getElementById('alt').value)||0;
  var swarmOn=isOn('swarmEnabled')&&swarmDrones.length>0;
  if(swarmOn){
    var payload=getSwarmDronePayload(swarmTxIndex,d.lat,d.lng,baseAlt,p.lat,p.lng);
    if(payload){
      sendUpdate(payload);
      swarmDrones.forEach(function(sd,si){sd.active=(si===swarmTxIndex);var el=document.getElementById('swarmStatus_'+si);if(el)el.className=sd.active?'drone-status active':'drone-status';});
    }
    swarmTxIndex=(swarmTxIndex+1)%swarmDrones.length;
    if(missionState==='playing')updateSwarmMarkers();
  }else{
    var v=applyVariations(d.lat,d.lng,baseAlt);
    sendUpdate({basic_id:document.getElementById('basicId').value,drone_altitude:Math.round(v.alt),drone_lat:v.lat,drone_long:v.lng,pilot_lat:p.lat,pilot_long:p.lng});
  }
  tickerIncrement();
}

function startTxLoop(){
  killTxLoop();
  txRunning=true;
  swarmTxIndex=0;
  txSend();
  (function tick(){
    if(!txRunning)return;
    var swarmOn=isOn('swarmEnabled')&&swarmDrones.length>0;
    var interval=getTxInterval();
    if(swarmOn)interval=Math.max(80,interval/swarmDrones.length);
    txTimerId=setTimeout(function(){
      if(!txRunning)return;
      txSend();
      tick();
    },interval);
  })();
}

// ── API calls with retry ──

function sendUpdate(payload){
  fetch('/api/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).catch(function(err){console.error('TX fail:',err);});
  updateTelemetry(payload);
}

function updateTelemetry(p){
  var box=document.getElementById('telemBox');
  if(box)box.className='telem-box';
  var rid=document.getElementById('tRid'),alt=document.getElementById('tAlt');
  var lat=document.getElementById('tLat'),lng=document.getElementById('tLng');
  var plat=document.getElementById('tPLat'),plng=document.getElementById('tPLng');
  var txc=document.getElementById('tTxCount'),st=document.getElementById('tState');
  if(rid)rid.textContent=p.basic_id||'--';
  if(alt)alt.textContent=(p.drone_altitude||0)+'m';
  if(lat)lat.textContent=p.drone_lat?p.drone_lat.toFixed(6):'--';
  if(lng)lng.textContent=p.drone_long?p.drone_long.toFixed(6):'--';
  if(plat)plat.textContent=p.pilot_lat?p.pilot_lat.toFixed(6):'--';
  if(plng)plng.textContent=p.pilot_long?p.pilot_long.toFixed(6):'--';
  if(txc)txc.textContent=tickerCount;
  var bandEl=document.getElementById('tBand');
  if(bandEl){var bm=parseInt(document.getElementById('bandMode').value);bandEl.textContent=bm===0?'2.4G':bm===1?'5G':'DUAL';bandEl.style.color=bm===2?'#7DF9FF':bm===1?'#FF00FF':'#00ff88';}
  if(st){var s=missionState==='playing'?'TRANSMITTING':missionState==='paused'?'PAUSED':'IDLE';st.textContent=s;if(s==='TRANSMITTING')st.style.color='#00ff88';else if(s==='PAUSED')st.style.color='#ffa500';else st.style.color='rgba(255,255,255,0.15)';}
  updateSwarmTelemetry(p);
}

function updateSwarmTelemetry(lastPayload){
  var box=document.getElementById('swarmTelemBox');
  var feed=document.getElementById('swarmTelemFeed');
  if(!feed)return;
  if(!isOn('swarmEnabled')||swarmDrones.length===0){
    if(box)box.className='telem-box idle';
    feed.innerHTML='<div style="font-size:11px;color:rgba(255,255,255,0.15);">No active drones</div>';
    return;
  }
  if(box)box.className='telem-box';
  var html='';
  swarmDrones.forEach(function(d,i){
    var ac=d.active?'active':'';
    var alt=Math.round((parseInt(document.getElementById('alt').value)||0)+d.altOffset);
    var lat=d.currentLat?d.currentLat.toFixed(5):'--';
    var lng=d.currentLng?d.currentLng.toFixed(5):'--';
    html+='<div class="swarm-telem-row '+ac+'"><span class="st-id">'+d.id.substring(0,10)+'</span><span class="st-val">'+lat+' '+lng+' '+alt+'m</span></div>';
  });
  feed.innerHTML=html;
}

function clearTelemetry(){
  var box=document.getElementById('telemBox');if(box)box.className='telem-box idle';
  ['tRid','tAlt','tLat','tLng','tPLat','tPLng','tBand'].forEach(function(id){var e=document.getElementById(id);if(e)e.textContent='--';});
  var txc=document.getElementById('tTxCount');if(txc)txc.textContent='0';
  var st=document.getElementById('tState');if(st)st.textContent='IDLE';
  var sbox=document.getElementById('swarmTelemBox');if(sbox)sbox.className='telem-box idle';
  var sf=document.getElementById('swarmTelemFeed');if(sf)sf.innerHTML='<div style="font-size:11px;color:rgba(255,255,255,0.15);">No active drones</div>';
}

function sendCommand(endpoint,cb){
  fetch(endpoint,{method:'POST'}).then(function(r){return r.json();}).then(function(d){if(cb)cb(null,d);}).catch(function(err){console.error('CMD fail:',err);if(cb)cb(err);});
}

function toggleHw(type,muted){
  fetch('/api/'+type,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({muted:muted})}).catch(console.error);
}

function sendBandConfig(){
  var mode=parseInt(document.getElementById('bandMode').value);
  var chIds=['ch149','ch153','ch157','ch161','ch165'];
  var channels=chIds.map(function(id){return document.getElementById(id).classList.contains('on');});
  var show5=mode===1||mode===2;
  document.getElementById('fiveGhzChannels').style.display=show5?'block':'none';
  fetch('/api/band',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({band_mode:mode,channels_5g:channels})}).catch(console.error);
}

// ── movement animation ──

function moveSegment(idx,offset){
  if(missionState!=='playing')return;
  simIndex=idx;
  var from=path[idx],to=path[(idx+1)%path.length];
  var dist=map.distance(L.latLng(from),L.latLng(to));
  if(dist<0.01){segmentOffset=0;moveSegment((idx+1)%path.length,0);return;}
  var startTime=performance.now();
  (function step(){
    if(missionState!=='playing')return;
    var liveSpeed=getLiveSpeed()*getSpeedMultiplier();
    var duration=(dist/liveSpeed)*1000;
    var t=offset+(performance.now()-startTime)/duration;
    if(t>=1){segmentOffset=0;moveSegment((idx+1)%path.length,0);}
    else{
      var lat=from[0]+(to[0]-from[0])*t,lng=from[1]+(to[1]-from[1])*t;
      var hd=getHeadingDrift();
      if(hd!==0){
        var dl=to[0]-from[0],dn=to[1]-from[1],sl=Math.sqrt(dl*dl+dn*dn);
        if(sl>0){lat+=(-dn/sl)*hd*0.00001;lng+=(dl/sl)*hd*0.00001;}
      }
      droneMarker.setLatLng([lat,lng]);
      if(statusCircle)statusCircle.setLatLng([lat,lng]);
      segmentOffset=t;
      requestAnimationFrame(step);
    }
  })();
}

function setStatusCircle(color){
  if(statusCircle)map.removeLayer(statusCircle);
  if(droneMarker)statusCircle=L.circleMarker(droneMarker.getLatLng(),{radius:16,color:color,fill:false,weight:3}).addTo(map);
}

// ── PLAY ──

document.getElementById('play').onclick=function(){
  flash('play');
  if(missionState==='paused'){
    missionState='playing';playing=true;
    setStatusCircle('#00cc00');
    updateTicker('playing');
    moveSegment(simIndex,segmentOffset);
    if(isOn('swarmEnabled')&&swarmDrones.length>0){stopSwarmAnimation();animateSwarmDrones();}
    return;
  }
  if(!pilotMarker)return alert('Set pilot location first.');
  if(path.length<2)return alert('Set at least 2 waypoints.');
  if(!isOn('swarmEnabled')&&!document.getElementById('basicId').value.trim())return alert('Remote ID is required. Enter a drone identifier before starting.');
  missionState='playing';playing=true;
  var missionData={basic_id:document.getElementById('basicId').value,drone_altitude:parseInt(document.getElementById('alt').value)||0,path:path};
  fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(missionData)}).catch(console.error);
  var swarmOn=isOn('swarmEnabled')&&swarmDrones.length>0;
  if(swarmOn)buildSwarmPaths();
  var startPos=path[0],p=pilotMarker.getLatLng(),initAlt=parseInt(document.getElementById('alt').value)||0;
  if(swarmOn){var fp=getSwarmDronePayload(0,startPos[0],startPos[1],initAlt,p.lat,p.lng);if(fp)sendUpdate(fp);}
  else{var iv=applyVariations(startPos[0],startPos[1],initAlt);sendUpdate({basic_id:document.getElementById('basicId').value,drone_altitude:Math.round(iv.alt),drone_lat:iv.lat,drone_long:iv.lng,pilot_lat:p.lat,pilot_long:p.lng});}
  if(simIndex===null){simIndex=0;segmentOffset=0;if(droneMarker)droneMarker.setLatLng(path[0]);else droneMarker=L.marker(path[0],{icon:createIcon('UAV')}).addTo(map);}
  setStatusCircle('#00cc00');
  if(lastHighlight)map.removeLayer(lastHighlight);
  lastHighlight=L.circle(path[path.length-1],{radius:12,color:'#7DF9FF',fill:false,weight:2}).addTo(map);
  if(path.length>1){if(loopLine)map.removeLayer(loopLine);loopLine=L.polyline([path[path.length-1],path[0]],{color:'rgba(125,249,255,0.3)',weight:1,dashArray:'6,8'}).addTo(map);}
  moveSegment(simIndex,segmentOffset);
  if(swarmOn){stopSwarmAnimation();animateSwarmDrones();}
  startTxLoop();
  updateTicker('playing');
};

// ── PAUSE ──

document.getElementById('pause').onclick=function(){
  flash('pause');
  if(missionState!=='playing')return;
  missionState='paused';playing=false;
  stopSwarmAnimation();
  sendCommand('/api/pause');
  setStatusCircle('#ffa500');
  updateTicker('paused');
};

// ── STOP ──

document.getElementById('stop').onclick=function(){
  flash('stop');
  if(missionState==='idle')return;
  killTxLoop();
  missionState='idle';playing=false;
  stopSwarmAnimation();
  sendCommand('/api/stop');
  simIndex=null;segmentOffset=0;
  setStatusCircle('#ff3333');
  updateTicker('idle');clearTelemetry();
  clearSwarmMarkers();clearSwarmPolylines();
  swarmDrones.forEach(function(sd,si){sd.active=false;sd.flightPath=null;sd.simIndex=0;sd.segmentOffset=0;var el=document.getElementById('swarmStatus_'+si);if(el)el.className='drone-status';});
  swarmTxIndex=0;
};

// ── serial status polling ──

var connectedBoardCount=0;
function updateSerialStatus(){
  fetch('/api/serial_status').then(function(r){return r.json();}).then(function(s){
    var el=document.getElementById('serialStatus');
    var roster=document.getElementById('boardRoster');
    var addBtn=document.getElementById('addBoardBtn');
    if(!s.boards||s.boards.length===0){
      el.innerHTML='<span style="color:red;">NO BOARDS</span>';
      if(roster)roster.innerHTML='<div style="font-size:12px;color:rgba(255,255,255,0.2);">No boards connected</div>';
      connectedBoardCount=0;
      if(addBtn)addBtn.style.display='block';
      return;
    }
    connectedBoardCount=s.boards.length;
    if(addBtn)addBtn.style.display=s.boards.length>=3?'none':'block';
    var barHtml='',rosterHtml='';
    s.boards.forEach(function(b,i){
      var dot=b.connected?'on':'off';
      var col=b.label==='C5'?'#7DF9FF':'#FF00FF';
      var portShort=b.port.split('/').pop();
      barHtml+='<span class="board-pill"><span class="dot '+dot+'"></span><span style="color:'+col+';">'+b.label+'</span><span style="color:rgba(255,255,255,0.35);font-size:10px;">'+portShort+'</span></span>';
      rosterHtml+='<div class="board-row"><span class="b-dot '+dot+'"></span><span class="b-label" style="color:'+col+';">'+b.label+'</span><span class="b-port">'+portShort+'</span><button onclick="removeBoard(&apos;'+b.port.replace(/'/g,"&apos;")+'&apos;)" style="padding:2px 6px;font-size:9px;background:transparent;color:#ff3333;border:1px solid rgba(255,51,51,0.3);cursor:pointer;font-family:inherit;margin-left:4px;">X</button></div>';
    });
    el.innerHTML=barHtml;
    if(roster)roster.innerHTML=rosterHtml;
  }).catch(function(){});
}

function showAddBoard(){
  var row=document.getElementById('addBoardRow');
  if(row.style.display==='none'){
    fetch('/api/ports').then(function(r){return r.json();}).then(function(d){
      var sel=document.getElementById('addBoardPort');
      sel.innerHTML='<option value="">[ SELECT ]</option>';
      d.ports.forEach(function(p){
        if(d.used.indexOf(p)===-1)sel.innerHTML+='<option value="'+p+'">'+p+'</option>';
      });
      row.style.display='block';
    });
  }else{row.style.display='none';}
}

function doAddBoard(){
  var port=document.getElementById('addBoardPort').value;
  var label=document.getElementById('addBoardLabel').value;
  if(!port)return;
  fetch('/api/add_board',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:port,label:label})}).then(function(r){return r.json();}).then(function(d){
    document.getElementById('addBoardRow').style.display='none';
    updateSerialStatus();
  }).catch(console.error);
}

function removeBoard(port){
  if(!confirm('Remove board '+port+'?'))return;
  fetch('/api/remove_board',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:port})}).then(function(r){return r.json();}).then(function(d){
    updateSerialStatus();
  }).catch(console.error);
}

setInterval(updateSerialStatus,2000);
updateSerialStatus();

// ── clear paths ──

document.getElementById('clearPaths').onclick=function(){
  flash('clearPaths');
  if(missionState!=='idle')document.getElementById('stop').click();
  waypointMarkers.forEach(function(m){map.removeLayer(m);});waypointMarkers=[];
  path=[];poly.setLatLngs(path);
  if(loopLine){map.removeLayer(loopLine);loopLine=null;}
  if(firstHighlight){map.removeLayer(firstHighlight);firstHighlight=null;}
  if(lastHighlight){map.removeLayer(lastHighlight);lastHighlight=null;}
  if(droneMarker){map.removeLayer(droneMarker);droneMarker=null;}
  if(statusCircle){map.removeLayer(statusCircle);statusCircle=null;}
  stopSwarmAnimation();clearSwarmMarkers();clearSwarmPolylines();
  simIndex=null;segmentOffset=0;missionState='idle';playing=false;
  updateTicker('idle');clearTelemetry();
};
</script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    global boards
    ports = [p.device for p in list_ports.comports()]
    if request.method == 'POST':
        # close existing connections
        for b in boards:
            try:
                if b['ser'] and b['ser'].is_open:
                    b['ser'].close()
            except Exception:
                pass
        new_boards = []
        for i in range(MAX_BOARDS):
            port = request.form.get(f'port_{i}', '').strip()
            label = request.form.get(f'label_{i}', 'S3').strip()
            if not port:
                continue
            # skip duplicate ports
            if any(b['port'] == port for b in new_boards):
                continue
            s = None
            try:
                s = serial.Serial(port, BAUD_RATE, timeout=1)
            except Exception:
                s = None
            new_boards.append({'port': port, 'ser': s, 'lock': threading.Lock(), 'label': label})
        boards = new_boards
        return redirect(url_for('map_view'))
    active_ports = [boards[i]['port'] if i < len(boards) else '' for i in range(MAX_BOARDS)]
    active_labels = [boards[i]['label'] if i < len(boards) else 'S3' for i in range(MAX_BOARDS)]
    bc = sum(1 for b in boards if b['ser'] and b['ser'].is_open)
    return render_template_string(PORT_SELECT_HTML, ports=ports, ascii_art=ASCII_ART,
                                  active_ports=active_ports, active_labels=active_labels,
                                  boards_connected=bc)

@app.route('/map')
def map_view():
    resp = app.make_response(render_template_string(HTML))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

def _write_one(board, data_str):
    """Write to a single board with reconnect logic."""
    with board['lock']:
        if board['ser'] is None or not board['ser'].is_open:
            try:
                board['ser'] = serial.Serial(board['port'], BAUD_RATE, timeout=1)
            except Exception:
                board['ser'] = None
                return False
        try:
            board['ser'].write((data_str + "\n").encode('ascii'))
            board['ser'].flush()
            return True
        except Exception:
            try:
                board['ser'].close()
            except Exception:
                pass
            try:
                board['ser'] = serial.Serial(board['port'], BAUD_RATE, timeout=1)
                board['ser'].write((data_str + "\n").encode('ascii'))
                board['ser'].flush()
                return True
            except Exception:
                board['ser'] = None
                return False

def safe_serial_write(data_str, board_index=None):
    """Write to one board (by index) or all boards (None)."""
    if board_index is not None:
        if board_index < len(boards):
            return _write_one(boards[board_index], data_str)
        return False
    ok = False
    for b in boards:
        if _write_one(b, data_str):
            ok = True
    return ok

@app.route('/api/start', methods=['POST'])
def start():
    global play_active
    play_active = True
    data = request.get_json()
    if not data:
        return jsonify(status='error', msg='no payload'), 400
    start_cmd = {"action": "start", "basic_id": data.get("basic_id", ""), "drone_altitude": data.get("drone_altitude", 0)}
    safe_serial_write(json.dumps(start_cmd))
    try:
        with open(PATH_CSV, 'a', newline='') as f:
            csv.writer(f).writerow([datetime.now().isoformat(), json.dumps(data.get('path', []))])
    except Exception:
        pass
    return jsonify(status='ok')

@app.route('/api/pause', methods=['POST'])
def pause_api():
    safe_serial_write(json.dumps({"action": "pause"}))
    return jsonify(status='paused')

@app.route('/api/stop', methods=['POST'])
def stop():
    global play_active
    play_active = False
    for _ in range(3):
        if safe_serial_write(json.dumps({"action": "stop"})):
            break
        time.sleep(0.05)
    return jsonify(status='stopped')

@app.route('/api/update', methods=['POST'])
def update_position():
    if not play_active:
        return jsonify(status='idle'), 200
    data = request.get_json()
    if not data or 'drone_lat' not in data or 'drone_long' not in data:
        return jsonify(status='error', msg='missing fields'), 400
    safe_serial_write(json.dumps(data))
    return jsonify(status='ok')

@app.route('/api/buzzer', methods=['POST'])
def buzzer_toggle():
    data = request.get_json()
    muted = data.get('muted', False) if data else False
    safe_serial_write(json.dumps({"buzzer_mute": muted}))
    return jsonify(status='ok', muted=muted)

@app.route('/api/led', methods=['POST'])
def led_toggle():
    data = request.get_json()
    muted = data.get('muted', False) if data else False
    safe_serial_write(json.dumps({"led_mute": muted}))
    return jsonify(status='ok', muted=muted)

@app.route('/api/band', methods=['POST'])
def band_config():
    data = request.get_json()
    if not data:
        return jsonify(status='error', msg='no payload'), 400
    payload = {}
    if 'band_mode' in data:
        payload['band_mode'] = data['band_mode']
    if 'channels_5g' in data:
        payload['channels_5g'] = data['channels_5g']
    safe_serial_write(json.dumps(payload))
    return jsonify(status='ok')

@app.route('/api/serial_status', methods=['GET'])
def serial_status():
    available = [p.device for p in list_ports.comports()]
    board_list = []
    for b in boards:
        if b['port'] not in available:
            with b['lock']:
                try:
                    if b['ser'] and b['ser'].is_open:
                        b['ser'].close()
                except Exception:
                    pass
                b['ser'] = None
        else:
            with b['lock']:
                if b['ser'] is None or not b['ser'].is_open:
                    try:
                        b['ser'] = serial.Serial(b['port'], BAUD_RATE, timeout=1)
                    except Exception:
                        b['ser'] = None
        board_list.append({
            "port": b['port'],
            "label": b['label'],
            "connected": bool(b['ser'] and b['ser'].is_open)
        })
    return jsonify({"boards": board_list, "count": len(boards)})

@app.route('/api/ports', methods=['GET'])
def list_ports_api():
    available = [p.device for p in list_ports.comports()]
    used = [b['port'] for b in boards]
    return jsonify({"ports": available, "used": used})

@app.route('/api/add_board', methods=['POST'])
def add_board():
    global boards
    if len(boards) >= MAX_BOARDS:
        return jsonify(status='error', msg='max 3 boards'), 400
    data = request.get_json()
    port = data.get('port', '').strip() if data else ''
    label = data.get('label', 'S3').strip() if data else 'S3'
    if not port:
        return jsonify(status='error', msg='no port'), 400
    if any(b['port'] == port for b in boards):
        return jsonify(status='error', msg='port already in use'), 400
    s = None
    try:
        s = serial.Serial(port, BAUD_RATE, timeout=1)
    except Exception:
        s = None
    boards.append({'port': port, 'ser': s, 'lock': threading.Lock(), 'label': label})
    return jsonify(status='ok', connected=bool(s and s.is_open))

@app.route('/api/remove_board', methods=['POST'])
def remove_board():
    global boards
    data = request.get_json()
    port = data.get('port', '').strip() if data else ''
    new_boards = []
    for b in boards:
        if b['port'] == port:
            try:
                if b['ser'] and b['ser'].is_open:
                    b['ser'].close()
            except Exception:
                pass
        else:
            new_boards.append(b)
    boards = new_boards
    return jsonify(status='ok', count=len(boards))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
