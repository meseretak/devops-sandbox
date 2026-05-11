"""
DevOps Sandbox Platform API
Flask API wrapping the shell scripts.
"""
import os, json, subprocess, glob
from flask import Flask, jsonify, request, abort

app = Flask(__name__)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM = os.path.join(ROOT, "platform")
ENVS_DIR = os.path.join(ROOT, "envs")
LOGS_DIR = os.path.join(ROOT, "logs")


def load_state(env_id):
    path = os.path.join(ENVS_DIR, f"{env_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def list_envs():
    states = []
    for path in glob.glob(os.path.join(ENVS_DIR, "env-*.json")):
        try:
            with open(path) as f:
                states.append(json.load(f))
        except Exception:
            pass
    return states


# ── POST /envs — create environment ──────────────────────────────────────────
@app.route("/envs", methods=["POST"])
def create_env():
    body = request.get_json(force=True) or {}
    name = body.get("name", "sandbox")
    ttl  = str(body.get("ttl", 1800))
    result = subprocess.run(
        ["bash", os.path.join(PLATFORM, "create_env.sh"), name, ttl],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return jsonify({"error": result.stderr}), 500
    # Parse env ID from output
    env_id = None
    for line in result.stdout.splitlines():
        if "ID:" in line:
            env_id = line.split("ID:")[-1].strip()
            break
    state = load_state(env_id) if env_id else {}
    return jsonify({"created": True, "env": state, "output": result.stdout}), 201


# ── GET /envs — list active environments ─────────────────────────────────────
@app.route("/envs", methods=["GET"])
def get_envs():
    import time
    envs = list_envs()
    now = int(time.time())
    for e in envs:
        e["ttl_remaining"] = max(0, e.get("expires_at", 0) - now)
    return jsonify(envs)


# ── DELETE /envs/:id — destroy environment ────────────────────────────────────
@app.route("/envs/<env_id>", methods=["DELETE"])
def destroy_env(env_id):
    if not load_state(env_id):
        abort(404, description=f"Environment {env_id} not found")
    result = subprocess.run(
        ["bash", os.path.join(PLATFORM, "destroy_env.sh"), env_id],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return jsonify({"error": result.stderr}), 500
    return jsonify({"destroyed": True, "id": env_id})


# ── GET /envs/:id/logs — last 100 lines of app.log ───────────────────────────
@app.route("/envs/<env_id>/logs", methods=["GET"])
def get_logs(env_id):
    log_path = os.path.join(LOGS_DIR, env_id, "app.log")
    archived = os.path.join(LOGS_DIR, "archived", env_id, "app.log")
    path = log_path if os.path.exists(log_path) else archived
    if not os.path.exists(path):
        return jsonify({"lines": [], "note": "No logs found"})
    with open(path) as f:
        lines = f.readlines()
    return jsonify({"env_id": env_id, "lines": [l.rstrip() for l in lines[-100:]]})


# ── GET /envs/:id/health — last 10 health check results ──────────────────────
@app.route("/envs/<env_id>/health", methods=["GET"])
def get_health(env_id):
    health_path = os.path.join(LOGS_DIR, env_id, "health.log")
    if not os.path.exists(health_path):
        return jsonify({"checks": [], "note": "No health data yet"})
    with open(health_path) as f:
        lines = f.readlines()
    checks = []
    for line in lines[-10:]:
        try:
            checks.append(json.loads(line))
        except Exception:
            checks.append({"raw": line.rstrip()})
    return jsonify({"env_id": env_id, "checks": checks})


# ── POST /envs/:id/outage — trigger simulation ────────────────────────────────
@app.route("/envs/<env_id>/outage", methods=["POST"])
def simulate_outage(env_id):
    if not load_state(env_id):
        abort(404, description=f"Environment {env_id} not found")
    body = request.get_json(force=True) or {}
    mode = body.get("mode", "crash")
    result = subprocess.run(
        ["bash", os.path.join(PLATFORM, "simulate_outage.sh"),
         "--env", env_id, "--mode", mode],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return jsonify({"error": result.stderr}), 500
    return jsonify({"simulated": True, "env_id": env_id, "mode": mode,
                    "output": result.stdout})


if __name__ == "__main__":
    port = int(os.getenv("PLATFORM_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
