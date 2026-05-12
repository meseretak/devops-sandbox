"""
DevOps Sandbox Platform API
Flask API wrapping the shell scripts.
"""
import os, json, subprocess, glob, time
from flask import Flask, jsonify, request, abort, render_template_string

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


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevOps Sandbox Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg:      #0d1117;
      --surface: #161b22;
      --border:  #21262d;
      --green:   #3fb950;
      --red:     #f85149;
      --orange:  #e3b341;
      --blue:    #58a6ff;
      --grey:    #8b949e;
      --text:    #c9d1d9;
      --white:   #f0f6fc;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: var(--bg); color: var(--text); min-height: 100vh; }

    header {
      background: var(--surface); border-bottom: 1px solid var(--border);
      padding: 16px 28px; display: flex; align-items: center;
      justify-content: space-between; position: sticky; top: 0; z-index: 100;
    }
    header h1 { font-size: 1.1rem; font-weight: 600; color: var(--white);
                display: flex; align-items: center; gap: 10px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green);
           box-shadow: 0 0 8px var(--green); animation: pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    #updated { font-size: .78rem; color: var(--grey); }

    main { padding: 24px 28px; max-width: 1200px; margin: 0 auto; }

    /* ── Summary cards ── */
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
             gap: 14px; margin-bottom: 28px; }
    .card { background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; padding: 18px 20px; }
    .card .label { font-size: .72rem; text-transform: uppercase;
                   letter-spacing: .06em; color: var(--grey); margin-bottom: 8px; }
    .card .value { font-size: 1.9rem; font-weight: 700; color: var(--white); }
    .card .value.green  { color: var(--green); }
    .card .value.red    { color: var(--red); }
    .card .value.orange { color: var(--orange); }

    /* ── Create form ── */
    .create-bar {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 16px 20px; margin-bottom: 28px;
      display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap;
    }
    .create-bar label { font-size: .8rem; color: var(--grey);
                        display: flex; flex-direction: column; gap: 5px; }
    .create-bar input {
      background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
      color: var(--white); padding: 7px 12px; font-size: .9rem; width: 160px;
      outline: none;
    }
    .create-bar input:focus { border-color: var(--blue); }
    .btn {
      padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer;
      font-size: .85rem; font-weight: 600; transition: opacity .15s;
    }
    .btn:hover { opacity: .85; }
    .btn-green  { background: var(--green);  color: #000; }
    .btn-red    { background: var(--red);    color: #fff; }
    .btn-orange { background: var(--orange); color: #000; }
    .btn-blue   { background: var(--blue);   color: #000; }
    .btn-grey   { background: #30363d;       color: var(--white); }

    /* ── Env table ── */
    .panel { background: var(--surface); border: 1px solid var(--border);
             border-radius: 10px; overflow: hidden; margin-bottom: 28px; }
    .panel-header { padding: 14px 20px; border-bottom: 1px solid var(--border);
                    display: flex; align-items: center; justify-content: space-between; }
    .panel-header h2 { font-size: .95rem; font-weight: 600; color: var(--white); }
    table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    thead th { padding: 10px 16px; text-align: left; font-size: .72rem;
               text-transform: uppercase; letter-spacing: .06em; color: var(--grey);
               background: rgba(255,255,255,.02); border-bottom: 1px solid var(--border); }
    tbody tr { border-bottom: 1px solid var(--border); transition: background .15s; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: rgba(255,255,255,.03); }
    tbody td { padding: 10px 16px; vertical-align: middle; }
    .empty { text-align: center; color: var(--grey); padding: 32px; font-style: italic; }

    .badge { font-size: .72rem; padding: 3px 9px; border-radius: 20px; font-weight: 600; }
    .badge-green  { background: rgba(63,185,80,.15);  color: var(--green); }
    .badge-red    { background: rgba(248,81,73,.15);  color: var(--red); }
    .badge-orange { background: rgba(227,179,65,.15); color: var(--orange); }
    .badge-grey   { background: rgba(139,148,158,.15);color: var(--grey); }

    .mono { font-family: monospace; font-size: .82rem; }

    /* ── TTL bar ── */
    .ttl-wrap { display: flex; align-items: center; gap: 8px; }
    .ttl-bar-outer { width: 80px; height: 5px; background: var(--border);
                     border-radius: 3px; overflow: hidden; }
    .ttl-bar-inner { height: 100%; border-radius: 3px; transition: width .6s; }

    /* ── Log / health drawer ── */
    #drawer {
      position: fixed; right: 0; top: 0; bottom: 0; width: 520px;
      background: var(--surface); border-left: 1px solid var(--border);
      display: flex; flex-direction: column; transform: translateX(100%);
      transition: transform .25s ease; z-index: 200;
    }
    #drawer.open { transform: translateX(0); }
    #drawer-header { padding: 14px 18px; border-bottom: 1px solid var(--border);
                     display: flex; align-items: center; justify-content: space-between; }
    #drawer-title { font-size: .9rem; font-weight: 600; color: var(--white); }
    #drawer-close { background: none; border: none; color: var(--grey);
                    font-size: 1.3rem; cursor: pointer; line-height: 1; }
    #drawer-tabs { display: flex; border-bottom: 1px solid var(--border); }
    .tab { padding: 10px 18px; font-size: .82rem; cursor: pointer;
           color: var(--grey); border-bottom: 2px solid transparent; }
    .tab.active { color: var(--blue); border-bottom-color: var(--blue); }
    #drawer-body { flex: 1; overflow-y: auto; padding: 14px 18px; }
    .log-line { font-family: monospace; font-size: .78rem; color: var(--text);
                line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
    .log-line.err { color: var(--red); }
    .health-row { padding: 8px 0; border-bottom: 1px solid var(--border);
                  font-size: .82rem; }
    .health-row:last-child { border-bottom: none; }

    /* ── Outage modal ── */
    #modal-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,.6);
      display: none; align-items: center; justify-content: center; z-index: 300;
    }
    #modal-overlay.open { display: flex; }
    #modal { background: var(--surface); border: 1px solid var(--border);
             border-radius: 12px; padding: 24px; width: 360px; }
    #modal h3 { font-size: 1rem; color: var(--white); margin-bottom: 16px; }
    .mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
                 margin-bottom: 16px; }
    .mode-btn { padding: 10px; border-radius: 8px; border: 1px solid var(--border);
                background: var(--bg); color: var(--text); cursor: pointer;
                font-size: .85rem; text-align: center; transition: all .15s; }
    .mode-btn:hover { border-color: var(--orange); color: var(--orange); }
    .mode-btn.recover { border-color: var(--green); color: var(--green); }
    .mode-btn.recover:hover { background: rgba(63,185,80,.1); }
  </style>
