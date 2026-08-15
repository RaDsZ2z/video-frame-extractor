"""帧提取与挑帧工具的本地网页界面。

用法:
    .venv/Scripts/python src/server.py [--port 8765]

启动后自动打开浏览器（默认 http://127.0.0.1:8765），在页面上完成:
    上传/选择视频 -> 抽帧(可选绿幕抠图) -> 总览图/差异分析 -> 点选帧 -> 预览 GIF

与命令行共用同一套目录，网页版只是 extract_frames.py / frame_tools.py 的图形入口:
    视频统一放 input/（网页上传会自动收纳进去，重名自动加序号），
    帧与拼图/差异图/GIF 统一产出到 output/<视频名>/。
"""

import json
import os
import re
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import extract_frames
import frame_tools

INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

MIME = {".html": "text/html; charset=utf-8", ".png": "image/png",
        ".gif": "image/gif", ".mp4": "video/mp4"}


def normalize(name: str) -> str:
    """文件名安全化：保留中英文/数字/_-，其余字符替换为 _。"""
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", os.path.splitext(name)[0]).strip("_")
    return safe or "video"


def unique_path(name: str) -> str:
    """input/ 下不重名：已存在则追加 _2、_3……"""
    target = os.path.join(INPUT_DIR, name + ".mp4")
    n = 2
    while os.path.exists(target):
        target = os.path.join(INPUT_DIR, f"{name}_{n}.mp4")
        n += 1
    return target


def safe_name(name: str) -> str:
    """项目名即 output/ 下的目录名，拒绝路径穿越。"""
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"非法名称: {name!r}")
    return name


def project_dir(name: str) -> str:
    return os.path.join(OUTPUT_DIR, safe_name(name))


def frames_dir(name: str) -> str:
    return os.path.join(project_dir(name), "frames")


