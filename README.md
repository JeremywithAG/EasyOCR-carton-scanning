# Omnidirectional Barcode & OCR Product Scanner

A multi-camera warehouse scanning system that uses 5 Raspberry Pi cameras arranged omnidirectionally to identify products via barcode detection and OCR, matched against a MySQL database. Results are published via MQTT and optionally bridged into a ROS2 network.

---

## System Architecture

```
Raspberry Pi ×5          Windows PC                  Ubuntu VM (ROS2)
─────────────────        ──────────────────────       ─────────────────────
camera.py                Mosquitto broker             trigger_node.py
 ├─ MQTT subscriber  ←── camera/capture topic         (optional ROS trigger)
 ├─ picamera2        ──► HTTP POST /upload ──►
 └─ captures image       trigger.py (Flask :5000)     result_bridge_node.py
                          └─ scan_and_lookup.py   ──► /scan/result ROS topic
                              ├─ pyzbar (barcode)
                              ├─ EasyOCR
                              └─ MySQL lookup
                                      │
                                 scan/result MQTT
```

---

## Features

- Omnidirectional scanning using 5 Raspberry Pi cameras
- Barcode and QR code detection via `pyzbar`
- OCR fallback using `EasyOCR` for printed text
- Variance check to skip blank/empty faces before OCR
- Confidence threshold filtering for OCR results
- MySQL database lookup by EAN, SKU, or product name
- Early stop — stops processing remaining images once a match is found
- MQTT-based trigger system for camera coordination
- HTTP POST image transfer via Flask
- Optional ROS2 integration — results published to `/scan/result` topic

---

## Project Structure

```
project/
├── trigger.py              # Windows — keyboard trigger + Flask image receiver
├── scan_and_lookup.py      # Windows — full OCR/barcode pipeline, MQTT node
├── camera.py               # Raspberry Pi — MQTT subscriber + camera + uploader
└── ros/
    └── scanner_pkg/
        ├── trigger_node.py         # ROS2 — fires cameras via ROS topic
        ├── result_bridge_node.py   # ROS2 — bridges MQTT result to ROS topic
        ├── package.xml
        └── setup.py
```

---

## Hardware Requirements

- 5× Raspberry Pi (any model with camera support)
- 5× Raspberry Pi Camera Module
- Windows PC (processing + MQTT broker)
- Ubuntu 22.04 VM or machine (optional, for ROS2)

---

## Software Requirements

### Windows PC

```
Python 3.x
mosquitto (MQTT broker)
MySQL Server
```

Python packages:
```
pip install paho-mqtt flask easyocr opencv-python mysql-connector-python pyzbar
```

