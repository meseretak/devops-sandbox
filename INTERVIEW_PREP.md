# DevOps Sandbox — Interview Prep
> Every command with explanation + every question an interviewer may ask with answers

---

## END-TO-END COMMANDS WITH EXPLANATION

---

### Step 1 — Enter the project
```bash
cd devops-sandbox
```
Move into the project directory. All commands must run from here because the Makefile uses relative paths for logs, envs, nginx/conf.d, and platform scripts.

---

### Step 2 — Build the app image
```bash
make build
```
Builds a Docker image called `sandbox-app:latest` from `app/Dockerfile`.
This image is the Flask app that runs inside every sandbox environment.
Uses Python 3.12 Alpine base — lightweight, under 100MB.
Gunicorn serves it with 2 worker processes on port 5000.
You only build once. Every environment reuses this same image.

---

### Step 3 — Start the platform
```bash
make up
```
Starts four background processes:
- **Nginx container** on port 80 — reverse proxy, routes `/env-<id>/` to the right container
- **Platform API** (Flask) on port 8080 — REST interface wrapping the shell scripts
- **Cleanup daemon** — bash loop, runs every 60s, destroys expired environments
- **Health poller** — Python loop, runs every 30s, polls `/health` on every active environment

Expected output:
```
✅ Platform is up!
   Nginx:  http://localhost:80
   API:    http://localhost:8080
```

---

### Step 4 — Verify Nginx is up
```bash
curl http://localhost/
```
Nginx default server returns a JSON message.
Confirms Nginx container started and port 80 is bound.

Expected:
```json
{"status":"DevOps Sandbox Platform","message":"Use /env-<id>/ to reach an environment"}
```

---

### Step 5 — Verify API is up
```bash
curl http://localhost:8080/envs
```
API returns empty list — no environments yet.
Confirms Flask API process started and port 8080 is bound.

Expected: `[]`

---

### Step 6 — Create an environment
```bash
make create
# name: myapp
# TTL:  300
```
Runs `platform/create_env.sh` which does 6 things:
1. Generates unique ID: `env-<timestamp>-<random-hex>`
2. Creates isolated Docker network: `net-env-<id>`
3. Starts app container on a random port (10000–19999)
4. Writes Nginx config to `nginx/conf.d/<env-id>.conf` and reloads Nginx
5. Starts `docker logs -f` piped to `logs/<env-id>/app.log`
6. Writes state JSON to `envs/<env-id>.json`

Expected:
```
✅ Environment ready!
   ID:      env-1747000000-a3f2c1b0
   URL:     http://localhost/env-1747000000-a3f2c1b0/
   Direct:  http://localhost:14523/
   TTL:     300s
```

---

### Step 7 — Save the env ID
```bash
ENV=env-1747000000-a3f2c1b0
```
Store the ID in a shell variable so you don't retype it every command.
Replace with your actual ID from step 6.

---

### Step 8 — Hit the app through Nginx
```bash
curl http://localhost/$ENV/
```
Request goes: `curl → Nginx (port 80) → container (port 5000)`.
Nginx rewrites the path and proxies using the upstream defined in `nginx/conf.d/<env-id>.conf`.
Confirms end-to-end routing is working.

Expected:
```json
{"env": "env-...", "status": "running", "uptime": 4.2}
```

---

### Step 9 — Hit the health endpoint
```bash
curl http://localhost/$ENV/health
```
Hits the `/health` route on the app.
This is the exact same endpoint the health poller calls every 30 seconds automatically.

Expected:
```json
{"status": "ok", "env": "env-...", "uptime": 12.1}
```

---

### Step 10 — List environments via API
```bash
curl http://localhost:8080/envs
```
API reads all `envs/env-*.json` state files, calculates `ttl_remaining` for each, and returns the list.
Shows status, port, name, created time, and seconds left before auto-destroy.

---

### Step 11 — Check health via make
```bash
make health
```
Reads state files and the last line of each health log.
Shows a human-readable summary: ID, name, status, TTL remaining, last HTTP status and latency.

---

### Step 12 — Watch health poller live
```bash
tail -f logs/$ENV/health.log
```
The health poller writes one JSON line every 30 seconds.
Open this in a second terminal and leave it running so you can watch failures appear in real time.

