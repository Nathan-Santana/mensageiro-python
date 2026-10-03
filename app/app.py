import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

NODE = os.getenv("NODE_NAME", "app1")
PEERS = [p.strip() for p in os.getenv("PEERS", "").split(",") if p.strip()]
DATA_DIR = os.getenv("DATA_DIR", "/data")
PEER_TIMEOUT = float(os.getenv("PEER_TIMEOUT", "2"))

MSG_FILE = os.path.join(DATA_DIR, f"messages_{NODE}.jsonl")
LOG_FILE = os.path.join(DATA_DIR, f"{NODE}.log")

os.makedirs(DATA_DIR, exist_ok=True)

log = logging.getLogger(NODE)
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(name)s] %(message)s")
for handler in (logging.FileHandler(LOG_FILE), logging.StreamHandler()):
    handler.setFormatter(_fmt)
    log.addHandler(handler)

app = Flask(__name__)
lock = threading.Lock()


def load_messages():
    if not os.path.exists(MSG_FILE):
        return []
    with open(MSG_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


seen_ids = {m["id"] for m in load_messages()}


def store(record):
    with lock:
        if record["id"] in seen_ids:
            return False
        with open(MSG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        seen_ids.add(record["id"])
        return True


def replicate(record):
    results = {}
    for peer in PEERS:
        try:
            r = requests.post(
                f"http://{peer}/send",
                json=record,
                headers={"X-Replicated": "true"},  # marca cópia
                timeout=PEER_TIMEOUT,
            )
            results[peer] = "ok" if r.ok else f"erro {r.status_code}"
        except requests.RequestException as exc:
            results[peer] = f"falhou ({type(exc).__name__})"
        log.info("replicação id=%s -> %s: %s", record["id"], peer, results[peer])
    return results


@app.post("/send")
def send():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="corpo deve ser um JSON"), 400

    is_copy = request.headers.get("X-Replicated") == "true"

    if is_copy:
        if not all(k in data for k in ("id", "message", "origin", "timestamp")):
            return jsonify(error="cópia replicada incompleta"), 400
        record = data
    else:
        text = data.get("message")
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="campo 'message' (texto) é obrigatório"), 400
        record = {
            "id": str(uuid.uuid4()),
            "message": text,
            "origin": NODE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    created = store(record)
    log.info("%s id=%s origem=%s msg=%r",
             "recebida (cópia)" if is_copy else "recebida (cliente)",
             record["id"], record["origin"], record["message"])

    if is_copy:
        return jsonify(status="replicated" if created else "duplicate", id=record["id"]), 201 if created else 200

    return jsonify(status="stored", id=record["id"], replicated_to=replicate(record)), 201


@app.get("/messages")
def messages():
    with lock:
        msgs = load_messages()
    return jsonify(node=NODE, count=len(msgs), messages=msgs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
