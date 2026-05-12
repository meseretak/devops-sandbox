# DevOps Sandbox Platform

A self-service platform for spinning up isolated temporary environments, deploying apps, simulating outages, monitoring health, and auto-destroying everything.

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           Linux VM (single host)         │
                    │                                          │
  User/CI ──────►  │  ┌──────────┐    ┌─────────────────┐    │
                    │  │  Nginx   │    │  Platform API   │    │
                    │  │ :80      │    │  (Flask) :8080  │    │
                    │  └────┬─────┘    └────────┬────────┘    │
                    │       │                   │             │
                    │       │ proxy per env      │ wraps       │
                    │       ▼                   ▼             │
                    │  ┌─────────────────────────────────┐    │
                    │  │        sandbox-net (bridge)      │    │
                    │  │  ┌──────────┐  ┌──────────┐     │    │
                    │  │  │ app-env1 │  │ app-env2 │ ... │    │
                    │  │  │ :5000    │  │ :5000    │     │    │
                    │  │  └──────────┘  └──────────┘     │    │
                    │  └─────────────────────────────────┘    │
                    │                                          │
                    │  ┌──────────────┐  ┌────────────────┐   │
                    │  │ Cleanup      │  │ Health Poller  │   │
                    │  │ Daemon       │  │ (30s interval) │   │
                    │  │ (60s loop)   │  │                │   │
                    │  └──────────────┘  └────────────────┘   │
                    └─────────────────────────────────────────┘

State:  envs/<env-id>.json
Logs:   logs/<env-id>/app.log + health.log
Nginx:  nginx/conf.d/<env-id>.conf (auto-generated)
```

---

## Prerequisites

- Docker
- Python 3.10+
- bash
- make

---

## Quick Start (5 commands) doine

```bash
git clone https://github.com/meseretak/devops-sandbox.git
cd devops-sandbox
cp .env.example .env
make build
make up
```

Then create your first environment:
```bash
make create
# Enter name: myapp
# Enter TTL: 300
```

---

## Dashboard

A live web dashboard is available at:
```
http://<your-server-ip>/dashboard
```

Shows all active environments, status, TTL countdown, logs, health checks, and outage simulation — all in the browser.

---

## Full Demo Walkthrough

```bash
# 1. Start the platform
make up

# 2. Create an environment
make create
# → prints: URL: http://localhost/env-1234567-abcd/

# 3. Check health
make health

# 4. Simulate a crash
make simulate ENV=env-1234567-abcd MODE=crash

# 5. Watch health monitor detect the failure (within 90s)
tail -f logs/env-1234567-abcd/health.log

# 6. Recover
make simulate ENV=env-1234567-abcd MODE=recover

# 7. Tail logs
make logs ENV=env-1234567-abcd

# 8. Manually destroy
make destroy ENV=env-1234567-abcd

# 9. Or wait for TTL — cleanup daemon auto-destroys
tail -f logs/cleanup.log
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/envs` | Create environment `{"name":"x","ttl":300}` |
| GET | `/envs` | List all active environments + TTL remaining |
| DELETE | `/envs/:id` | Destroy environment |
| GET | `/envs/:id/logs` | Last 100 lines of app.log |
| GET | `/envs/:id/health` | Last 10 health check results |
| POST | `/envs/:id/outage` | Simulate outage `{"mode":"crash"}` |
| GET | `/dashboard` | Live web dashboard |

---

## Makefile Targets

```
make up                       # start Nginx + daemon + API
make down                     # stop everything, destroy all envs
make build                    # build app Docker image
make create                   # create new env (prompts for name + TTL)
make destroy ENV=env-abc123   # destroy specific env
make logs ENV=env-abc123      # tail env logs
make health                   # show all env health statuses
make simulate ENV=… MODE=…    # run outage simulation
make clean                    # wipe all state, logs, archives
```

---

## Outage Modes

| Mode | Effect | Recovery |
|---|---|---|
| `crash` | `docker kill` container | `--mode recover` |
| `pause` | `docker pause` container | `--mode recover` |
| `network` | Disconnect from network | `--mode recover` |
| `recover` | Restore all of the above | — |
| `stress` | CPU spike with stress-ng | Automatic after 30s |

---

## Known Limitations

- Single VM only — no multi-host support
- Port range 10000-19999 — max ~10000 concurrent environments
- Log shipping uses `docker logs -f` (Approach A) — not suitable for very high volume
- Nginx reload is synchronous — brief interruption possible during config changes
- `date -d` flag is Linux-specific — macOS requires `date -r`