Expected every 30s:
```json
{"ts":"2026-05-11T10:00:00Z","env_id":"env-...","status":200,"latency":4.2}
```

---

### Step 13 — Simulate a crash
```bash
make simulate ENV=$ENV MODE=crash
```
Runs `docker kill` on the container — hard kill, no graceful shutdown.
Simulates what happens when an app crashes unexpectedly in production.

---

### Step 14 — Watch failure detection
```bash
tail -f logs/$ENV/health.log
```
After the crash, the next health check fails.
After 3 consecutive failures the health poller updates `envs/<env-id>.json` to `"status": "degraded"`.
This takes up to 90 seconds (3 × 30s).

Expected after crash:
```json
{"ts":"...","status":0,"latency":5001.0,"error":"timed out"}
```

---

### Step 15 — Confirm degraded status
```bash
curl http://localhost:8080/envs
```
The API reads the updated state file and returns `"status": "degraded"`.
Proves automatic failure detection is working without any manual intervention.

---

### Step 16 — Recover
```bash
make simulate ENV=$ENV MODE=recover
```
Runs `docker start` to restart the killed container.
Also handles `docker unpause` and `docker network connect` if those modes were used.
Updates state file back to `"status": "running"`.

---

### Step 17 — Confirm recovery
```bash
curl http://localhost/$ENV/health
```
App is back up. Returns `{"status": "ok", ...}`.
Health poller will also start recording 200s again in the health log.

---

### Step 18 — Get logs via API
```bash
curl http://localhost:8080/envs/$ENV/logs
```
Returns last 100 lines of `logs/<env-id>/app.log` as JSON.
This is how you check what the app was doing before or during a crash.

---

### Step 19 — Get health history via API
```bash
curl http://localhost:8080/envs/$ENV/health
```
Returns last 10 health check records from the health log.
Shows the full history of pass and fail checks with timestamps and latency.

---

### Step 20 — Trigger outage via API
```bash
curl -X POST http://localhost:8080/envs/$ENV/outage \
  -H "Content-Type: application/json" \
  -d '{"mode":"crash"}'
```
Same as `make simulate` but through the REST API.
The API calls `simulate_outage.sh` internally.
Useful for triggering outages from CI/CD pipelines or external tools.

---

### Step 21 — Recover again
```bash
make simulate ENV=$ENV MODE=recover
```

---

### Step 22 — Try other outage modes
```bash
# Freeze all processes in the container — it runs but cannot respond
make simulate ENV=$ENV MODE=pause

# Recover from pause
make simulate ENV=$ENV MODE=recover

# Disconnect the container from the network — unreachable but still running
make simulate ENV=$ENV MODE=network

# Recover from network cut
make simulate ENV=$ENV MODE=recover

# Spike CPU to 100% for 30 seconds using stress-ng
make simulate ENV=$ENV MODE=stress
# This one recovers automatically after 30s
```

---

### Step 23 — Watch auto-cleanup
```bash
tail -f logs/cleanup.log
```
When the 300s TTL from step 6 expires, the cleanup daemon detects it and calls `destroy_env.sh`.
No manual action needed. Logs are archived automatically.

Expected when TTL expires:
```
[2026-05-11T10:05:00Z] TTL expired for env-... — destroying
[2026-05-11T10:05:02Z] ✅ Environment env-... destroyed and logs archived
```

---

### Step 24 — Manually destroy
```bash
make destroy ENV=$ENV
```
Runs `platform/destroy_env.sh` which:
1. Kills the log-shipping process
2. Stops and removes the Docker container
3. Removes the Docker network
4. Deletes the Nginx config and reloads Nginx
5. Archives logs to `logs/archived/<env-id>/`
6. Deletes the state file from `envs/`

---

### Step 25 — Confirm gone
```bash
curl http://localhost:8080/envs
```
Returns `[]` — environment is fully removed.

---

### Step 26 — Stop the platform
```bash
make down
```
Stops Nginx container, kills API process, kills cleanup daemon, kills health poller.
Destroys any remaining environments first.

---

### Step 27 — Wipe everything
```bash
make clean
```
Deletes all files in `logs/` and `envs/`.
Resets to a completely clean state.