</head>
<body>

<header>
  <h1><span class="dot"></span> DevOps Sandbox Dashboard</h1>
  <span id="updated">Connecting…</span>
</header>

<main>

  <!-- Summary cards -->
  <div class="cards">
    <div class="card">
      <div class="label">Total Environments</div>
      <div class="value" id="c-total">—</div>
    </div>
    <div class="card">
      <div class="label">Running</div>
      <div class="value green" id="c-running">—</div>
    </div>
    <div class="card">
      <div class="label">Degraded</div>
      <div class="value red" id="c-degraded">—</div>
    </div>
    <div class="card">
      <div class="label">API</div>
      <div class="value green">Online</div>
    </div>
  </div>

  <!-- Create form -->
  <div class="create-bar">
    <label>Environment Name
      <input id="new-name" type="text" placeholder="myapp" value="myapp">
    </label>
    <label>TTL (seconds)
      <input id="new-ttl" type="number" placeholder="300" value="300" min="30">
    </label>
    <button class="btn btn-green" onclick="createEnv()">＋ Create Environment</button>
    <span id="create-msg" style="font-size:.82rem;color:var(--grey);margin-left:8px"></span>
  </div>

  <!-- Environments table -->
  <div class="panel">
    <div class="panel-header">
      <h2>Active Environments</h2>
      <span style="font-size:.78rem;color:var(--grey)">Auto-refreshes every 5s</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Name</th>
          <th>Status</th>
          <th>URL</th>
          <th>TTL Remaining</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="env-tbody">
        <tr><td colspan="6" class="empty">Loading…</td></tr>
      </tbody>
    </table>
  </div>

</main>

