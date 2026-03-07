# Remote-ID-Spoofer

![WiFi Remote ID Spoofer & Simulator](spoof.png)

**An OUI Spy firmware for WiFi-based FAA Remote ID spoofing and simulation.**

Part of the [OUI Spy](https://github.com/colonelpanichacks) ecosystem -- built for the Seeed Studio XIAO ESP32-S3 and compatible ESP32-S3 boards (M5Stack Stamp S3).

Inspired by [d0tslash](https://github.com/d0tslash) and **H.A.R.D** (Hackers Against Remote ID).

---

## Legal Disclaimer

> **WARNING: READ THIS BEFORE USE.**
>
> This software is provided strictly for **educational, research, and authorized security testing purposes only**.
>
> **Transmitting spoofed or falsified Remote ID signals is illegal in many jurisdictions**, including but not limited to violations of:
>
> - **United States**: FAA 14 CFR Part 89 (Remote Identification of Unmanned Aircraft), FCC regulations on unauthorized radio transmissions
> - **European Union**: EU Regulation 2019/945 and 2019/947 (U-Space / Remote ID requirements)
> - **United Kingdom**: CAA regulations on drone identification
> - **Canada**: Transport Canada RPAS regulations
> - **Australia**: CASA Remote ID requirements
>
> Unauthorized transmission of spoofed Remote ID broadcasts may constitute a **federal crime** and can result in:
> - Criminal prosecution and imprisonment
> - Significant fines (up to $250,000+ USD)
> - Seizure of equipment
> - Civil liability
>
> **You are solely responsible for ensuring compliance with all applicable local, national, and international laws and regulations before operating this software.** The authors, contributors, and distributors of this project accept **no liability** for any misuse, legal violations, damages, or consequences resulting from the use of this software.
>
> **Do not operate this software near active airspace, airports, or in any manner that could interfere with aviation safety or emergency operations.**
>
> By using this software, you acknowledge that you have read, understood, and agree to these terms.

---

## Overview

This project provides:

- **ESP32-S3 Firmware** capable of broadcasting WiFi-based ASTM F3411 Remote ID via NAN action frames and AP beacon vendor IEs
- **Flask Web UI** with a dark cyberpunk interface for mission planning, real-time flight simulation, and live telemetry
- **Realistic Variation Engine** with per-parameter toggles for altitude drift, speed variation, GPS jitter, heading wobble, and TX timing jitter
- **Swarm Mode** for multi-drone spoofing with configurable formations, flight paths, and independent ID management
- **Hardware Feedback** with buzzer (Close Encounters boot tone, heartbeat during TX) and LED indicators with mute controls
- **Live Telemetry** showing real-time broadcast data, coordinates, altitude, TX count, and per-drone swarm feeds

## Features

### Mission Control (Left Panel)
- Remote ID configuration with altitude and speed inputs
- Map-based waypoint flight path planning (click to drop waypoints)
- Play / Pause / Stop state machine with visual indicators
- Hardware mute toggles for buzzer and LED
- Realistic Variations with individual ON/OFF toggles and range sliders:
  - Altitude Drift (Perlin noise, Sine wave, or Random Walk patterns)
  - Speed Variation
  - GPS Jitter
  - Heading Wobble
  - TX Timing Jitter
- Live broadcast telemetry feed (RID, altitude, lat/lng, pilot position, TX count, state)

### Swarm Mode (Right Panel)
- Spoof up to 20 simultaneous drone IDs
- ID modes: Random, Prefix-based, or Manual entry
- Configurable spread (lateral, altitude, speed)
- Formation options: Scatter, Line, Circle, V-Formation
- Flight path modes: Formation Lock, Offset Paths, Random Routes
- Stagger start for realistic appearance
- Live swarm telemetry feed showing all active drone positions

### Broadcast
- WiFi NAN Action Frames (primary ASTM F3411 transport)
- WiFi NAN Sync Beacons
- AP Beacon Vendor Information Elements via `esp_wifi_set_vendor_ie`
- 1Hz broadcast rate matching real Remote ID transmitters
- Proper ODID message pack encoding (Basic ID, Location/Vector, System, Operator ID)
- **Dual-band on ESP32-C5**: 2.4GHz + 5GHz (UNII-3: ch149, 153, 157, 161, 165) with per-channel toggles
- Band mode selector: 2.4 Only, 5GHz Only, or Dual Band

### Status Ticker
- Red pulsing "SPOOFING ACTIVE" banner with live TX count during broadcast
- Orange "PAUSED" indicator when mission is paused
- Auto-hides when stopped

## Hardware

### Supported Boards

| Board | WiFi | 5GHz | Buzzer | LED |
|-------|------|------|--------|-----|
| **Seeed XIAO ESP32-C5** | WiFi 6 | 2.4 + 5GHz | GPIO25 (D2) | GPIO27 (active HIGH) |
| **Seeed XIAO ESP32-S3** | WiFi 4 | 2.4GHz only | GPIO3 (D2) | GPIO21 (active LOW) |
| **M5Stack Stamp S3** | WiFi 4 | 2.4GHz only | GPIO1 (wire your own) | GPIO21 (SK6812 NeoPixel RGB) |

Pin mapping and band capability auto-detected at compile time.

### Optional
- Passive buzzer on D2 pin for audio feedback (XIAO boards) or GPIO1 (M5Stack Stamp S3)
- Built-in LED for visual feedback (NeoPixel RGB on M5Stack Stamp S3)

## Getting Started

### 1. Clone
```bash
git clone https://github.com/colonelpanichacks/Remote-ID-Spoofer.git
cd Remote-ID-Spoofer
```

### 2. Flash Firmware
Connect via USB and flash with PlatformIO:
```bash
# ESP32-C5 (dual-band)
pio run -e seeed_xiao_esp32c5 -t upload

# ESP32-S3 — Seeed XIAO (single-band)
pio run -e seeed_xiao_esp32s3 -t upload

# ESP32-S3 — M5Stack Stamp S3 (single-band)
pio run -e m5stack_stamps3 -t upload
```

> **Note (M5Stack Stamp S3):** If the board is not detected, hold the **G0** button while plugging USB, then release to enter download mode. The Stamp S3 uses a built-in SK6812 NeoPixel RGB LED on GPIO21 (green flash on TX) and requires the Adafruit NeoPixel library (automatically pulled by PlatformIO).

### 3. Install Python Dependencies
```bash
pip install flask pyserial
```

### 4. Run
```bash
python spoofer.py
```
Open `http://localhost:5000` in your browser, select the serial port, and you're in.

## Usage

1. Enter a Remote ID, set altitude and speed
2. Click "Set Pilot Location" and click the map to place the pilot
3. Click the map to drop waypoints for the flight path
4. Hit **Play** -- the drone marker follows the path while broadcasting Remote ID
5. Adjust any variation slider or toggle mid-flight -- changes apply immediately
6. Enable **Swarm Mode** on the right panel to spoof multiple drones simultaneously
7. Monitor the **Live Broadcast** telemetry feed at the bottom of each panel

## Architecture

```
Browser (Flask Web UI)
    |
    | JSON over HTTP (start/stop/pause/update)
    |
Flask Server (spoofer.py)
    |
    | JSON over Serial (USB)
    |
ESP32-S3 Firmware (main.cpp)
    |
    | WiFi Raw TX (NAN frames) + Vendor IE (AP beacons)
    |
Over-the-air Remote ID broadcast
```

## OUI Spy Ecosystem

Part of the [OUI Spy](https://github.com/colonelpanichacks/oui-spy) hardware & firmware platform for the Seeed Studio XIAO ESP32 family. More info and hardware at [colonelpanic.tech](https://colonelpanic.tech).

### Unified Firmware

| Firmware | Description | Board |
|----------|-------------|-------|
| [OUI Spy Unified Blue](https://github.com/colonelpanichacks/oui-spy-unified-blue) | All-in-one: Detector + Foxhunter + Flock-You + Sky Spy with WiFi boot selector | ESP32-S3 / ESP32-C5 |

### Standalone Firmwares

| Firmware | Description | Board |
|----------|-------------|-------|
| [OUI-SPY Detector](https://github.com/colonelpanichacks/ouispy-detector) | Multi-target BLE scanner with OUI filtering and web config | ESP32-S3 |
| [OUI-SPY Foxhunter](https://github.com/colonelpanichacks/ouispy-foxhunter) | Precision BLE proximity tracker for radio direction finding | ESP32-S3 |
| [Flock-You](https://github.com/colonelpanichacks/flock-you) | Flock Safety & Raven surveillance detector with GPS wardriving | ESP32-S3 |
| [Sky Spy](https://github.com/colonelpanichacks/Sky-Spy) | Drone Remote ID detector — WiFi + BLE, multi-drone tracking | ESP32-S3 |
| **Remote-ID-Spoofer** *(this repo)* | Remote ID spoofer & simulator with swarm mode | ESP32-S3 / ESP32-C5 / M5Stack Stamp S3 |
| [OUI-SPY UniPwn](https://github.com/colonelpanichacks/Oui-Spy-UniPwn) | Unitree robot BLE exploitation with AutoPwn and web UI | ESP32-S3 |

## Credits

- [colonelpanic.tech](https://colonelpanic.tech)
- Inspired by [d0tslash](https://github.com/d0tslash) and **H.A.R.D** (Hackers Against Remote ID)
- Open Drone ID protocol implementation based on [opendroneid-core-c](https://github.com/opendroneid/opendroneid-core-c)

## License

Distributed under the MIT License. See `LICENSE` for details.

---

**Use responsibly. Know your laws. Hack the planet.**
