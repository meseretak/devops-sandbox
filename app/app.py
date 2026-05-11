"""
Simple demo app that runs inside each sandbox environment.
"""
import os, time, random
from flask import Flask, jsonify

app = Flask(__name__)
START = time.time()
ENV_ID = os.getenv("ENV_ID", "unknown")

@app.route("/")
def index():
    return jsonify({"env": ENV_ID, "status": "running",
                    "uptime": round(time.time() - START, 1)})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "env": ENV_ID,
                    "uptime": round(time.time() - START, 1)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
