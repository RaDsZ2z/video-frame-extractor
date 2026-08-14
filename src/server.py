"""帧提取与挑帧工具的本地网页界面。

用法:
    .venv/Scripts/python src/server.py [--port 8765]

启动后自动打开浏览器（默认 http://127.0.0.1:8765），在页面上完成:
    上传视频 -> 抽帧(可选绿幕抠图) -> 总览图/差异分析 -> 点选帧 -> 预览 GIF
"""

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import extract_frames
import frame_tools

WS = os.path.join(PROJECT_ROOT, "workspace")
FRAMES_DIR = os.path.join(WS, "frames")
OUT_DIR = os.path.join(WS, "output")
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

MIME = {".html": "text/html; charset=utf-8", ".png": "image/png",
        ".gif": "image/gif", ".mp4": "video/mp4"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext not in MIME or not os.path.isfile(path):
            return self.send_error(404)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME[ext])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def run_tool(self, fn):
        """调用 frame_tools/extract_frames 里的函数，把 sys.exit 转成错误响应。"""
        try:
            fn()
            return True
        except SystemExit as e:
            self.send_json({"error": str(e)}, 400)
            return False
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)
            return False

    # ---------------- GET ----------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/":
            return self.send_file(os.path.join(SCRIPT_DIR, "index.html"))
        if path == "/api/frames":
            try:
                frames = frame_tools.list_frames(FRAMES_DIR)
            except SystemExit:  # 帧目录为空时返回空列表，而不是断开连接
                frames = []
            return self.send_json({"frames": [n for n, _ in frames]})
        if path == "/api/diff":
            chart = os.path.join(OUT_DIR, "diff_chart.png")
            holder = {}

            def work():
                holder["info"] = frame_tools.analyze_diff(FRAMES_DIR, chart)

            if not self.run_tool(work):
                return
            info = holder["info"]
            info["chart_url"] = "/ws/output/diff_chart.png"
            info.pop("chart", None)
            return self.send_json(info)
        if path.startswith("/ws/"):
            rel = os.path.normpath(path[len("/ws/"):])
            full = os.path.join(WS, rel)
            if not os.path.abspath(full).startswith(os.path.abspath(WS)):
                return self.send_error(403)
            return self.send_file(full)
        return self.send_error(404)

    # ---------------- POST ----------------
    def do_POST(self):
        url = urlparse(self.path)
        path, qs = url.path, parse_qs(url.query)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if path == "/api/extract":
            return self.api_extract(qs, body)
        if path == "/api/sheet":
            opts = json.loads(body or b"{}")
            return self.run_tool(lambda: frame_tools.cmd_sheet(
                FRAMES_DIR, os.path.join(OUT_DIR, "contact_sheet.png"),
                int(opts.get("cols", 5)), int(opts.get("width", 240)))) \
                and self.send_json({"url": "/ws/output/contact_sheet.png"})
        if path == "/api/preview":
            opts = json.loads(body or b"{}")
            nums = opts.get("frames")
            if not nums:
                return self.send_json({"error": "请先选择至少一帧"}, 400)
            spec = ",".join(str(n) for n in sorted(nums))
            fps = int(opts.get("fps", 12))
            return self.run_tool(lambda: frame_tools.cmd_preview(
                FRAMES_DIR, spec, fps, os.path.join(OUT_DIR, "preview.gif"))) \
                and self.send_json({"url": "/ws/output/preview.gif"})
        return self.send_error(404)

    def api_extract(self, qs, body):
        if not body:
            return self.send_json({"error": "没有收到视频数据"}, 400)
        name = qs.get("name", ["video.mp4"])[0]
        ext = os.path.splitext(name)[1] or ".mp4"
        video = os.path.join(WS, "upload" + ext)
        with open(video, "wb") as f:
            f.write(body)
        # 清空旧帧
        for f in os.listdir(FRAMES_DIR):
            os.remove(os.path.join(FRAMES_DIR, f))
        green = qs.get("green", ["0"])[0] == "1"
        color = qs.get("color", ["0x00FF00"])[0].replace("#", "0x")
        sim = qs.get("similarity", ["0.08"])[0]
        blend = qs.get("blend", ["0.02"])[0]
        if not self.run_tool(lambda: extract_frames.extract(
                video, FRAMES_DIR, green, color, sim, blend)):
            return
        count = len([f for f in os.listdir(FRAMES_DIR) if f.endswith(".png")])
        self.send_json({"count": count})


def main():
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"服务已启动: {url}  (Ctrl+C 停止)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
