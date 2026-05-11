#!/usr/bin/env python3
"""
health_poller.py — polls /health on every active environment every 30s.
Writes results to logs/<env_id>/health.log.
After 3 consecutive failures, marks env as degraded.
"""
import os, json, time, glob, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENVS_DIR  = os.path.join(ROOT, "envs")
LOGS_DIR  = os.path.join(ROOT, "logs")
INTERVAL  = 30
FAIL_THRESHOLD = 3

fail_counts = {}   # env_id -> consecutive failure count


def load_envs():
    envs = []
    for path in glob.glob(os.path.join(ENVS_DIR, "env-*.json")):
        try:
            with open(path) as f:
                envs.append(json.load(f))
        except Exception:
            pass
    return envs


def poll_env(env):
    env_id = env["id"]
    port   = env.get("port")
    url    = f"http://localhost:{port}/health"
    ts     = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    start  = time.time()
    status = 0
    error  = None

    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            status  = r.status
            latency = round((time.time() - start) * 1000, 1)
    except urllib.error.HTTPError as e:
        status  = e.code
        latency = round((time.time() - start) * 1000, 1)
    except Exception as e:
        latency = round((time.time() - start) * 1000, 1)
        error   = str(e)

    result = {
        "ts":      ts,
        "env_id":  env_id,
        "status":  status,
        "latency": latency,
    }
    if error:
        result["error"] = error

    # Write to health log
    log_dir = os.path.join(LOGS_DIR, env_id)
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "health.log"), "a") as f:
        f.write(json.dumps(result) + "\n")

    # Track failures
    ok = (status == 200)
    if ok:
        fail_counts[env_id] = 0
    else:
        fail_counts[env_id] = fail_counts.get(env_id, 0) + 1
        if fail_counts[env_id] >= FAIL_THRESHOLD:
            print(f"[{ts}] ⚠️  WARNING: {env_id} has failed {fail_counts[env_id]} consecutive health checks — marking DEGRADED")
            # Update state file
            state_path = os.path.join(ENVS_DIR, f"{env_id}.json")
            if os.path.exists(state_path):
                try:
                    with open(state_path) as f:
                        state = json.load(f)
                    state["status"] = "degraded"
                    import tempfile
                    tmp = tempfile.mktemp()
                    with open(tmp, "w") as f:
                        json.dump(state, f, indent=2)
                    os.replace(tmp, state_path)
                except Exception as e:
                    print(f"[{ts}] ERROR updating state: {e}")

    print(f"[{ts}] {env_id} → HTTP {status} ({latency}ms)" +
          (f" ERROR: {error}" if error else ""))
    return result


def main():
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Health poller started (interval={INTERVAL}s)")
    while True:
        envs = load_envs()
        if not envs:
            print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] No active environments")
        for env in envs:
            try:
                poll_env(env)
            except Exception as e:
                print(f"ERROR polling {env.get('id')}: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