<!-- Log / Health drawer -->
<div id="drawer">
  <div id="drawer-header">
    <span id="drawer-title">Logs</span>
    <button id="drawer-close" onclick="closeDrawer()">✕</button>
  </div>
  <div id="drawer-tabs">
    <div class="tab active" id="tab-logs"    onclick="switchTab('logs')">App Logs</div>
    <div class="tab"        id="tab-health"  onclick="switchTab('health')">Health Checks</div>
  </div>
  <div id="drawer-body">Loading…</div>
</div>

<!-- Outage modal -->
<div id="modal-overlay">
  <div id="modal">
    <h3 id="modal-title">Simulate Outage</h3>
    <div class="mode-grid">
      <div class="mode-btn" onclick="triggerOutage('crash')">💥 Crash<br><small>docker kill</small></div>
      <div class="mode-btn" onclick="triggerOutage('pause')">⏸ Pause<br><small>freeze processes</small></div>
      <div class="mode-btn" onclick="triggerOutage('network')">🔌 Network Cut<br><small>disconnect</small></div>
      <div class="mode-btn" onclick="triggerOutage('stress')">🔥 CPU Stress<br><small>30s spike</small></div>
      <div class="mode-btn recover" onclick="triggerOutage('recover')" style="grid-column:span 2">
        ✅ Recover — restore everything
      </div>
    </div>
    <button class="btn btn-grey" style="width:100%" onclick="closeModal()">Cancel</button>
  </div>
</div>