---

---

## INTERVIEW QUESTIONS AND ANSWERS

---

### ARCHITECTURE

**Q: Walk me through the architecture of this project.**

The platform runs on a single Linux VM. There are four main components:
- The **app** — a Flask container that runs inside each sandbox environment
- The **Platform API** — a Flask app on port 8080 that wraps shell scripts and exposes a REST interface
- **Nginx** — a reverse proxy on port 80 that routes traffic to each environment using dynamically generated config files
- Two background daemons — a **health poller** that checks every environment every 30 seconds, and a **cleanup daemon** that destroys expired environments every 60 seconds

State is stored as JSON files in `envs/`. Logs go to `logs/`. Nginx configs are generated per environment in `nginx/conf.d/`.

---

**Q: Why did you use shell scripts instead of Python for create and destroy?**

Shell scripts are the natural language for Docker and system operations. `docker run`, `docker kill`, `docker network create`, `nginx -s reload` — these are all shell commands. Wrapping them in Python would add complexity without benefit. The API layer in Python calls the shell scripts via `subprocess`, which gives a clean separation: Python handles HTTP and JSON, Bash handles Docker and system operations.

---

**Q: Why store state in JSON files instead of a database?**

For a single-VM platform, JSON files are simpler, faster to implement, and have zero dependencies. Each environment gets one file. The cleanup daemon and health poller can read them with a single `glob` call. If this needed to scale to multiple hosts, a database would be the right choice — but for this scope, files are sufficient and easier to inspect and debug.

---

**Q: How does Nginx routing work per environment?**

When an environment is created, `create_env.sh` writes a config file to `nginx/conf.d/<env-id>.conf`. That file defines an upstream pointing to the container by name on the Docker network, and a server block that matches the URL path `/env-<id>/`. Nginx is then reloaded with `nginx -s reload` so the new route is live immediately. When the environment is destroyed, the config file is deleted and Nginx is reloaded again.

---

**Q: How does the health poller work?**

It runs in an infinite loop with a 30-second sleep. On each iteration it reads all `envs/env-*.json` state files to get the list of active environments and their ports. For each environment it makes an HTTP GET to `http://localhost:<port>/health` with a 5-second timeout. It writes the result — timestamp, HTTP status, latency, and any error — as a JSON line to `logs/<env-id>/health.log`. It tracks consecutive failures per environment. After 3 failures it updates the state file to `"status": "degraded"`.

---

**Q: What happens when an environment's TTL expires?**

The cleanup daemon runs every 60 seconds. It reads all state files and compares `expires_at` (a Unix timestamp) against the current time. If `now > expires_at`, it calls `destroy_env.sh` for that environment. The destroy script stops the container, removes the network, deletes the Nginx config, archives the logs, and deletes the state file. The whole process is automatic — no human action needed.

---

### DOCKER

**Q: Why does each environment get its own Docker network?**

Isolation. Each environment gets a `net-env-<id>` network in addition to the shared `sandbox-net`. This means containers cannot talk to each other by accident. The shared `sandbox-net` is only used so Nginx can reach the containers by name. The per-environment network is used for the outage simulation — the `network` mode disconnects the container from `sandbox-net`, making it unreachable through Nginx while the container itself keeps running.

---

**Q: How do you prevent port conflicts between environments?**

Each environment gets a random host port between 10000 and 19999 assigned at creation time using Python's `random.randint`. The port is stored in the state file. The probability of collision is low for the expected number of concurrent environments, and the `docker run` command will fail if the port is already taken, which would surface as an error.

---

**Q: Why use `docker logs -f` for log shipping instead of a log driver?**

Simplicity. `docker logs -f` pipes the container's stdout/stderr to a file with no extra configuration. A proper log driver like Fluentd or Loki would require additional infrastructure. For this platform the goal was zero external dependencies — just Docker, Python, and Bash. The log PID is saved so it can be killed cleanly when the environment is destroyed.

---

### NGINX

**Q: How does Nginx reload without downtime?**

`nginx -s reload` sends a SIGHUP to the Nginx master process. The master reads the new config and starts new worker processes with the updated config. Old workers finish their current requests and then exit. There is no hard restart — existing connections are not dropped. The brief window where a new config file exists but Nginx has not reloaded yet is acceptable for this use case.

