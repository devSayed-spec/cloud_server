# ================================================================
#  cloud_server.py — Server Publik (Deploy ke Railway)
#  Politeknik Negeri Lhokseumawe
#  Fungsi: Terima log dari server lokal, sajikan dashboard publik
#  Deploy: railway.app (gratis)
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

    # Simpan ke blockchain lokal cloud
    blok = blockchain.tambah_blok(data)
    stat = blockchain.get_statistik()

    # Cache untuk dashboard
    log_entry = {
        "nama"         : data.get("nama"),
        "jam_akses"    : data.get("jam_akses"),
        "tanggal_akses": data.get("tanggal_akses"),
        "status"       : data.get("status_akses"),
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

    return jsonify({"ok": True, "blok": blok["index"]})


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
<title>Loker Security — Politeknik Negeri Lhokseumawe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&family=Playfair+Display:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#f5f5f7; --surface:#fff; --surface-2:#fafafa;
  --border:rgba(0,0,0,.08); --border-2:rgba(0,0,0,.13);
  --text:#1d1d1f; --text-2:#6e6e73; --text-3:#aeaeb2;
  --ok:#30d158; --er:#ff3b30; --info:#0071e3; --warn:#ff9f0a; --chain:#bf5af2;
  --ok-bg:rgba(48,209,88,.1); --er-bg:rgba(255,59,48,.1);
  --info-bg:rgba(0,113,227,.1); --chain-bg:rgba(191,90,242,.1);
  --fd:'Playfair Display',Georgia,serif;
  --fb:'DM Sans',-apple-system,sans-serif;
  --fm:'DM Mono','SF Mono',monospace;
  --r1:8px; --r2:14px; --r3:20px; --r4:28px;
  --s1:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --s2:0 4px 16px rgba(0,0,0,.07),0 1px 4px rgba(0,0,0,.04);
  --s3:0 12px 40px rgba(0,0,0,.10),0 4px 12px rgba(0,0,0,.05);
  --ease:cubic-bezier(.4,0,.2,1);
  --spring:cubic-bezier(.34,1.56,.64,1);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:var(--fb);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;display:flex;flex-direction:column}

.hdr{display:flex;align-items:center;justify-content:space-between;padding:0 24px;height:58px;background:rgba(255,255,255,.85);backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--border);flex-shrink:0;position:sticky;top:0;z-index:100}
.hdr-brand{display:flex;align-items:center;gap:11px}
.brand-mark{width:32px;height:32px;border-radius:9px;background:var(--text);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:15px;color:#fff}
.brand-name{font-family:var(--fd);font-size:14px;font-weight:600;letter-spacing:-.2px}
.brand-sub{font-size:10px;color:var(--text-3)}
.hdr-nav{display:flex;align-items:center;gap:2px;background:rgba(0,0,0,.05);border-radius:11px;padding:3px}
.nav-btn{background:none;border:none;padding:6px 15px;border-radius:8px;font-family:var(--fb);font-size:13px;font-weight:500;color:var(--text-2);cursor:pointer;transition:all .2s var(--ease);text-decoration:none;display:inline-block;line-height:1.4}
.nav-btn:hover{color:var(--text)}
.nav-btn.active{background:var(--surface);color:var(--text);box-shadow:var(--s1)}
.hdr-status{display:flex;align-items:center;gap:9px}
.chip{display:flex;align-items:center;gap:6px;padding:4px 11px;background:var(--surface);border:1px solid var(--border);border-radius:20px;font-size:11px;color:var(--text-2);font-family:var(--fm)}
.sdot{width:6px;height:6px;border-radius:50%;background:var(--warn);animation:blink 1.4s infinite;flex-shrink:0}
.sdot.on{background:var(--ok);animation:none}
.sdot.off{background:var(--er);animation:none}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
.clock{font-family:var(--fm);font-size:13px;font-weight:500;letter-spacing:1px}

.metrics{display:flex;align-items:center;justify-content:center;height:54px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0;padding:0 20px}
.metric{display:flex;flex-direction:column;align-items:center;gap:2px;padding:0 28px}
.mval{font-family:var(--fd);font-size:19px;font-weight:600;line-height:1}
.mval.ok{color:var(--ok)}.mval.er{color:var(--er)}.mval.info{color:var(--info)}.mval.chain{color:var(--chain)}
.mlbl{font-size:10px;color:var(--text-3);letter-spacing:.4px;white-space:nowrap}
.mdiv{width:1px;height:26px;background:var(--border);flex-shrink:0}

.tab{display:none;flex:1;min-height:0;overflow:hidden;flex-direction:column}
.tab.active{display:flex}
#t-daftar.active{overflow-y:auto}

.grid{display:grid;grid-template-columns:1fr 310px;gap:14px;padding:18px 24px;flex:1;min-height:0;overflow:hidden;width:100%}

.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r3);overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--s1);transition:box-shadow .25s var(--ease)}
.card:hover{box-shadow:var(--s2)}
.card-hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--border);flex-shrink:0}
.card-ttl{font-size:13px;font-weight:600;display:flex;align-items:center;gap:7px}
.card-body{flex:1;overflow-y:auto}
.card-body::-webkit-scrollbar{width:3px}
.card-body::-webkit-scrollbar-thumb{background:var(--border-2);border-radius:2px}