<script>
  let currentEnvId = null;
  let currentTab   = 'logs';

  // ── Fetch and render environments ──────────────────────────────────────────
  async function refresh() {
    try {
      const r    = await fetch('/envs');
      const envs = await r.json();

      const running  = envs.filter(e => e.status === 'running').length;
      const degraded = envs.filter(e => e.status === 'degraded').length;
      document.getElementById('c-total').textContent    = envs.length;
      document.getElementById('c-running').textContent  = running;
      document.getElementById('c-degraded').textContent = degraded;

      const tbody = document.getElementById('env-tbody');
      if (envs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No active environments — create one above</td></tr>';
      } else {
        tbody.innerHTML = envs.map(e => {
          const pct     = Math.round((e.ttl_remaining / e.ttl) * 100);
          const barColor = pct > 50 ? 'var(--green)' : pct > 20 ? 'var(--orange)' : 'var(--red)';
          const badge    = e.status === 'running'
            ? '<span class="badge badge-green">running</span>'
            : e.status === 'degraded'
            ? '<span class="badge badge-red">degraded</span>'
            : '<span class="badge badge-grey">' + e.status + '</span>';
          const url = '/env-' + e.id.replace('env-','') + '/';
          return `<tr>
            <td class="mono">${e.id}</td>
            <td>${e.name}</td>
            <td>${badge}</td>
            <td><a href="http://${location.hostname}/${e.id}/" target="_blank"
                   style="color:var(--blue);font-size:.8rem">Open ↗</a></td>
            <td>
              <div class="ttl-wrap">
                <span class="mono" style="min-width:42px">${e.ttl_remaining}s</span>
                <div class="ttl-bar-outer">
                  <div class="ttl-bar-inner" style="width:${pct}%;background:${barColor}"></div>
                </div>
              </div>
            </td>
            <td style="display:flex;gap:6px;flex-wrap:wrap">
              <button class="btn btn-blue"   style="font-size:.75rem;padding:5px 10px"
                      onclick="openDrawer('${e.id}')">Logs</button>
              <button class="btn btn-orange" style="font-size:.75rem;padding:5px 10px"
                      onclick="openModal('${e.id}')">Outage</button>
              <button class="btn btn-red"    style="font-size:.75rem;padding:5px 10px"
                      onclick="destroyEnv('${e.id}')">Destroy</button>
            </td>
          </tr>`;
        }).join('');
      }

      document.getElementById('updated').textContent =
        'Updated ' + new Date().toLocaleTimeString();
    } catch(e) {
      document.getElementById('updated').textContent = 'Connection error — retrying…';
    }
  }

  // ── Create environment ─────────────────────────────────────────────────────
  async function createEnv() {
    const name = document.getElementById('new-name').value.trim() || 'sandbox';
    const ttl  = parseInt(document.getElementById('new-ttl').value) || 300;
    const msg  = document.getElementById('create-msg');
    msg.textContent = 'Creating…';
    try {
      const r = await fetch('/envs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, ttl})
      });
      if (r.ok) {
        msg.style.color = 'var(--green)';
        msg.textContent = '✔ Created!';
        setTimeout(() => msg.textContent = '', 3000);
        refresh();
      } else {
        const d = await r.json();
        msg.style.color = 'var(--red)';
        msg.textContent = '✖ ' + (d.error || 'Failed');
      }
    } catch(e) {
      msg.style.color = 'var(--red)';
      msg.textContent = '✖ Network error';
    }
  }

  // ── Destroy environment ────────────────────────────────────────────────────
  async function destroyEnv(envId) {
    if (!confirm('Destroy ' + envId + '?')) return;
    await fetch('/envs/' + envId, {method: 'DELETE'});
    refresh();
  }

  // ── Log / health drawer ────────────────────────────────────────────────────
  async function openDrawer(envId) {
    currentEnvId = envId;
    document.getElementById('drawer-title').textContent = envId;
    document.getElementById('drawer').classList.add('open');
    await loadDrawerContent();
  }

  function closeDrawer() {
    document.getElementById('drawer').classList.remove('open');
    currentEnvId = null;
  }

  async function switchTab(tab) {
    currentTab = tab;
    document.getElementById('tab-logs').classList.toggle('active',   tab === 'logs');
    document.getElementById('tab-health').classList.toggle('active', tab === 'health');
    await loadDrawerContent();
  }

  async function loadDrawerContent() {
    if (!currentEnvId) return;
    const body = document.getElementById('drawer-body');
    body.innerHTML = 'Loading…';
    try {
      if (currentTab === 'logs') {
        const r = await fetch('/envs/' + currentEnvId + '/logs');
        const d = await r.json();
        if (!d.lines || d.lines.length === 0) {
          body.innerHTML = '<p style="color:var(--grey);font-style:italic">No logs yet</p>';
        } else {
          body.innerHTML = d.lines.map(l => {
            const cls = l.toLowerCase().includes('error') ? 'log-line err' : 'log-line';
            return '<div class="' + cls + '">' + escHtml(l) + '</div>';
          }).join('');
          body.scrollTop = body.scrollHeight;
        }
      } else {
        const r = await fetch('/envs/' + currentEnvId + '/health');
        const d = await r.json();
        const checks = d.checks || [];
        if (checks.length === 0) {
          body.innerHTML = '<p style="color:var(--grey);font-style:italic">No health data yet</p>';
        } else {
          body.innerHTML = [...checks].reverse().map(c => {
            const ok    = c.status === 200;
            const color = ok ? 'var(--green)' : 'var(--red)';
            const icon  = ok ? '✔' : '✖';
            return `<div class="health-row">
              <span style="color:${color};font-weight:700">${icon}</span>
              <span class="mono" style="margin-left:8px">HTTP ${c.status || 0}</span>
              <span style="color:var(--grey);margin-left:8px;font-size:.78rem">${c.latency}ms</span>
              <span style="color:var(--grey);margin-left:8px;font-size:.75rem">${c.ts || ''}</span>
              ${c.error ? '<div style="color:var(--red);font-size:.78rem;margin-top:3px">' + escHtml(c.error) + '</div>' : ''}
            </div>`;
          }).join('');
        }
      }
    } catch(e) {
      body.innerHTML = '<p style="color:var(--red)">Error loading data</p>';
    }
  }

  // ── Outage modal ───────────────────────────────────────────────────────────
  function openModal(envId) {
    currentEnvId = envId;
    document.getElementById('modal-title').textContent = 'Simulate Outage — ' + envId;
    document.getElementById('modal-overlay').classList.add('open');
  }

  function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
  }

  async function triggerOutage(mode) {
    closeModal();
    await fetch('/envs/' + currentEnvId + '/outage', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode})
    });
    setTimeout(refresh, 1000);
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // Close modal on overlay click
  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
  });

  setInterval(refresh, 5000);
  refresh();
</script>
</body>
</html>"""


# ── GET /dashboard — web UI ───────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


if __name__ == "__main__":
    port = int(os.getenv("PLATFORM_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
