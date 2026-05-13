# ================================================================
#  cloud_server.py — Server Publik (Deploy ke Railway)
#  Politeknik Negeri Lhokseumawe
#  Fungsi: Terima log dari server lokal, sajikan dashboard publik
#  Deploy: railway.app (gratis)
#  
#  v2.0: Support photo_url dari ImgBB, gallery foto di dashboard
# ================================================================
import os
import json
import queue
import threading
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, render_template_string
from flask_cors import CORS
from datetime import datetime
from blockchain import Blockchain

load_dotenv()
app          = Flask(__name__)
CORS(app)
blockchain   = Blockchain()
event_queue  = queue.Queue(maxsize=500)
CLOUD_SECRET = os.getenv("CLOUD_SECRET", "ganti_dengan_token_rahasia_kamu")

# Log in-memory untuk SSE (bukan persisten, hanya untuk live feed)
log_cache = []
log_lock  = threading.Lock()


# ================================================================
# HELPER
# ================================================================
def kirim_event(tipe: str, data: dict):
    payload = json.dumps({
        "tipe"     : tipe,
        "data"     : data,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }, ensure_ascii=False)
    try:
        event_queue.put_nowait(payload)
    except queue.Full:
        pass


# ================================================================
# ENDPOINT: Terima log dari server lokal
# POST /api/log-masuk
# ================================================================
@app.route("/api/log-masuk", methods=["POST"])
def log_masuk():
    data  = request.get_json(force=True)
    if not data:
        return jsonify({"ok": False, "pesan": "Body kosong"}), 400

    token = data.pop("token", "")
    if token != CLOUD_SECRET:
        return jsonify({"ok": False, "pesan": "Unauthorized"}), 403

    # Pastikan ada field yang dibutuhkan
    now = datetime.now()
    data.setdefault("jam_akses",     now.strftime("%H:%M:%S"))
    data.setdefault("tanggal_akses", now.strftime("%Y-%m-%d"))
    data.setdefault("nama",          "Unknown")
    data.setdefault("status_akses",  "?")
    data.setdefault("photo_url",     "")

    # Simpan ke blockchain lokal cloud
    blok = blockchain.tambah_blok(data)
    stat = blockchain.get_statistik()

    # Cache untuk dashboard
    log_entry = {
        "nama"         : data.get("nama"),
        "jam_akses"    : data.get("jam_akses"),
        "tanggal_akses": data.get("tanggal_akses"),
        "status"       : data.get("status_akses"),
        "photo_url"    : data.get("photo_url", ""),
        "blok_index"   : blok["index"],
    }
    with log_lock:
        log_cache.insert(0, log_entry)
        if len(log_cache) > 200:
            log_cache.pop()

    # Broadcast ke semua SSE client
    kirim_event(f"akses_{data['status_akses'].lower()}", {
        **log_entry,
        "statistik": stat,
        "valid"    : blockchain.validasi_rantai(),
    })

    return jsonify({"ok": True, "blok": blok["index"], "photo_url": data.get("photo_url", "")})


# ================================================================
# SSE — Live monitoring
# GET /events
# ================================================================
@app.route("/events")
def events():
    def generate():
        # Kirim state awal
        with log_lock:
            recent = log_cache[:50]

        init = json.dumps({
            "tipe": "init",
            "data": {
                "rantai"   : blockchain.rantai[-50:],  # 50 blok terakhir
                "statistik": blockchain.get_statistik(),
                "valid"    : blockchain.validasi_rantai(),
                "recent"   : recent,
            },
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }, ensure_ascii=False)
        yield f"data: {init}\n\n"

        while True:
            try:
                payload = event_queue.get(timeout=25)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'tipe':'ping'})}\n\n"
            except GeneratorExit:
                break

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control"              : "no-cache",
        "X-Accel-Buffering"         : "no",
        "Connection"                 : "keep-alive",
        "Access-Control-Allow-Origin": "*",
    })


# ================================================================
# API
# ================================================================
@app.route("/api/blockchain")
def api_blockchain():
    return jsonify({
        "rantai"   : blockchain.rantai,
        "valid"    : blockchain.validasi_rantai(),
        "statistik": blockchain.get_statistik(),
    })

@app.route("/api/logs")
def api_logs():
    with log_lock:
        return jsonify({"logs": log_cache, "total": len(log_cache)})

@app.route("/ping")
def ping():
    return jsonify({
        "status"    : "ok",
        "waktu"     : datetime.now().isoformat(),
        "total_blok": len(blockchain.rantai),
        "server"    : "Loker PNL Cloud — Railway",
    })