---

**Q: What happens to Nginx if a container crashes?**

Nginx keeps the upstream config but the container is gone. Requests to that environment will get a 502 Bad Gateway from Nginx. The health poller detects this within 30 seconds and marks the environment as degraded. The Nginx config is only removed when the environment is explicitly destroyed.

---

### FLASK API

**Q: What endpoints does the API expose?**

Six endpoints:
- `POST /envs` — create environment, calls `create_env.sh`
- `GET /envs` — list all environments with TTL remaining
- `DELETE /envs/<id>` — destroy environment, calls `destroy_env.sh`
- `GET /envs/<id>/logs` — last 100 lines of app.log
- `GET /envs/<id>/health` — last 10 health check results
- `POST /envs/<id>/outage` — simulate outage, calls `simulate_outage.sh`

---

**Q: How does the API call the shell scripts?**

Using Python's `subprocess.run` with `capture_output=True`. The script path is constructed from the absolute path of the project root so it works regardless of the working directory. The return code is checked — non-zero means failure and the API returns a 500 with the stderr output.

---

### OUTAGE SIMULATION

**Q: What outage modes did you implement and why?**

Five modes:
- **crash** — `docker kill`, simulates a hard crash or OOM kill
- **pause** — `docker pause`, simulates a frozen/hung process that is still alive but not responding
- **network** — `docker network disconnect`, simulates a network partition where the app is running but unreachable
- **stress** — `stress-ng --cpu 2 --timeout 30s`, simulates high CPU load causing slow responses
- **recover** — handles all three recovery actions: unpause, reconnect network, restart container

These cover the most common real-world failure scenarios that a DevOps engineer would need to test.

---

**Q: How does the health poller distinguish between a crash and a network cut?**

It cannot distinguish — both result in a failed HTTP request. From the poller's perspective, both show up as `status: 0` with a timeout error. The distinction matters for recovery — `recover` mode tries all three recovery actions (unpause, reconnect, restart) so it handles any of the three failure modes.

---

### GENERAL DEVOPS

**Q: How would you scale this to multiple hosts?**

Several changes would be needed:
- Replace JSON state files with a shared database (Redis or PostgreSQL)
- Replace the single Nginx with a load balancer or use a service mesh
- Use Docker Swarm or Kubernetes for container orchestration across hosts
- Replace `docker logs -f` with a proper log aggregator like Loki or Elasticsearch
- The health poller and cleanup daemon would need to be distributed or run as a single leader

---

**Q: What would you add if you had more time?**

- Authentication on the API — right now anyone can create or destroy environments
- Resource limits on containers — CPU and memory caps to prevent one environment from starving others
- Metrics endpoint — expose Prometheus metrics for environment count, health status, TTL distribution
- Web UI — a simple dashboard showing all environments, their status, and logs
- Multi-host support using Docker Swarm
- Webhook notifications when an environment goes degraded or is auto-destroyed

---

**Q: What is the biggest limitation of this design?**

Single point of failure. Everything runs on one VM. If the VM goes down, all environments go down with it. The Nginx reload is also synchronous — there is a brief moment during config changes where a request could fail. And `date -d` is Linux-specific, so the scripts would not work on macOS without modification.

---

**Q: How do you make the state file writes safe?**

Atomic writes. The state file is written to a temp file first using `mktemp`, then moved into place with `mv` (which is atomic on Linux for files on the same filesystem). This prevents a partial write from corrupting the state file if the process is killed mid-write.

---

**Q: Why did you use Flask for the API instead of FastAPI or another framework?**

Flask was already a dependency for the app container, so it was already available. For a simple REST API with six endpoints and no async requirements, Flask is sufficient. FastAPI would add value if the API needed async operations, request validation with Pydantic, or auto-generated OpenAPI docs — none of which were required here.

---

**Q: How does the cleanup daemon avoid destroying an environment that is being used?**

It only checks `expires_at` from the state file. If the TTL has not expired, the environment is left alone. There is no locking mechanism — if a user extends the TTL by updating the state file, the daemon will respect the new expiry time on its next iteration. A more robust solution would use a distributed lock, but for a single-VM platform this is not needed.
