import cv2
import easyocr
import time
import numpy as np
import mysql.connector
from pyzbar.pyzbar import decode
from collections import Counter
import paho.mqtt.client as mqtt
import json

# ── DB CONFIG ────────────────────────────────────────
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "12345",
    "database": "ceva_1000_sku",
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def lookup_by_partial_name(product_name: str):
    sql = """
    SELECT sku, product_name
    FROM CEVA_Product_List
    WHERE product_name LIKE %s;
    """
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, (f"%{product_name}%",))
            return cur.fetchall()

def lookup_by_partial_sku(sku: str):
    sql = """
    SELECT sku, product_name
    FROM CEVA_Product_List
    WHERE sku LIKE %s;
    """
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, (f"%{sku}%",))
            return cur.fetchall()

def lookup_by_EAN(EAN_num: str):
    sql = """
    SELECT sku, product_name, EAN_number
    FROM CEVA_Product_List
    WHERE EAN_number LIKE %s;
    """
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, (f"%{EAN_num}%",))
            return cur.fetchall()

def is_number(text: str):
    return text.strip().replace(" ", "").isdigit()

# ── VARIANCE CHECK ────────────────────────────────────
def is_blank_face(image, threshold=50):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    print(f"  Variance Score: {variance:.2f} (threshold: {threshold})")
    return variance < threshold

# ── LOAD EASYOCR ONCE ─────────────────────────────────
print("Loading EasyOCR model...")
reader = easyocr.Reader(['en'], gpu=True)
print("✔ Model loaded.")

