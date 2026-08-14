"""把网页手动下载的视频收纳进项目输入目录，统一命名并给出下一步命令。

这是流水线第一步：在 MiniMax H3（或其他视频生成平台）网页上
用"参考图 + 提示词"生成视频并下载到本地后，用本脚本一键放进
input/，之后再用 extract_frames.py 抽帧。详见 README「第一步」一节。

用法:
    .venv/Scripts/python src/ingest_video.py 视频.mp4                    # 复制进 input/
    .venv/Scripts/python src/ingest_video.py 视频.mp4 --name 走路循环      # 自定义名称
    .venv/Scripts/python src/ingest_video.py 视频.mp4 --move --open        # 移动并打开预览
    .venv/Scripts/python src/ingest_video.py --list                       # 列出已收纳视频

选项:
    --name 名称   收纳后的文件名（默认取源文件名，特殊字符替换为 _）
    --move        移动而不是复制（源文件删除，节省空间）
    --open        收纳后用系统播放器打开视频，先看效果再决定是否抽帧
    --list        列出 input/ 下的视频
"""

import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
INPUT_DIR = os.path.join(ROOT, "input")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe") if os.name == "nt" \
    else os.path.join(ROOT, ".venv", "bin", "python")


def normalize(name: str) -> str:
    """文件名安全化：保留中英文/数字/_-，其余字符替换为 _。"""
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", os.path.splitext(name)[0]).strip("_")
    return safe or "video"


def unique_path(name: str) -> str:
    """input/ 下不重名：已存在则追加 _2、_3……"""
    os.makedirs(INPUT_DIR, exist_ok=True)
    target = os.path.join(INPUT_DIR, name + ".mp4")
    n = 2
    while os.path.exists(target):
        target = os.path.join(INPUT_DIR, f"{name}_{n}.mp4")
        n += 1
    return target


def open_video(path: str) -> None:
    """调用系统默认播放器打开视频。"""
    if os.name == "nt":
        os.startfile(path)  # noqa: S606
    else:
        import webbrowser
        webbrowser.open(path)


def ingest(video: str, name: str = "", move: bool = False,
           open_after: bool = False) -> str:
    if not os.path.isfile(video):
        sys.exit(f"找不到视频文件: {video}")
    if os.path.splitext(video)[1].lower() != ".mp4":
        sys.exit("目前只支持 mp4 视频（流水线后续抽帧同样只吃 mp4）")

    # 已经在 input/ 里的视频直接跳过收纳
    if os.path.abspath(video).startswith(os.path.abspath(INPUT_DIR) + os.sep):
        print(f"已在 input/ 中，无需收纳: {video}")
        if open_after:
            open_video(video)
        return video

    base = normalize(name) if name else normalize(os.path.basename(video))
    target = unique_path(base)
    (shutil.move if move else shutil.copy2)(video, target)
    size = os.path.getsize(target) / 1024 / 1024
    print(f"已{'移动' if move else '复制'}: {video}")
    print(f"  -> {os.path.abspath(target)}  ({size:.1f} MB)")

    print("\n先看视频再抽帧（动作/循环接缝/主体/绿幕），满意后执行：")
    print(f'  {PY} src\\extract_frames.py "{os.path.relpath(target, ROOT)}" --green')
    print("效果差就回生成平台换提示词/参数重生成，不必抽帧。")
    if open_after:
        open_video(target)
    return target


def list_inputs() -> None:
    if not os.path.isdir(INPUT_DIR) or not any(
            f.lower().endswith(".mp4") for f in os.listdir(INPUT_DIR)):
        print("input/ 下还没有视频。用法: .venv/Scripts/python src\\ingest_video.py 视频.mp4")
        return
    print(f"input/ 下已收纳的视频（{os.path.abspath(INPUT_DIR)}）:")
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.lower().endswith(".mp4"):
            p = os.path.join(INPUT_DIR, f)
            print(f"  {f}  ({os.path.getsize(p) / 1024 / 1024:.1f} MB)")


def main(argv):
    if "--list" in argv:
        list_inputs()
        return

    VALUE_FLAGS = {"--name"}
    args, i = [], 0
    while i < len(argv):  # 位置参数要跳过选项旗标和它们的值
        if argv[i] in VALUE_FLAGS:
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            args.append(argv[i])
            i += 1

    def opt(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if not args:
        sys.exit(__doc__)
    ingest(args[0], name=opt("--name", ""),
           move="--move" in argv, open_after="--open" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
