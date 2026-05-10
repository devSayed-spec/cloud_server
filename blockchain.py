# ================================================================
#  blockchain.py — Blockchain lokal SHA256 (backup lokal)
#  Dipakai oleh: local_server dan cloud_server
# ================================================================
import hashlib, json, os
from datetime import datetime

BLOCKCHAIN_FILE = "blockchain_data.json"

class Blockchain:
    def __init__(self):
        self.rantai = []
        self._load_atau_buat()

    def _load_atau_buat(self):
        if os.path.exists(BLOCKCHAIN_FILE):
            try:
                with open(BLOCKCHAIN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.rantai = data.get("rantai", [])
                if self.rantai and self.validasi_rantai():
                    print(f"[BC] ✓ Dimuat: {len(self.rantai)} blok")
                    return
            except Exception as e:
                print(f"[BC] ✗ Load gagal: {e}")
            self.rantai = []
        self._genesis()
        self._save()

    def _save(self):
        try:
            with open(BLOCKCHAIN_FILE, "w", encoding="utf-8") as f:
                json.dump({"rantai": self.rantai}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[BC] ✗ Simpan gagal: {e}")

    def _genesis(self):
        g = {
            "index"           : 0,
            "timestamp"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data"            : {
                "nama": "GENESIS", "kelas": "-", "semester": "-", "loker": "-",
                "jam_akses": "00:00:00",
                "tanggal_akses": datetime.now().strftime("%Y-%m-%d"),
                "status_akses": "GENESIS"
            },
            "hash_sebelumnya" : "0" * 64,
            "hash"            : ""
        }
        g["hash"] = self._hash(g)
        self.rantai.append(g)
        print(f"[BC] Genesis: {g['hash'][:20]}...")

    def _hash(self, blok):
        d = {k: v for k, v in blok.items() if k != "hash"}
        return hashlib.sha256(
            json.dumps(d, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def tambah_blok(self, data: dict) -> dict:
        b = {
            "index"           : len(self.rantai),
            "timestamp"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data"            : data,
            "hash_sebelumnya" : self.rantai[-1]["hash"],
            "hash"            : ""
        }
        b["hash"] = self._hash(b)
        self.rantai.append(b)
        self._save()
        print(f"[BC] Blok #{b['index']} | {data.get('status_akses','?')} | {b['hash'][:16]}...")
        return b

    def validasi_rantai(self) -> bool:
        for i in range(1, len(self.rantai)):
            cur = self.rantai[i]
            prv = self.rantai[i - 1]
            if cur["hash"] != self._hash(cur):
                return False
            if cur["hash_sebelumnya"] != prv["hash"]:
                return False
        return True

    def get_statistik(self) -> dict:
        t = {
            "total_blok"    : len(self.rantai),
            "total_daftar"  : 0,
            "total_berhasil": 0,
            "total_gagal"   : 0,
        }
        for b in self.rantai:
            s = b["data"].get("status_akses", "")
            if s == "DAFTAR"  : t["total_daftar"]   += 1
            elif s == "BERHASIL": t["total_berhasil"] += 1
            elif s == "GAGAL"   : t["total_gagal"]    += 1
        t["rantai_valid"] = self.validasi_rantai()
        return t