.pdot{width:7px;height:7px;border-radius:50%;background:var(--ok);position:relative;flex-shrink:0}
.pdot::after{content:'';position:absolute;inset:-3px;border-radius:50%;background:var(--ok);opacity:.3;animation:pulse 2s ease-out infinite}
@keyframes pulse{0%{transform:scale(1);opacity:.3}100%{transform:scale(2.5);opacity:0}}
.pdot.off{background:var(--er)}.pdot.off::after{background:var(--er)}

.badge{background:var(--info);color:#fff;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;font-family:var(--fm)}
.fcnt{font-size:11px;color:var(--text-3);font-family:var(--fm)}

.feed-body{padding:10px;display:flex;flex-direction:column;gap:5px}
.fi{padding:11px 13px;border-radius:var(--r2);background:var(--surface-2);border:1px solid var(--border);border-left:3px solid var(--border);animation:si .2s var(--spring)}
@keyframes si{from{opacity:0;transform:translateY(-6px) scale(.98)}to{opacity:1;transform:none}}
.fi.ok{border-left-color:var(--ok)}.fi.er{border-left-color:var(--er)}.fi.inf{border-left-color:var(--info)}.fi.wn{border-left-color:var(--warn)}
.fi-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.fi-st{font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase}
.fi-st.ok{color:var(--ok)}.fi-st.er{color:var(--er)}.fi-st.inf{color:var(--info)}.fi-st.wn{color:var(--warn)}
.fi-tm{font-size:10px;color:var(--text-3);font-family:var(--fm)}
.fi-nm{font-size:13px;font-weight:600}
.fi-dt{font-size:11px;color:var(--text-2);margin-top:1px}

.rcol{display:flex;flex-direction:column;gap:14px;overflow:hidden}
.ucard{flex:1;min-height:0}.bcard{flex:1;min-height:0}

.ubody{padding:9px;display:flex;flex-direction:column;gap:4px}
.ui{display:flex;align-items:center;gap:9px;padding:9px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r2);transition:border-color .2s}
.ui:hover{border-color:var(--border-2)}
.uav{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,var(--info),var(--chain));display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0}
.uinfo{flex:1;min-width:0}
.unm{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.umt{font-size:10px;color:var(--text-3);margin-top:1px}
.ulok{font-size:10px;font-weight:600;color:var(--info);background:var(--info-bg);padding:2px 7px;border-radius:5px;white-space:nowrap;font-family:var(--fm)}
.udel{background:none;border:1px solid var(--border);color:var(--text-3);border-radius:6px;width:24px;height:24px;cursor:pointer;font-size:11px;transition:all .2s;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.udel:hover{color:var(--er);border-color:var(--er);background:var(--er-bg)}

.cbody{padding:9px;display:flex;flex-direction:column;gap:4px}
.cval{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-2)}
.cdot{width:6px;height:6px;border-radius:50%;background:var(--text-3)}
.cdot.v{background:var(--ok)}.cdot.nv{background:var(--er)}
.bi{padding:9px 11px;background:var(--surface-2);border:1px solid var(--border);border-left:3px solid var(--border);border-radius:var(--r2);cursor:pointer;transition:all .2s}
.bi:hover{border-color:var(--chain);background:var(--chain-bg);transform:translateX(2px)}
.bi.BERHASIL{border-left-color:var(--ok)}.bi.DAFTAR{border-left-color:var(--info)}.bi.GAGAL{border-left-color:var(--er)}.bi.HAPUS{border-left-color:var(--warn)}.bi.GENESIS{border-left-color:var(--chain)}
.bi-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}
.bi-idx{font-size:10px;color:var(--chain);font-family:var(--fm)}
.bi-st{font-size:10px;font-weight:700}
.bi-st.BERHASIL{color:var(--ok)}.bi-st.DAFTAR{color:var(--info)}.bi-st.GAGAL{color:var(--er)}.bi-st.HAPUS{color:var(--warn)}.bi-st.GENESIS{color:var(--chain)}
.bi-nm{font-size:12px;font-weight:600}
.bi-mt{font-size:10px;color:var(--text-2);margin-top:1px}
.bi-hsh{font-size:9px;color:var(--text-3);font-family:var(--fm);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

.btn-reset-chain{background:none;border:1px solid var(--er);color:var(--er);border-radius:6px;padding:2px 9px;font-size:11px;font-weight:600;cursor:pointer;transition:all .2s;font-family:var(--fb)}
.btn-reset-chain:hover{background:var(--er-bg)}

.reg{display:grid;grid-template-columns:1fr 400px;gap:22px;padding:26px 24px;width:100%;align-items:start}
.sec-hdr{margin-bottom:24px}
.sec-ttl{font-family:var(--fd);font-size:22px;font-weight:600;letter-spacing:-.4px;margin-bottom:7px}
.sec-desc{font-size:13px;color:var(--text-2);line-height:1.6}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
.fg{display:flex;flex-direction:column;gap:5px}
.fg.full{grid-column:1/-1}
.flbl{font-size:11px;font-weight:600;color:var(--text-2)}
.finp,.fsel{background:var(--surface);border:1px solid var(--border-2);border-radius:var(--r1);padding:9px 13px;font-family:var(--fb);font-size:13px;color:var(--text);outline:none;transition:border-color .2s,box-shadow .2s;width:100%}
.finp:focus,.fsel:focus{border-color:var(--info);box-shadow:0 0 0 3px rgba(0,113,227,.12)}
.finp::placeholder{color:var(--text-3)}
.fsel{cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23aeaeb2' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 11px center;padding-right:30px}
.btn-pri{display:flex;align-items:center;justify-content:center;gap:7px;background:var(--text);color:#fff;border:none;border-radius:var(--r2);padding:12px 22px;font-family:var(--fb);font-size:14px;font-weight:600;cursor:pointer;width:100%;transition:all .2s var(--ease)}
.btn-pri:hover{background:#333;transform:translateY(-1px);box-shadow:var(--s2)}
.btn-pri:active{transform:none}
.btn-pri:disabled{opacity:.4;cursor:not-allowed;transform:none}

.prog-wrap{margin-top:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r2);padding:14px;display:none}
.prog-wrap.show{display:block}
.prog-top{display:flex;justify-content:space-between;font-size:12px;color:var(--text-2);margin-bottom:7px;font-weight:500}
#progPct{font-family:var(--fm);color:var(--info)}
.prog-track{height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:10px}
.prog-bar{height:100%;background:var(--info);border-radius:2px;width:0%;transition:width .4s var(--ease)}
.prog-log{display:flex;flex-direction:column;gap:3px;max-height:90px;overflow-y:auto}
.ll{display:flex;gap:7px;font-size:11px;font-family:var(--fm)}
.ll-ico.ok{color:var(--ok)}.ll-ico.er{color:var(--er)}.ll-ico.inf{color:var(--text-3)}
.ll-txt{color:var(--text-2)}

.cam-sec{display:flex;flex-direction:column;gap:10px}
.cam-wrap{aspect-ratio:4/3;background:#1d1d1f;border-radius:var(--r4);overflow:hidden;position:relative;box-shadow:var(--s3)}
#camPrev{
  width:100%;height:100%;object-fit:contain;display:block;
  transform:translateZ(0);
  will-change:contents;
  opacity:.35;
  transition:opacity .3s;
}
#camPrev.on{opacity:1}
.cam-ovl{position:absolute;inset:0;pointer-events:none}
.cc{position:absolute;width:18px;height:18px;border-color:rgba(255,255,255,.25);border-style:solid}
.cc.tl{top:13px;left:13px;border-width:2px 0 0 2px;border-radius:2px 0 0 0}
.cc.tr{top:13px;right:13px;border-width:2px 2px 0 0;border-radius:0 2px 0 0}
.cc.bl{bottom:13px;left:13px;border-width:0 0 2px 2px;border-radius:0 0 0 2px}
.cc.br{bottom:13px;right:13px;border-width:0 2px 2px 0;border-radius:0 0 2px 0}
.cam-badge{position:absolute;bottom:13px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.6);backdrop-filter:blur(8px);color:#fff;font-size:11px;font-weight:500;padding:4px 12px;border-radius:20px;display:flex;align-items:center;gap:6px;white-space:nowrap}
.cdotl{width:6px;height:6px;border-radius:50%;background:var(--warn);animation:blink 1.2s infinite}
.cdotl.live{background:var(--ok);animation:none}
.cdotl.rec{background:var(--info);animation:blink .8s infinite}
.cam-cap{font-size:11px;color:var(--text-3);text-align:center}

.mode-banner{display:none;background:rgba(0,113,227,.12);border:1px solid rgba(0,113,227,.25);border-radius:var(--r1);padding:8px 13px;font-size:12px;color:var(--info);font-weight:500;margin-top:10px;align-items:center;gap:7px}
.mode-banner.show{display:flex}

.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:36px 16px;gap:7px;text-align:center;color:var(--text-3);height:100%}
.empty-ico{font-size:26px;margin-bottom:3px}
.empty p{font-size:13px;font-weight:500}
.empty small{font-size:11px}
.empty.sm{padding:18px;font-size:12px}

.mbd{position:fixed;inset:0;background:rgba(0,0,0,.35);backdrop-filter:blur(8px);z-index:999;display:none;align-items:center;justify-content:center}
.mbd.open{display:flex}
.modal{background:var(--surface);border-radius:var(--r4);box-shadow:var(--s3),0 0 0 1px var(--border);width:100%;max-width:460px;margin:20px;animation:mi .3s var(--spring)}
@keyframes mi{from{opacity:0;transform:scale(.94) translateY(10px)}to{opacity:1;transform:none}}
.m-hdr{display:flex;align-items:center;justify-content:space-between;padding:18px 22px 14px;border-bottom:1px solid var(--border)}
.m-ttl{font-family:var(--fd);font-size:16px;font-weight:600}
.m-cl{background:rgba(0,0,0,.07);border:none;color:var(--text-2);width:26px;height:26px;border-radius:50%;cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;transition:background .2s}
.m-cl:hover{background:rgba(0,0,0,.12)}
.m-body{padding:18px 22px}
.mr{display:flex;justify-content:space-between;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--border);gap:14px}
.mr:last-child{border:none}
.mk{font-size:12px;color:var(--text-3);flex-shrink:0}
.mv{font-size:12px;color:var(--text);font-weight:600;text-align:right;word-break:break-all;font-family:var(--fm)}

.del-modal{padding:28px 26px;text-align:center;max-width:360px}
.del-ico{font-size:32px;margin-bottom:10px}
.del-ttl{font-family:var(--fd);font-size:18px;font-weight:600;color:var(--er);margin-bottom:8px}
.del-desc{font-size:13px;color:var(--text-2);line-height:1.5}
.del-nm{font-size:14px;font-weight:700;color:var(--text);margin:5px 0}
.del-btns{display:flex;gap:9px;margin-top:20px}
.btn-ghost{flex:1;background:var(--surface-2);border:1px solid var(--border-2);color:var(--text);border-radius:var(--r2);padding:10px;font-family:var(--fb);font-size:13px;font-weight:500;cursor:pointer;transition:all .2s}
.btn-ghost:hover{background:var(--border)}
.btn-er{flex:1;background:var(--er);border:none;color:#fff;border-radius:var(--r2);padding:10px;font-family:var(--fb);font-size:13px;font-weight:600;cursor:pointer;transition:all .2s}
.btn-er:hover{background:#d62f24}
.btn-er:disabled{opacity:.4;cursor:not-allowed}

@media(max-width:640px){
  html,body{overflow:hidden}
  .hdr{padding:0 14px;height:52px}
  .brand-sub{display:none}
  .hdr-nav{display:none}
  .clock{font-size:11px;letter-spacing:.5px}
  .chip{padding:3px 8px;font-size:10px}
  .metrics{justify-content:flex-start;overflow-x:auto;scrollbar-width:none;padding:0 10px;height:48px}
  .metrics::-webkit-scrollbar{display:none}
  .metric{padding:0 11px}
  .mval{font-size:16px}
  .mlbl{font-size:9px}
  .mdiv{height:20px}
  .grid{grid-template-columns:1fr;gap:10px;padding:10px 12px;overflow-y:auto;overflow-x:hidden}
  .grid > .card:first-child{min-height:260px;max-height:44vh}
  .rcol{flex-direction:row;gap:10px;overflow:visible}
  .ucard,.bcard{flex:1;min-height:190px;max-height:36vh}
  .reg{grid-template-columns:1fr;gap:14px;padding:14px 12px}
  .cam-sec{order:-1}
  .cam-wrap{border-radius:16px}
  .fgrid{grid-template-columns:1fr 1fr}
  .udel{width:32px;height:32px;font-size:13px;border-radius:8px}
  .btn-pri{padding:14px;font-size:15px;border-radius:14px}
  .finp,.fsel{padding:12px 13px;font-size:15px;border-radius:10px}
  .bi{padding:10px 12px}
  .mbd{align-items:flex-end}
  .modal{border-radius:20px 20px 0 0;margin:0;max-width:100%;animation:mob-slide .3s var(--spring)}
  @keyframes mob-slide{from{transform:translateY(100%)}to{transform:translateY(0)}}
  .modal::before{content:'';display:block;width:36px;height:4px;background:var(--border-2);border-radius:2px;margin:10px auto 0}
  .del-modal{padding:16px 20px 36px;border-radius:20px 20px 0 0;max-width:100%}
}

@media(min-width:641px) and (max-width:900px){
  .hdr{padding:0 16px}
  .hdr-nav .nav-btn{padding:5px 10px;font-size:12px}
  .metric{padding:0 16px}
  .grid{grid-template-columns:1fr 250px;padding:14px 16px;gap:10px}
  .reg{grid-template-columns:1fr 300px;padding:16px}
}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-brand">
    <div class="brand-mark">⬡</div>
    <div>
      <div class="brand-name">Loker Security</div>
      <div class="brand-sub">Politeknik Negeri Lhokseumawe</div>
    </div>
  </div>
  <nav class="hdr-nav">
    <button class="nav-btn active" onclick="goTab('monitoring',this)">Monitoring</button>
    <button class="nav-btn" onclick="goTab('daftar',this)">Pendaftaran</button>
    <a href="live.html" class="nav-btn">Live CCTV</a>
  </nav>
  <div class="hdr-status">
    <div class="chip"><span class="sdot" id="espDot"></span><span id="espLbl">ESP32</span></div>
    <div class="chip"><span class="sdot" id="srvDot"></span><span id="srvLbl">Server</span></div>
    <time class="clock" id="clk">--:--:--</time>
  </div>
</header>

<section class="metrics">
  <div class="metric"><span class="mval ok" id="mOk">0</span><span class="mlbl">Akses Berhasil</span></div>
  <div class="mdiv"></div>
  <div class="metric"><span class="mval er" id="mEr">0</span><span class="mlbl">Akses Ditolak</span></div>
  <div class="mdiv"></div>
  <div class="metric"><span class="mval info" id="mDf">0</span><span class="mlbl">Pendaftaran</span></div>
  <div class="mdiv"></div>
  <div class="metric"><span class="mval" id="mUs">0</span><span class="mlbl">Pengguna</span></div>
  <div class="mdiv"></div>
  <div class="metric"><span class="mval chain" id="mCh">—</span><span class="mlbl">Blockchain</span></div>
</section>

<div class="tab active" id="t-monitoring">
  <div class="grid">
    <div class="card">
      <div class="card-hdr">
        <div class="card-ttl"><span class="pdot" id="liveDot"></span>Aktivitas Real-Time</div>
        <span class="fcnt" id="fcnt">0 log</span>
      </div>
      <div class="card-body feed-body" id="feedList">
        <div class="empty"><div class="empty-ico">◎</div><p>Menunggu aktivitas…</p><small>Sistem siap memantau</small></div>
      </div>
    </div>
    <div class="rcol">
      <div class="card ucard">
        <div class="card-hdr">
          <div class="card-ttl">Pengguna Terdaftar</div>
          <span class="badge" id="ucnt">0</span>
        </div>
        <div class="card-body ubody" id="uList"><div class="empty sm">Belum ada pengguna</div></div>
      </div>
      <div class="card bcard">
        <div class="card-hdr">
          <div class="card-ttl">Log Blockchain</div>
          <div style="display:flex;align-items:center;gap:8px">
            <div class="cval"><span class="cdot v" id="cdot"></span><span id="clbl">Valid</span></div>
            <button class="btn-reset-chain" onclick="resetBlockchain()">Hapus</button>
          </div>
        </div>
        <div class="card-body cbody" id="cList"><div class="empty sm">Memuat…</div></div>
      </div>
    </div>
  </div>
</div>

<div class="tab" id="t-daftar">
  <div class="reg">
    <div>
      <div class="sec-hdr">
        <h2 class="sec-ttl">Daftar Pengguna Baru</h2>
        <p class="sec-desc">ESP32-CAM mengambil 5 foto otomatis. Mode stream dimatikan sementara selama pendaftaran. Foto tanpa wajah otomatis dilewati.</p>
      </div>
      <div class="fgrid">
        <div class="fg full"><label class="flbl">Nama Lengkap</label><input class="finp" id="rNama" type="text" placeholder="Masukkan nama lengkap"></div>
        <div class="fg"><label class="flbl">Kelas</label><input class="finp" id="rKelas" type="text" placeholder="Contoh: TI-3A"></div>
        <div class="fg"><label class="flbl">Semester</label><input class="finp" id="rSem" type="text" placeholder="Contoh: 6"></div>
        <div class="fg full"><label class="flbl">Nomor Loker</label>
          <select class="fsel" id="rLoker">
            <option value="1">Loker 1 — Solenoid 1</option>
            <option value="2">Loker 2 — Solenoid 2</option>
          </select>
        </div>
      </div>
      <button class="btn-pri" id="btnDftr" onclick="daftar()">◉ &nbsp;Mulai Pendaftaran</button>
      <div class="mode-banner" id="modeBanner">
        <span>⏸</span><span id="modeBannerText">Mode pendaftaran aktif — stream dimatikan sementara</span>
      </div>
      <div class="prog-wrap" id="progWrap">
        <div class="prog-top"><span id="progLbl">Memproses…</span><span id="progPct">0%</span></div>
        <div class="prog-track"><div class="prog-bar" id="progBar"></div></div>
        <div class="prog-log" id="progLog"></div>
      </div>
    </div>
    <div class="cam-sec">
      <div class="cam-wrap">
        <img id="camPrev" src="" alt="Kamera" onerror="camErr()" onload="camOk()">
        <div class="cam-ovl">
          <div class="cc tl"></div><div class="cc tr"></div>
          <div class="cc bl"></div><div class="cc br"></div>
        </div>
        <div class="cam-badge" id="camBadge">
          <span class="cdotl" id="camDotl"></span>
          <span id="camBadgeTxt">Menghubungkan…</span>
        </div>
      </div>
      <p class="cam-cap">Preview via Server Flask · stream jeda saat pendaftaran berlangsung</p>
    </div>
  </div>
</div>

<div class="mbd" id="mBlok" onclick="if(event.target===this)closeBlok()">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="m-hdr">
      <h3 class="m-ttl">Detail Blok</h3>
      <button class="m-cl" onclick="closeBlok()">✕</button>
    </div>
    <div class="m-body" id="mBlokBody"></div>
  </div>
</div>

<div class="mbd" id="mHapus" onclick="if(event.target===this)batal()">
  <div class="modal del-modal" onclick="event.stopPropagation()">
    <div class="del-ico">⚠</div>
    <h3 class="del-ttl">Hapus Pengguna?</h3>
    <p class="del-desc">Semua data dan foto dataset milik</p>
    <p class="del-nm" id="delNm">—</p>
    <p class="del-desc">akan dihapus permanen dari ESP32 dan server.</p>
    <div class="del-btns">
      <button class="btn-ghost" onclick="batal()">Batalkan</button>
      <button class="btn-er" id="btnHapus" onclick="hapus()">Hapus Sekarang</button>
    </div>
  </div>
</div>

<script>
'use strict';

// ================================================================
// KONFIGURASI IP — sesuai jaringan lokal
// ================================================================
const SRV_IP = '192.168.1.6';   // IP server Flask (PC kamu)
const ESP_IP = '192.168.1.7';   // IP ESP32-CAM

const ESP    = 'http://' + ESP_IP + ':82';
const SRV    = 'http://' + SRV_IP + ':5000';

// ================================================================
// FIX LAG STREAM:
// - Tidak pakai cache-buster di setiap reconnect (hanya saat error)
// - Tambah header Cache-Control via meta agar browser tidak buffer
// - Gunakan ?nocache= hanya saat benar-benar reconnect
// ================================================================
const STREAM = 'http://' + SRV_IP + ':5000/video';

let fc = 0, delKey = null;
let sedangDaftar = false;

setInterval(() => {
  document.getElementById('clk').textContent = new Date().toTimeString().slice(0,8);
}, 1000);

function goTab(id, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('t-' + id).classList.add('active');
  btn.classList.add('active');
  if (id === 'daftar') camStart();
}

async function pingESP() {
  const d = document.getElementById('espDot');
  const l = document.getElementById('espLbl');
  try {
    const r = await fetch(ESP + '/status', { signal: AbortSignal.timeout(4000) });
    if (r.ok) { d.className = 'sdot on'; l.textContent = 'ESP32'; }
    else throw new Error();
  } catch {
    d.className = 'sdot off'; l.textContent = 'ESP32 ✗';
  }
}
setInterval(pingESP, 10000); pingESP();

// ================================================================
// CAMERA — native MJPEG <img> dengan fix lag
// ================================================================
let camErrCount = 0;
let camErrTimer = null;

function camStart() {
  clearTimeout(camErrTimer);
  const img = document.getElementById('camPrev');
  // Hanya tambah nocache saat reconnect untuk flush koneksi browser
  img.src = STREAM + '?nocache=' + Date.now();
}

function camOk() {
  camErrCount = 0;
  clearTimeout(camErrTimer);
  document.getElementById('camPrev').classList.add('on');
  const dot = document.getElementById('camDotl');
  const txt = document.getElementById('camBadgeTxt');
  if (sedangDaftar) {
    dot.className = 'cdotl rec';
    txt.textContent = 'Pendaftaran berlangsung';
  } else {
    dot.className = 'cdotl live';
    txt.textContent = 'Live';
  }
}

function camErr() {
  camErrCount++;
  document.getElementById('camPrev').classList.remove('on');
  document.getElementById('camDotl').className = 'cdotl';
  document.getElementById('camBadgeTxt').textContent =
    'Stream terputus — reconnect ke-' + camErrCount + '…';
  const delay = Math.min(1500 * camErrCount, 8000);
  camErrTimer = setTimeout(camStart, delay);
}

camStart();

// ── Feed ──
const FEED_MAP = {
  akses_berhasil:   { c:'ok',  s:'✓ Akses Diterima',   d: d => 'Loker ' + d.loker + ' · Conf: ' + d.confidence },
  akses_ditolak:    { c:'er',  s:'✗ Akses Ditolak',     d: d => 'Score: ' + d.confidence },
  daftar_selesai:   { c:'inf', s:'○ Daftar Selesai',    d: d => (d.kelas||'') + ' · Loker ' + (d.loker||'') },
  daftar_proses:    { c:'inf', s:'◉ Foto',               d: d => d.pesan||'' },
  pengguna_dihapus: { c:'wn',  s:'⊗ Pengguna Dihapus',  d: _d => '' },
};

function addFeed(tipe, data, ts) {
  const list = document.getElementById('feedList');
  const emp  = list.querySelector('.empty');
  if (emp) emp.remove();
  fc++;
  document.getElementById('fcnt').textContent = fc + ' log';
  const m = FEED_MAP[tipe];
  if (!m) return;
  const el = document.createElement('div');
  el.className = 'fi ' + m.c;
  el.innerHTML = `
    <div class="fi-hdr">
      <span class="fi-st ${m.c}">${m.s}</span>
      <span class="fi-tm">${ts||'--:--:--'}</span>
    </div>
    <div class="fi-nm">${data.nama||'—'}</div>
    <div class="fi-dt">${m.d(data)}</div>`;
  list.insertBefore(el, list.firstChild);
  while (list.children.length > 100) list.removeChild(list.lastChild);
}

function renderUsers(list) {
  document.getElementById('ucnt').textContent = list.length;
  document.getElementById('mUs').textContent  = list.length;
  const el = document.getElementById('uList');
  if (!list.length) { el.innerHTML = '<div class="empty sm">Belum ada pengguna</div>'; return; }
  el.innerHTML = list.map(u => {
    const ini = u.nama.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
    const key = u.nama_key.replace(/'/g,"\\'");
    const nm  = u.nama.replace(/'/g,"\\'");
    return `<div class="ui">
      <div class="uav">${ini}</div>
      <div class="uinfo">
        <div class="unm">${u.nama}</div>
        <div class="umt">${u.kelas} · Sem ${u.semester}</div>
      </div>
      <span class="ulok">L${u.loker}</span>
      <button class="udel" onclick="konfHapus('${key}','${nm}')">✕</button>
    </div>`;
  }).join('');
}

async function loadUsers() {
  try {
    const r = await fetch(SRV + '/api/pengguna');
    const d = await r.json();
    renderUsers(d.pengguna || []);
  } catch(e) { console.warn('[Users]', e); }
}

function renderChain(chain, valid) {
  document.getElementById('cdot').className   = 'cdot ' + (valid ? 'v' : 'nv');
  document.getElementById('clbl').textContent = valid ? 'Valid' : 'Tidak Valid';
  document.getElementById('mCh').textContent  = valid ? '✓ Valid' : '✗ Rusak';
  document.getElementById('mCh').style.color  = valid ? 'var(--ok)' : 'var(--er)';
  const el = document.getElementById('cList');
  if (!chain?.length) { el.innerHTML = '<div class="empty sm">Belum ada blok</div>'; return; }
  const ico = {BERHASIL:'✓', DAFTAR:'○', GAGAL:'✗', HAPUS:'⊗', GENESIS:'⬡'};
  el.innerHTML = [...chain].reverse().map(b => {
    const s   = b.data.status_akses || 'GENESIS';
    const det = s === 'HAPUS'
      ? 'Dihapus dari sistem'
      : (b.data.kelas||'') + ' · Sem ' + (b.data.semester||'') + ' · Loker ' + (b.data.loker||'—');
    return `<div class="bi ${s}" onclick="lihatBlok(${b.index})">
      <div class="bi-hdr"><span class="bi-idx">#${b.index}</span><span class="bi-st ${s}">${ico[s]||'?'} ${s}</span></div>
      <div class="bi-nm">${b.data.nama}</div>
      <div class="bi-mt">${det} · ${b.data.tanggal_akses||''} ${b.data.jam_akses||''}</div>
      <div class="bi-hsh">⬡ ${b.hash}</div>
    </div>`;
  }).join('');
}

async function refreshChain() {
  try {
    const r = await fetch(SRV + '/api/blockchain');
    const d = await r.json();
    renderChain(d.rantai, d.valid);
  } catch {}
}

async function lihatBlok(idx) {
  try {
    const r = await fetch(SRV + '/api/blockchain');
    const d = await r.json();
    const b = d.rantai.find(x => x.index === idx);
    if (!b) return;
    document.getElementById('mBlokBody').innerHTML = [
      ['Index','#'+b.index], ['Timestamp',b.timestamp], ['Nama',b.data.nama],
      ['Kelas',b.data.kelas||'—'], ['Semester',b.data.semester||'—'], ['Loker',b.data.loker||'—'],
      ['Jam',b.data.jam_akses||'—'], ['Tanggal',b.data.tanggal_akses||'—'],
      ['Status',b.data.status_akses||'—'], ['Confidence',b.data.confidence||'—'],
      ['Prev Hash',b.hash_sebelumnya], ['Hash',b.hash]
    ].map(([k,v]) => `<div class="mr"><span class="mk">${k}</span><span class="mv">${v}</span></div>`).join('');
    document.getElementById('mBlok').classList.add('open');
  } catch(e) { console.warn(e); }
}
function closeBlok() { document.getElementById('mBlok').classList.remove('open'); }

async function resetBlockchain() {
  if (!confirm('Hapus semua log blockchain? Tidak bisa dibatalkan.')) return;
  try {
    const r = await fetch(SRV + '/api/blockchain/reset', { method: 'POST' });
    const d = await r.json();
    if (d.ok) await refreshChain();
    else alert('Gagal: ' + (d.pesan || 'Error'));
  } catch(e) { alert('Koneksi server gagal: ' + e.message); }
}

function konfHapus(key, nama) {
  delKey = key;
  document.getElementById('delNm').textContent = nama;
  document.getElementById('mHapus').classList.add('open');
}
function batal() { delKey = null; document.getElementById('mHapus').classList.remove('open'); }
async function hapus() {
  if (!delKey) return;
  const btn = document.getElementById('btnHapus');
  btn.disabled = true; btn.textContent = 'Menghapus…';
  try {
    const r = await fetch(ESP + '/hapus/' + delKey, { method: 'DELETE' });
    const d = await r.json();
    if (d.ok) { batal(); await loadUsers(); }
    else alert('Gagal: ' + (d.pesan || 'Error'));
  } catch(e) { alert('Koneksi ESP32 gagal: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Hapus Sekarang'; }
}

function setProgress(pct, lbl) {
  document.getElementById('progBar').style.width = pct + '%';
  document.getElementById('progLbl').textContent = lbl;
  document.getElementById('progPct').textContent = pct + '%';
  document.getElementById('progWrap').classList.add('show');
}
function logProg(msg, t) {
  const ico = t==='ok' ? '✓' : t==='er' ? '✗' : '·';
  const log = document.getElementById('progLog');
  log.innerHTML += `<div class="ll"><span class="ll-ico ${t}">${ico}</span><span class="ll-txt">${msg}</span></div>`;
  log.scrollTop = log.scrollHeight;
}
function setBannerDaftar(aktif) {
  sedangDaftar = aktif;
  const banner = document.getElementById('modeBanner');
  if (aktif) {
    banner.className = 'mode-banner show';
    document.getElementById('modeBannerText').textContent =
      'Mode pendaftaran aktif — stream kamera dimatikan sementara';
    document.getElementById('camDotl').className = 'cdotl rec';
    document.getElementById('camBadgeTxt').textContent = 'Pendaftaran berlangsung';
  } else {
    banner.className = 'mode-banner';
    camStart();
  }
}

async function daftar() {
  const nama  = document.getElementById('rNama').value.trim();
  const kelas = document.getElementById('rKelas').value.trim();
  const sem   = document.getElementById('rSem').value.trim();
  const loker = parseInt(document.getElementById('rLoker').value);

  if (!nama || !kelas || !sem) {
    alert('Lengkapi semua data terlebih dahulu.'); return;
  }

  const btn = document.getElementById('btnDftr');
  btn.disabled = true; btn.textContent = '⏳ Mendaftarkan…';
  document.getElementById('progLog').innerHTML = '';

  try { await fetch(SRV + '/api/stream/pause', { method:'POST' }); } catch {}

  setBannerDaftar(true);
  setProgress(5, 'Menghubungi ESP32…');
  logProg('Mengirim perintah ke ESP32-CAM…', 'inf');

  try {
    const r = await fetch(ESP + '/daftar', {
      method:  'POST',
      headers: {'Content-Type':'application/json'},
      body:    JSON.stringify({ nama, kelas, semester: sem, loker })
    });
    const d = await r.json();
    if (d.ok) {
      logProg('ESP32 memulai pengambilan 5 foto…', 'ok');
      setProgress(15, 'Mengambil foto…');
      setTimeout(() => {
        if (sedangDaftar) setProgress(80, 'Menunggu konfirmasi server…');
      }, 12000);
    } else {
      logProg('Gagal: ' + (d.pesan||'Error dari ESP32'), 'er');
      setProgress(0, 'Gagal');
      setBannerDaftar(false);
      try { await fetch(SRV + '/api/stream/resume', { method:'POST' }); } catch {}
    }
  } catch(e) {
    logProg('Error koneksi ke ESP32: ' + e.message, 'er');
    setProgress(0, 'Koneksi gagal');
    setBannerDaftar(false);
    try { await fetch(SRV + '/api/stream/resume', { method:'POST' }); } catch {}
  } finally {
    btn.disabled = false;
    btn.innerHTML = '◉ &nbsp;Mulai Pendaftaran';
  }
}

// ── SSE ──
let sseRetryDelay = 2000;

function sseConnect() {
  const es = new EventSource(SRV + '/events');

  es.onopen = () => {
    sseRetryDelay = 2000;
    document.getElementById('srvDot').className   = 'sdot on';
    document.getElementById('srvLbl').textContent = 'Server';
    document.getElementById('liveDot').className  = 'pdot';
  };

  es.onmessage = (e) => {
    try {
      const { tipe, data, timestamp } = JSON.parse(e.data);
      if (tipe === 'ping') return;

      if (tipe === 'init') {
        if (data.statistik) updateStats(data.statistik);
        renderChain(data.rantai, data.valid);
        data.pengguna ? renderUsers(data.pengguna) : loadUsers();
        return;
      }

      addFeed(tipe, data, timestamp);
      if (data.statistik) updateStats(data.statistik);

      if (['daftar_selesai','pengguna_dihapus','akses_berhasil','akses_ditolak'].includes(tipe)) {
        refreshChain();
      }

      if (data.pengguna) renderUsers(data.pengguna);
      else if (['daftar_selesai','pengguna_dihapus'].includes(tipe)) loadUsers();

      if (tipe === 'daftar_proses' && data.nomor_foto != null) {
        const pct = 15 + (data.nomor_foto / 5) * 65;
        setProgress(pct, data.pesan || '');
        logProg(data.pesan, data.ok ? 'ok' : 'er');
      }

      if (tipe === 'daftar_selesai') {
        setProgress(100, '✓ Pendaftaran Selesai');
        logProg((data.nama||'') + ' berhasil terdaftar!', 'ok');
        setBannerDaftar(false);
        setTimeout(() => {
          document.getElementById('rNama').value  = '';
          document.getElementById('rKelas').value = '';
          document.getElementById('rSem').value   = '';
          document.getElementById('progWrap').classList.remove('show');
        }, 5000);
      }

    } catch(_) {}
  };

  es.onerror = () => {
    document.getElementById('srvDot').className   = 'sdot off';
    document.getElementById('srvLbl').textContent = 'Server ✗';
    document.getElementById('liveDot').className  = 'pdot off';
    es.close();
    sseRetryDelay = Math.min(sseRetryDelay * 1.5, 15000);
    setTimeout(sseConnect, sseRetryDelay);
  };
}

function updateStats(s) {
  if (s.total_berhasil != null) document.getElementById('mOk').textContent = s.total_berhasil;
  if (s.total_gagal    != null) document.getElementById('mEr').textContent = s.total_gagal;
  if (s.total_daftar   != null) document.getElementById('mDf').textContent = s.total_daftar;
}

sseConnect();
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
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