# ================================================================
# DASHBOARD HTML — bisa diakses publik
# GET /
# ================================================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitoring Loker — PNL</title>
<style>
  :root {
    --bg: #0a0e1a; --card: #111827; --border: #1f2937;
    --green: #10b981; --red: #ef4444; --blue: #3b82f6;
    --yellow: #f59e0b; --text: #e5e7eb; --muted: #6b7280;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Courier New', monospace; }
  
  header {
    background: var(--card); border-bottom: 1px solid var(--border);
    padding: 16px 24px; display: flex; align-items: center; gap: 12px;
  }
  header h1 { font-size: 1rem; letter-spacing: 2px; color: var(--green); }
  header span { font-size: .75rem; color: var(--muted); }
  
  .live-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--green); animation: pulse 1.5s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  
  .grid { 
    display: grid; 
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); 
    gap: 12px; 
    padding: 20px 24px 0; 
  }
  
  .stat-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }
  .stat-card .label { font-size: .7rem; color: var(--muted); letter-spacing: 1px; }
  .stat-card .value { font-size: 1.8rem; font-weight: bold; margin-top: 4px; }
  .value.green { color: var(--green); }
  .value.red   { color: var(--red);   }
  .value.blue  { color: var(--blue);  }
  .value.yellow{ color: var(--yellow);}
  
  .container {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 20px;
    padding: 20px 24px;
  }
  
  .log-section h2 { 
    font-size: .8rem; 
    letter-spacing: 2px; 
    color: var(--muted); 
    margin-bottom: 12px; 
  }
  
  .log-list { 
    display: flex; 
    flex-direction: column; 
    gap: 6px; 
    max-height: 60vh; 
    overflow-y: auto; 
  }
  
  .log-item {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px 14px;
    display: grid; grid-template-columns: 1fr 1fr 1fr auto;
    gap: 8px; align-items: center; font-size: .8rem;
    animation: fadeIn .3s ease;
    cursor: pointer;
    transition: border-color .2s, background .2s;
  }
  .log-item:hover { border-color: var(--blue); background: rgba(59,130,246,.05); }
  
  @keyframes fadeIn { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:none} }
  
  .log-item.berhasil { border-left: 3px solid var(--green); }
  .log-item.gagal    { border-left: 3px solid var(--red);   }
  .log-item.daftar   { border-left: 3px solid var(--blue);  }
  .log-item.hapus    { border-left: 3px solid var(--yellow); }
  
  .nama { color: var(--text); font-weight: bold; }
  .waktu { color: var(--muted); font-size: .75rem; }
  .badge {
    padding: 2px 8px; border-radius: 4px; font-size: .7rem; font-weight: bold;
    text-align: center;
  }
  .badge.berhasil { background: rgba(16,185,129,.15); color: var(--green); }
  .badge.gagal    { background: rgba(239,68,68,.15);  color: var(--red);   }
  .badge.daftar   { background: rgba(59,130,246,.15); color: var(--blue);  }
  .badge.hapus    { background: rgba(245,158,11,.15); color: var(--yellow); }
  .blok { color: var(--muted); font-size: .7rem; }
  .empty { color: var(--muted); text-align: center; padding: 40px; font-size: .8rem; }
  
  .photo-gallery {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px;
    max-height: 60vh; overflow-y: auto;
  }
  
  .photo-item {
    margin-bottom: 10px; border-radius: 6px; overflow: hidden;
    border: 1px solid var(--border);
  }
  
  .photo-img {
    width: 100%; height: auto; display: block;
    background: var(--bg);
  }
  
  .photo-info {
    padding: 6px; background: rgba(0,0,0,.3); font-size: .7rem;
    color: var(--muted);
  }
  
  footer { 
    padding: 16px 24px; 
    font-size: .7rem; 
    color: var(--muted); 
    border-top: 1px solid var(--border); 
  }
  
  @media (max-width: 900px) {
    .container { grid-template-columns: 1fr; }
  }
  
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--card); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<header>
  <div class="live-dot"></div>
  <h1>MONITORING LOKER</h1>
  <span>Politeknik Negeri Lhokseumawe</span>
  <span style="margin-left:auto" id="waktu">--:--:--</span>
</header>

<div class="grid">
  <div class="stat-card"><div class="label">TOTAL BLOK</div><div class="value blue" id="s-blok">0</div></div>
  <div class="stat-card"><div class="label">AKSES BERHASIL</div><div class="value green" id="s-berhasil">0</div></div>
  <div class="stat-card"><div class="label">AKSES GAGAL</div><div class="value red" id="s-gagal">0</div></div>
  <div class="stat-card"><div class="label">PENDAFTARAN</div><div class="value yellow" id="s-daftar">0</div></div>
  <div class="stat-card"><div class="label">RANTAI VALID</div><div class="value green" id="s-valid">–</div></div>