# ── MAIN PIPELINE ────────────────────────────────────
def scan_and_lookup(image_path):
    program_start = time.time()

    print("=" * 50)
    print(f"Processing: {image_path}")
    print("=" * 50)

    image = cv2.imread(image_path)
    if image is None:
        print("Error: Cannot load image.")
        print(f"\n  Total Program Runtime: {time.time() - program_start:.4f} seconds")
        return

    # ── STEP 1: BARCODE/QR ───────────────────────────
    print("\n[STEP 1] Scanning for Barcode / QR Code...")
    start = time.time()
    barcodes = decode(image)
    end = time.time()

    if barcodes:
        print("✔ Barcode/QR detected!")
        for barcode in barcodes:
            data = barcode.data.decode("utf-8")
            print(f"  Type        : {barcode.type}")
            print(f"  Data        : {data}")
            print(f"  Bounding Box: {barcode.rect}")
        print(f"  Detection Time: {end - start:.4f} seconds")

        print("\n[STEP 2] Looking up EAN in database...")
        db_start = time.time()
        matched = False
        for barcode in barcodes:
            data = barcode.data.decode("utf-8").strip()
            print(f"  Searching EAN: '{data}'")
            rows = lookup_by_EAN(data)
            if rows:
                print("\n  ✔ MATCH FOUND:\n")
                for product in rows:
                    print(f"    SKU       : {product['sku']}")
                    print(f"    Name      : {product['product_name']}")
                    print(f"    EAN Number: {product['EAN_number']}")
                    print("-" * 40)
                matched = True
            else:
                print(f"  ✘ No match found for EAN '{data}'")
        print(f"  DB Search Time: {time.time() - db_start:.4f} seconds")
        print(f"\n  Total Program Runtime: {time.time() - program_start:.4f} seconds")
        print("=" * 50)
        return rows[0] if matched else None

    # ── STEP 2: VARIANCE CHECK ───────────────────────
    print("\n✘ No barcode. Checking if face has content...")
    print("[STEP 2] Variance check...")
    start = time.time()
    blank = is_blank_face(image)
    end = time.time()
    print(f"  Variance Check Time: {end - start:.4f} seconds")

    if blank:
        print("✘ Plain face detected — skipping OCR.")
        print(f"\n  Total Program Runtime: {time.time() - program_start:.4f} seconds")
        print("=" * 50)
        return

    # ── STEP 3: EASYOCR ──────────────────────────────
    print("✔ Content detected — running EasyOCR...\n")
    print("[STEP 3] Running EasyOCR...")
    start = time.time()
    results = reader.readtext(
    image_path,
    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    )
    end = time.time()

    if not results:
        print("✘ No text detected by OCR.")
        print(f"\n  Total Program Runtime: {time.time() - program_start:.4f} seconds")
        print("=" * 50)
        return

    print("✔ OCR Results:")
    for bbox, text, confidence in results:
        print(f"  Text      : {text}")
        print(f"  Confidence: {confidence:.2%}")
        print("-" * 40)
    print(f"  OCR Time: {end - start:.4f} seconds")

    # ── STEP 4: DB LOOKUP ────────────────────────────
    print("\n[STEP 4] Routing detections to correct lookup...")
    all_matches = []
    sku_to_product = {}
    db_start = time.time()

    CONFIDENCE_THRESHOLD = 0.30

    for bbox, text, confidence in results:
        if confidence < CONFIDENCE_THRESHOLD:
            print(f"  Skipping '{text}' — low confidence ({confidence:.2%})")
            continue
        cleaned = text.strip()

        if is_number(cleaned):
            print(f"\n  '{cleaned}' is a NUMBER → searching by partial EAN")
            results_sql = lookup_by_EAN(cleaned)
        else:
            print(f"\n  '{cleaned}' is a STRING → searching by product name")
            results_sql = lookup_by_partial_name(cleaned)

        if results_sql:
            skus = set()
            for product in results_sql:
                s = product['sku']
                skus.add(s)
                sku_to_product[s] = product
                print(f"    SKU : {s}")
                print(f"    Name: {product['product_name']}")
                print("-" * 40)
            all_matches.append(skus)
        else:
            print(f"    No match found for '{cleaned}'")

    db_end = time.time()
    print(f"\n  Database Search Time: {db_end - db_start:.4f} seconds")

    # ── STEP 5: FINAL RESULT ─────────────────────────
    print("\n[STEP 5] Finding final result...")
    print("=" * 50)

    if not all_matches:
        print("✘ No matching products found in database.")
        print(f"\n  Total Program Runtime: {time.time() - program_start:.4f} seconds")
        print("=" * 50)
        return

    if len(all_matches) == 1:
        final_skus = all_matches[0]
    else:
        final_skus = all_matches[0]
        for s in all_matches[1:]:
            final_skus &= s
        if not final_skus:
            print("  ⚠ No exact common result — using most frequent match.\n")
            all_flat = [s for subset in all_matches for s in subset]
            final_skus = {Counter(all_flat).most_common(1)[0][0]}

    print("  ✔ FINAL RESULT:\n")
    for sku in final_skus:
        product = sku_to_product[sku]
        print(f"  SKU : {product['sku']}")
        print(f"  Name: {product['product_name']}")
        print("-" * 40)

    ocr_time = end - start
    db_time = db_end - db_start
    print(f"\n  OCR Time             : {ocr_time:.4f} seconds")
    print(f"  Database Search Time : {db_time:.4f} seconds")
    print(f"  OCR + Database Time  : {ocr_time + db_time:.4f} seconds")
    print(f"  Total Program Runtime: {time.time() - program_start:.4f} seconds")
    print("=" * 50)
    return sku_to_product[next(iter(final_skus))]
# ── RUN ──────────────────────────────────────────────
BROKER = "localhost"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe("scan/start", qos=1)
        print("[scan_node] Connected — waiting for images...\n")

def on_message(client, userdata, msg):
    print("\n[scan_node] Images ready — starting processing...\n")

    image_files = [f"omnidirectional picture/image_{i}.jpg" for i in range(1, 6)]

    for image_path in image_files:
        result = scan_and_lookup(image_path)
        print("\n")
        if result:
            print(f"✔ Match found in {image_path} — stopping early.")
            payload = json.dumps({
                "image": image_path,
                "sku": result['sku'] if isinstance(result, dict) else "matched",
                "product_name": result['product_name'] if isinstance(result, dict) else ""
            })
            mqtt_client.publish("scan/result", payload, qos=1)
            print(f"[scan_node] Result published to MQTT.")
            break

    print("[scan_node] Done. Waiting for next trigger...\n")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, keepalive=60)

print("[scan_node] Starting — connecting to broker...")
mqtt_client.loop_forever()