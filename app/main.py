"""
Small demo service for the DevOps homework assignment.

Endpoints:
    GET    /health           -> liveness/readiness style health check
    GET    /version           -> static application version
    GET    /env                -> reflects the ENVIRONMENT env var
    POST   /config             -> store a key/value config entry (in-memory)
    GET    /config/<name>      -> read a stored config entry
    DELETE /config/<name>      -> delete a stored config entry

The config store is intentionally kept in memory (a plain dict) since the
assignment does not ask for persistence. See README "Known Limitations".
"""
import logging
import os
import threading

from flask import Flask, jsonify, request

APP_VERSION = "1.0.0"

app = Flask(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("myapp")

# In-memory config store. A lock is used because gunicorn can run multiple
# worker *threads* inside a single process (see Dockerfile CMD). Note this
# does NOT share state across multiple processes/pods - see README.
_config_lock = threading.Lock()
_config_store: dict[str, str] = {}


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/version")
def version():
    return jsonify({"version": APP_VERSION})


@app.get("/env")
def env():
    return jsonify({"environment": os.environ.get("ENVIRONMENT", "unknown")})


@app.post("/config")
def create_config():
    payload = request.get_json(silent=True)
    if not payload or "name" not in payload or "value" not in payload:
        return jsonify({"error": "request body must contain 'name' and 'value'"}), 400

    name = str(payload["name"])
    value = str(payload["value"])

    if not name:
        return jsonify({"error": "'name' must not be empty"}), 400

    with _config_lock:
        _config_store[name] = value

    return jsonify({"name": name, "value": value}), 201


@app.get("/config/<name>")
def get_config(name):
    with _config_lock:
        value = _config_store.get(name)

    if value is None:
        return jsonify({"error": f"config '{name}' not found"}), 404

    return jsonify({"name": name, "value": value})


@app.delete("/config/<name>")
def delete_config(name):
    with _config_lock:
        existed = _config_store.pop(name, None) is not None

    return jsonify({"deleted": existed})


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"error": "method not allowed"}), 405


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    # Dev server only - the container uses gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=port)
