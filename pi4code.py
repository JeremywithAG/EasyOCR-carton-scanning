import os
import time
import threading
import requests
import paho.mqtt.client as mqtt
from picamera2 import Picamera2
from libcamera import controls

# ── Config ────────────────────────────────────────────────────
LAPTOP_IP  = "192.168.137.134"
UPLOAD_URL = f"http://{LAPTOP_IP}:5000/upload"
BROKER     = LAPTOP_IP
TOPIC      = "camera/capture"
DEVICE_ID  = "2"              # set to "2" on the other Pi
SAVE_DIR   = "captures"
IMAGE_PATH = os.path.join(SAVE_DIR, "temp.jpg")
os.makedirs(SAVE_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# Shared camera instance
picam2 = Picamera2()
camera_ready = threading.Event()

def init_camera():
    config = picam2.create_still_configuration(main={"size": (2304, 1296)})
    picam2.configure(config)
    picam2.start()
    picam2.set_controls({
        "AfMode": controls.AfModeEnum.Manual,
        "LensPosition": 3.33,   # 1/0.3m ≈ 3.33 dioptres → focus at ~30 cm
    })
    time.sleep(1)   # let the lens settle
    camera_ready.set()
    print(f"[Device {DEVICE_ID}] Camera ready (focus ≈ 30 cm).")

def upload_image(path):
    try:
        with open(path, "rb") as f:
            files = {"file": ("photo.jpg", f, "image/jpeg")}
            data  = {"device_id": DEVICE_ID}
            r = requests.post(UPLOAD_URL, files=files, data=data, timeout=30)
        print(f"[Device {DEVICE_ID}] Upload → {r.status_code} {r.text}")
    except Exception as e:
        print(f"[Device {DEVICE_ID}] Upload error: {e}")

def capture_and_upload():
    """Run in a thread so MQTT loop stays unblocked."""
    if not camera_ready.is_set():
        print(f"[Device {DEVICE_ID}] Camera not ready yet, skipping.")
        return
    try:
        picam2.capture_file(IMAGE_PATH)
        print(f"[Device {DEVICE_ID}] Captured {IMAGE_PATH}")
        upload_image(IMAGE_PATH)
    except Exception as e:
        print(f"[Device {DEVICE_ID}] Capture error: {e}")

# ── MQTT callbacks ────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(TOPIC, qos=1)
        print(f"[Device {DEVICE_ID}] Subscribed to '{TOPIC}'")
    else:
        print(f"[Device {DEVICE_ID}] MQTT connect failed: {reason_code}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode().strip()
    targeted_ids = [d.strip() for d in payload.split(",")]
    if DEVICE_ID in targeted_ids:
        print(f"[Device {DEVICE_ID}] Triggered! Starting capture...")
        threading.Thread(target=capture_and_upload, daemon=True).start()
    else:
        print(f"[Device {DEVICE_ID}] Message received but not for me ({payload}), ignoring.")

# ─────────────────────────────────────────────────────────────
def main():
    # Start camera init in background so MQTT connects immediately
    threading.Thread(target=init_camera, daemon=True).start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 1883, keepalive=60)
    print(f"[Device {DEVICE_ID}] Connecting to broker at {BROKER}…")

    try:
        client.loop_forever()       # blocks here; Ctrl+C to quit
    finally:
        picam2.stop()
        picam2.close()
        print(f"[Device {DEVICE_ID}] Shut down.")

if __name__ == "__main__":
    main()