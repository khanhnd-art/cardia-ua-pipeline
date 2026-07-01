#!/usr/bin/env python3
"""Cardia — server local nhẹ: xem dashboard + nút "Pull data mới" chạy pipeline thủ công.

Chạy:  python3 serve.py        → mở http://localhost:8787/
       CARDIA_PORT=9000 python3 serve.py   (đổi port)

- Chỉ lắng nghe 127.0.0.1 (không expose ra mạng).
- POST /api/pull   → chạy run_pipeline.sh ở thread nền (pull → dashboard → weekly report).
- GET  /api/status → trạng thái lần chạy gần nhất (cho nút poll).
- Mọi đường khác → serve file tĩnh trong thư mục này (mặc định dashboard.html).
Chỉ dùng thư viện chuẩn Python 3.
"""
import http.server, socketserver, subprocess, threading, json, pathlib, os, time

HERE = pathlib.Path(__file__).resolve().parent
PORT = int(os.environ.get("CARDIA_PORT", "8787"))
PIPELINE = HERE / "run_pipeline.sh"

STATE = {"running": False, "started_at": None, "finished_at": None, "ok": None, "tail": ""}
LOCK = threading.Lock()


def run_pipeline():
    with LOCK:
        if STATE["running"]:
            return
        STATE.update(running=True, started_at=time.time(), finished_at=None, ok=None, tail="")
    ok, tail = False, ""
    try:
        p = subprocess.run(["bash", str(PIPELINE)], cwd=str(HERE),
                           capture_output=True, text=True, timeout=900)
        ok = (p.returncode == 0)
        tail = ((p.stdout or "") + (p.stderr or ""))[-800:]
    except Exception as e:
        tail = str(e)
    with LOCK:
        STATE.update(running=False, finished_at=time.time(), ok=ok, tail=tail)


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(HERE), **k)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") == "/api/pull":
            threading.Thread(target=run_pipeline, daemon=True).start()
            return self._json({"started": True})
        self._json({"error": "not found"}, 404)

    def guess_type(self, path):
        t = super().guess_type(path)
        if t == "text/html":
            return "text/html; charset=utf-8"
        return t

    def do_GET(self):
        if self.path.rstrip("/") == "/api/status":
            with LOCK:
                return self._json(dict(STATE))
        if self.path in ("/", ""):
            self.path = "/dashboard.html"
        return super().do_GET()

    def log_message(self, *a):
        pass  # im lặng cho gọn terminal


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as httpd:
        print(f"▶ Cardia dashboard: http://localhost:{PORT}/")
        print("  Nút 'Pull data mới' (sidebar) sẽ chạy run_pipeline.sh rồi tự reload.")
        print("  Ctrl+C để dừng.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n⏹ đã dừng server.")