</div>

<div class="container">
  <div class="log-section">
    <h2>LOG AKSES TERBARU</h2>
    <div class="log-list" id="log-list">
      <div class="empty">Menunggu data dari server lokal...</div>
    </div>
  </div>
  
  <div>
    <h2 style="font-size:.8rem;letter-spacing:2px;color:var(--muted);margin-bottom:12px">GALERI FOTO TERBARU</h2>
    <div class="photo-gallery" id="photo-gallery">
      <div class="empty" style="padding:20px;font-size:.75rem">Menunggu foto...</div>
    </div>
  </div>
</div>

<footer>
  Data diterima dari server lokal via HTTPS · Blockchain: SHA256 lokal + Polygon Amoy Testnet · Foto dari ImgBB
</footer>

<script>
const logList = document.getElementById('log-list');
const photoGallery = document.getElementById('photo-gallery');
let logItems  = [];
let photoItems = [];

function updateStats(stat) {
  document.getElementById('s-blok').textContent     = stat.total_blok     || 0;
  document.getElementById('s-berhasil').textContent = stat.total_berhasil || 0;
  document.getElementById('s-gagal').textContent    = stat.total_gagal    || 0;
  document.getElementById('s-daftar').textContent   = stat.total_daftar   || 0;
  document.getElementById('s-valid').textContent    = stat.rantai_valid ? '✓ YA' : '✗ TIDAK';
}

function addLog(d) {
  const status = (d.status || '').toLowerCase();
  const item   = {
    nama         : d.nama          || '-',
    jam_akses    : d.jam_akses     || '-',
    tanggal_akses: d.tanggal_akses || '-',
    status,
    photo_url    : d.photo_url     || '',
    blok_index   : d.blok_index    ?? '-',
  };
  logItems.unshift(item);
  if (logItems.length > 100) logItems.pop();
  renderLog();
  
  // Tambah ke galeri foto kalau ada
  if (item.photo_url) {
    addPhoto(item);
  }
}

function addPhoto(logItem) {
  photoItems.unshift({
    nama: logItem.nama,
    jam_akses: logItem.jam_akses,
    photo_url: logItem.photo_url,
    status: logItem.status
  });
  if (photoItems.length > 20) photoItems.pop();
  renderGallery();
}

function renderLog() {
  if (!logItems.length) {
    logList.innerHTML = '<div class="empty">Belum ada log.</div>';
    return;
  }
  logList.innerHTML = logItems.map(l => `
    <div class="log-item ${l.status}">
      <span class="nama">${l.nama}</span>
      <span class="waktu">${l.jam_akses}<br>${l.tanggal_akses}</span>
      <span class="blok">Blok #${l.blok_index}</span>
      <span class="badge ${l.status}">${l.status.toUpperCase()}</span>
    </div>
  `).join('');
}

function renderGallery() {
  if (!photoItems.length) {
    photoGallery.innerHTML = '<div class="empty" style="padding:20px;font-size:.75rem">Belum ada foto.</div>';
    return;
  }
  photoGallery.innerHTML = photoItems.map(p => `
    <div class="photo-item">
      <img class="photo-img" src="${p.photo_url}" alt="Foto ${p.nama}" 
        onerror="this.style.display='none'">
      <div class="photo-info">
        <div style="font-weight:bold">${p.nama}</div>
        <div>${p.jam_akses} · ${p.status.toUpperCase()}</div>
      </div>
    </div>
  `).join('');
}

// SSE
const es = new EventSource('/events');
es.onmessage = e => {
  try {
    const msg = JSON.parse(e.data);
    if (msg.tipe === 'ping') return;

    if (msg.tipe === 'init') {
      const d = msg.data;
      if (d.statistik) updateStats(d.statistik);
      if (d.recent) { 
        logItems = d.recent; 
        photoItems = d.recent.filter(x => x.photo_url);
        renderLog();
        renderGallery();
      }
      return;
    }

    if (msg.data) {
      addLog(msg.data);
      if (msg.data.statistik) updateStats(msg.data.statistik);
    }
  } catch (err) {
    console.error('[SSE Parse Error]', err);
  }
};
es.onerror = () => console.warn('[SSE] Reconnecting...');

// Jam
setInterval(() => {
  document.getElementById('waktu').textContent =
    new Date().toLocaleTimeString('id-ID');
}, 1000);
</script>
</body>
</html>"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# ================================================================
# MAIN
# ================================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"\n[CLOUD] Server publik jalan di port {port}")
    print(f"[CLOUD] Dashboard: http://0.0.0.0:{port}/")
    print(f"[CLOUD] SSE: /events")
    print(f"[CLOUD] API: /api/blockchain, /api/logs, /ping\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)