def out_url(name: str, filename: str) -> str:
    """output/<项目>/<文件> 对应的浏览 URL（名称可能含中文，需转义）。"""
    return f"/out/{quote(name)}/{filename}"


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

    def serve_under(self, root, rel):
        """静态服务 root 下的文件（rel 需反转义），禁止越出 root。"""
        full = os.path.join(root, os.path.normpath(unquote(rel)))
        if not os.path.abspath(full).startswith(os.path.abspath(root) + os.sep):
            return self.send_error(403)
        return self.send_file(full)

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
        path, qs = url.path, parse_qs(url.query)
        if path == "/":
            return self.send_file(os.path.join(SCRIPT_DIR, "index.html"))
        if path == "/api/list":
            videos = sorted(f for f in os.listdir(INPUT_DIR)
                            if f.lower().endswith(".mp4"))
            projects = []
            for d in sorted(os.listdir(OUTPUT_DIR)):
                fd = os.path.join(OUTPUT_DIR, d, "frames")
                if os.path.isdir(fd):
                    n = len([f for f in os.listdir(fd) if f.endswith(".png")])
                    projects.append({"name": d, "frames": n})
            return self.send_json({"videos": videos, "projects": projects})
        if path == "/api/frames":
            try:
                frames = frame_tools.list_frames(frames_dir(qs.get("name", [""])[0]))
            except (SystemExit, ValueError, FileNotFoundError):  # 项目不存在或无帧时返回空列表
                frames = []
            return self.send_json({"frames": [n for n, _ in frames]})
        if path == "/api/diff":
            try:
                name = safe_name(qs.get("name", [""])[0])
                chart = os.path.join(project_dir(name), "diff_chart.png")
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            holder = {}

            def work():
                holder["info"] = frame_tools.analyze_diff(frames_dir(name), chart)

            if not self.run_tool(work):
                return
            info = holder["info"]
            info["chart_url"] = out_url(name, "diff_chart.png")
            info.pop("chart", None)
            info.pop("csv", None)
            return self.send_json(info)
        if path.startswith("/out/"):
            return self.serve_under(OUTPUT_DIR, path[len("/out/"):])
        if path.startswith("/in/"):
            return self.serve_under(INPUT_DIR, path[len("/in/"):])
        return self.send_error(404)

    # ---------------- POST ----------------
    def do_POST(self):
        url = urlparse(self.path)
        path, qs = url.path, parse_qs(url.query)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if path == "/api/extract":
            return self.api_extract(qs, body)
        if path == "/api/sheet" or path == "/api/preview" or path == "/api/loop":
            try:
                opts = json.loads(body or b"{}")
            except ValueError:  # 非法 JSON 或非 UTF-8 编码（JSONDecodeError/UnicodeDecodeError 都是 ValueError）
                return self.send_json({"error": "请求体不是合法的 UTF-8 JSON"}, 400)
        if path == "/api/sheet":
            try:
                name = safe_name(opts.get("name", ""))
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            out = os.path.join(project_dir(name), "contact_sheet.png")
            return self.run_tool(lambda: frame_tools.cmd_sheet(
                frames_dir(name), out,
                int(opts.get("cols", 5)), int(opts.get("width", 240)))) \
                and self.send_json({"url": out_url(name, "contact_sheet.png")})
        if path == "/api/preview":
            nums = opts.get("frames")
            if not nums:
                return self.send_json({"error": "请先选择至少一帧"}, 400)
            try:
                name = safe_name(opts.get("name", ""))
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            spec = ",".join(str(n) for n in sorted(nums))
            fps = int(opts.get("fps", 12))
            out = os.path.join(project_dir(name), "preview.gif")
            return self.run_tool(lambda: frame_tools.cmd_preview(
                frames_dir(name), spec, fps, out)) \
                and self.send_json({"url": out_url(name, "preview.gif")})
        if path == "/api/loop":
            try:
                name = safe_name(opts.get("name", ""))
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            strip = os.path.join(project_dir(name), "loop_strip.png")
            gif = os.path.join(project_dir(name), "loop_preview.gif")
            holder = {}

            def work():
                holder["info"] = frame_tools.analyze_loop(
                    frames_dir(name),
                    int(opts.get("min", 4)), int(opts.get("max", 60)),
                    int(opts.get("fps", 18)), strip, gif)

            if not self.run_tool(work):
                return
            info = holder["info"]
            info.pop("strip", None)
            info.pop("gif", None)
            info["strip_url"] = out_url(name, "loop_strip.png")
            info["gif_url"] = out_url(name, "loop_preview.gif")
            return self.send_json(info)
        return self.send_error(404)

    def api_extract(self, qs, body):
        green = qs.get("green", ["0"])[0] == "1"
        color = qs.get("color", ["0x00FF00"])[0].replace("#", "0x")
        sim = qs.get("similarity", ["0.08"])[0]
        blend = qs.get("blend", ["0.02"])[0]

        if body:  # 上传新视频：先收纳进 input/（安全化命名 + 重名加序号）
            raw = qs.get("name", ["video.mp4"])[0]
            if os.path.splitext(raw)[1].lower() != ".mp4":
                return self.send_json({"error": "只支持 mp4 视频"}, 400)
            video = unique_path(normalize(raw))
            with open(video, "wb") as f:
                f.write(body)
        else:  # 不上传时直接抽 input/ 里已有的视频
            src = qs.get("input", [""])[0]
            video = os.path.join(INPUT_DIR, os.path.basename(src))
            if not src or not os.path.isfile(video):
                return self.send_json({"error": "没有收到视频数据"}, 400)

        name = os.path.splitext(os.path.basename(video))[0]
        out = frames_dir(name)
        shutil.rmtree(out, ignore_errors=True)  # 重抽时清掉旧帧
        if not self.run_tool(lambda: extract_frames.extract(
                video, out, green, color, sim, blend)):
            return
        count = len([f for f in os.listdir(out) if f.endswith(".png")])
        self.send_json({"count": count, "name": name})


class SingletonHTTPServer(ThreadingHTTPServer):
    """关掉地址重用：让端口充当单实例锁，第二个实例 bind 时直接失败。

    （默认 allow_reuse_address=1 在 Windows 下允许多个进程同时监听同一端口，
    请求会被随机分给其中任意一个，新旧代码并存时接口行为不稳定。）
    """
    allow_reuse_address = False


def main():
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    url = f"http://127.0.0.1:{port}"
    try:
        server = SingletonHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"端口 {port} 已被占用：已有实例在运行，本次不再重复启动，直接打开浏览器。")
        print("想换用最新代码的话，先关闭旧的服务终端窗口再启动；")
        print("刚关闭时端口可能几十秒内未释放，提示占用就稍等再试。")
        webbrowser.open(url)
        return
    print(f"服务已启动: {url}  (Ctrl+C 停止)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