System:
- [Mosquitto MQTT Broker](https://mosquitto.org/download/)
- [MySQL Server](https://dev.mysql.com/downloads/)

### Raspberry Pi

```
pip install paho-mqtt picamera2 requests
```

### Ubuntu VM (ROS2 — optional)

```
ROS2 Humble
pip install paho-mqtt
```

---

## Setup

### 1. Mosquitto Broker (Windows)

Edit `C:\Program Files\mosquitto\mosquitto.conf`:
```
listener 1883
allow_anonymous true
```

Start the broker:
```powershell
net start mosquitto
```

### 2. MySQL Database

Create a database and table:
```sql
CREATE DATABASE ceva_1000_sku;
USE ceva_1000_sku;

CREATE TABLE CEVA_Product_List (
    sku          VARCHAR(50),
    product_name VARCHAR(255),
    EAN_number   VARCHAR(50)
);
```

Update `DB_CONFIG` in `scan_and_lookup.py` with your credentials.

### 3. Raspberry Pi Configuration

In `camera.py`, set:
```python
LAPTOP_IP = "192.168.x.x"   # your Windows PC IP
DEVICE_ID = "1"              # unique ID per Pi (1–5)
```

Run on each Pi:
```bash
python camera.py
```

### 4. Windows — Trigger & Scanner

In `trigger.py`, confirm:
```python
BROKER = "localhost"   # Mosquitto is on this PC
```

Run both scripts in separate terminals:
```bash
# Terminal 1
python trigger.py

# Terminal 2
python scan_and_lookup.py
```

---

## Usage

1. Start Mosquitto on Windows
2. Start `scan_and_lookup.py` — it waits for images
3. Start `trigger.py` — Flask server starts on port 5000
4. Run `camera.py` on each Raspberry Pi
5. Press **C** in the `trigger.py` terminal to fire all cameras
6. Images are received, processed, and the first match is printed and published to MQTT `scan/result`

### Output Example

```
==================================================
Processing: omnidirectional picture/image_2.jpg
==================================================

[STEP 1] Scanning for Barcode / QR Code...
✔ Barcode/QR detected!
  Type        : EAN13
  Data        : 9310015393052

[STEP 2] Looking up EAN in database...
  ✔ MATCH FOUND:

    SKU       : ABC-001
    Name      : Matte Surface Spray 500ml
    EAN Number: 9310015393052

✔ Match found in image_2.jpg — stopping early.
[scan_node] Result published to MQTT.
```

---

## ROS2 Integration (Optional)

### Setup

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python scanner_pkg

# copy node files into scanner_pkg/scanner_pkg/
# update setup.py entry_points

cd ~/ros2_ws
colcon build
source install/setup.bash
```

### Running

```bash
# Terminal 1 — optional: fire cameras from ROS
ros2 run scanner_pkg trigger_node

# Terminal 2 — bridge MQTT result into ROS
ros2 run scanner_pkg result_bridge_node

# Terminal 3 — watch results
ros2 topic echo /scan/result

# Fire cameras via ROS
ros2 topic pub /scan/trigger std_msgs/msg/String "data: '1,2,3,4,5'" --once
```

Set `BROKER` in both ROS nodes to your Windows PC IP:
```python
BROKER = "192.168.x.x"   # Windows PC running Mosquitto
```

---

## How It Works

### Scanning Pipeline

Each image goes through 5 steps:

1. **Barcode/QR scan** — `pyzbar` decodes any standard barcode or QR code and looks up the EAN in the database directly
2. **Variance check** — Laplacian variance detects blank faces with no product label, skipping OCR to save time
3. **EasyOCR** — reads all visible text with a confidence threshold of 60%
4. **Database lookup** — numbers are looked up by EAN, strings by product name
5. **Result intersection** — if multiple text detections match different products, the most common SKU is selected

### MQTT Topics

| Topic | Direction | Purpose |
|---|---|---|
| `camera/capture` | PC → Pi | Trigger cameras to take photo |
| `scan/start` | PC → PC | Tell scanner that images are ready |
| `scan/result` | PC → all | Publish matched product as JSON |

### Early Stop

Once a match is found in any of the 5 images, processing stops immediately — remaining images are skipped. A new press of **C** resets the session.

---

## Configuration Reference

### `scan_and_lookup.py`

| Variable | Default | Description |
|---|---|---|
| `BROKER` | `"localhost"` | Mosquitto broker IP |
| `CONFIDENCE_THRESHOLD` | `0.60` | Minimum EasyOCR confidence |
| `is_blank_face threshold` | `50` | Laplacian variance cutoff |
| `text_threshold` | `0.60` | EasyOCR internal detector threshold |

### `camera.py`

| Variable | Description |
|---|---|
| `LAPTOP_IP` | Windows PC IP address |
| `DEVICE_ID` | Unique camera ID (1–5) |
| Camera resolution | `2304 × 1296` |

---

## Acknowledgements

- [EasyOCR](https://github.com/JaidedAI/EasyOCR)
- [pyzbar](https://github.com/NaturalHistoryMuseum/pyzbar)
- [Picamera2](https://github.com/raspberrypi/picamera2)
- [Eclipse Mosquitto](https://mosquitto.org/)
- [ROS2 Humble](https://docs.ros.org/en/humble/)
