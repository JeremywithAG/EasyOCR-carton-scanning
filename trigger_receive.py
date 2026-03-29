import paho.mqtt.client as mqtt
import msvcrt
import threading
import os
import time
from flask import Flask, request


# ── Config ────────────────────────────────────────────────────
BROKER           = "localhost"
TOPIC            = "camera/capture"
SAVE_DIR         = "omnidirectional picture"
EXPECTED_DEVICES = {"1", "2", "3", "4", "5"}
os.makedirs(SAVE_DIR, exist_ok=True)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER, 1883, keepalive=60)
client.loop_start()
# ─────────────────────────────────────────────────────────────

# ── Timing state ──────────────────────────────────────────────
state = {
    "trigger_time":     None,
    "received_devices": set(),
    "arrival_times":    {},
}
timing_lock = threading.Lock()
# ─────────────────────────────────────────────────────────────

# ── Flask upload server ───────────────────────────────────────
app = Flask(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/upload", methods=["POST"])
def upload():
    arrival_time = time.perf_counter()

    if "file" not in request.files:
        return "No file uploaded", 400

    f = request.files["file"]

    if f.filename == "":
        return "Empty filename", 400

    if not allowed_file(f.filename):
        return "Invalid file type", 400

    device_id = request.form.get("device_id", "").strip()

    if device_id not in EXPECTED_DEVICES:
        return "Invalid or missing device_id. Use 1, 2, 3, 4, or 5.", 400

    filename  = f"image_{device_id}.jpg"
    save_path = os.path.join(SAVE_DIR, filename)
    f.save(save_path)

    with timing_lock:
        t0 = state["trigger_time"]
        if t0 is not None:
            elapsed = arrival_time - t0
            state["received_devices"].add(device_id)
            count     = len(state["received_devices"])
            remaining = EXPECTED_DEVICES - state["received_devices"]

            print(f"[Flask] image_{device_id} received  |  "
                  f"+{elapsed:.3f}s since trigger  |  "
                  f"{count}/{len(EXPECTED_DEVICES)} images received", flush=True)
            #client.publish("scan/start", "1,2,3,4,5", qos=1) #if only using one pi
            state["arrival_times"][device_id] = elapsed
            if not remaining:
                slowest_device = max(state["arrival_times"], key=state["arrival_times"].get)
                slowest_time   = state["arrival_times"][slowest_device]
                print("-" * 55, flush=True)
                print(f"[Timing] All {len(EXPECTED_DEVICES)} images received in "
                      f"{slowest_time:.3f}s", flush=True)
                print("-" * 55, flush=True)
                client.publish("scan/start", "1,2,3,4,5", qos=1) #uncomment to only send when all 5 images are received
                print("[MQTT] Notified scan_node to start processing.", flush=True)
        else:
            print(f"[Flask] Saved {filename} (no active timing session)", flush=True)

    return f"Saved {filename} in '{SAVE_DIR}'", 200

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
# ─────────────────────────────────────────────────────────────

# ── MQTT keyboard trigger ─────────────────────────────────────
def get_key():
    return msvcrt.getwch().upper()

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("[Flask] Upload server running on port 5000", flush=True)



    print("\nMQTT trigger ready.")
    print("  Press C  → trigger all cameras (1,2,3,4,5)")
    print("  Press Q  → quit\n")

    while True:
        key = get_key()

        if key == "C":
            with timing_lock:
                state["received_devices"] = set()
                state["trigger_time"]     = time.perf_counter()

            payload = "1,2,3,4,5"
            client.publish(TOPIC, payload, qos=1)
            print(f"\n[MQTT] Trigger sent → devices {payload}")
            print(f"[MQTT] Timer started — waiting for {len(EXPECTED_DEVICES)} images...\n")

        elif key == "Q":
            print("Exiting.")
            break

    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()
