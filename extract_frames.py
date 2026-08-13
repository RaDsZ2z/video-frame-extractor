"""把 mp4 视频的全部帧导出为 PNG 序列，可选背景抠图（背景转透明）。

用法:
    .venv/Scripts/python extract_frames.py 视频.mp4 [输出目录] [选项]

    输出目录省略时默认为 output/<视频名>/frames

选项:
    --green            启用背景抠图（对绿幕/白幕等纯色背景均有效）
    --color 0x00FF00   幕布颜色，默认纯绿；建议用取色器取视频里的真实背景色
    --similarity 0.08  颜色容差，越大抠得越狠（建议 0.03~0.1，过大会误抠主体）
    --blend 0.02       边缘柔化程度（默认 0.02）
    --no-fill          不做内部孔洞填补（默认会填补，保护眼睛等亮色部位不被抠穿）

说明:
    幕布是有彩色（如绿幕）时用 chromakey 抠色度并去溢色；幕布是灰白黑等
    无彩色时自动改用 colorkey 按 RGB 距离抠（chromakey 对无彩色背景无效）。
    抠图后默认做"孔洞填补"：不与图像边缘连通的透明区域恢复不透明，
    避免主体上的亮色部位（如白色眼睛）被误抠成洞。

示例:
    .venv/Scripts/python extract_frames.py run.mp4                 # 普通视频
    .venv/Scripts/python extract_frames.py run.mp4 frames --green  # 绿幕视频
    .venv/Scripts/python extract_frames.py run.mp4 frames --green --color 0xFFFFFF  # 白幕视频
"""

import os
import subprocess
import sys

import imageio_ffmpeg


def is_neutral(color: str) -> bool:
    """无彩色（灰/白/黑）幕布返回 True。chromakey 按色度抠，对无彩色无效。"""
    c = color.lstrip("#") if color.startswith("#") else color[2:]
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return max(r, g, b) - min(r, g, b) < 24


def fill_holes(out_dir: str) -> None:
    """每帧里不与边缘连通的透明区域恢复不透明（RGB 保留原色）。"""
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    for f in sorted(os.listdir(out_dir)):
        if not f.endswith(".png"):
            continue
        path = os.path.join(out_dir, f)
        a = np.array(Image.open(path).convert("RGBA"))
        transp = a[..., 3] < 128
        if not transp.any():
            continue
        lab, _ = ndimage.label(transp)
        border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        holes = transp & ~np.isin(lab, border[border != 0])
        if holes.any():
            a[..., 3][holes] = 255
            Image.fromarray(a).save(path)


def extract(video_path: str, out_dir: str, green: bool,
            color: str, similarity: str, blend: str, fill: bool = True) -> None:
    if not os.path.isfile(video_path):
        sys.exit(f"找不到视频文件: {video_path}")
    os.makedirs(out_dir, exist_ok=True)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_pattern = os.path.join(out_dir, "frame_%05d.png")
    cmd = [ffmpeg, "-y", "-i", video_path, "-vsync", "0"]
    if green:
        if is_neutral(color):
            cmd += ["-vf", f"colorkey={color}:{similarity}:{blend}"]
        else:
            cmd += ["-vf", f"chromakey={color}:{similarity}:{blend},despill=type=green"]
    cmd.append(out_pattern)

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        sys.exit(f"ffmpeg 执行失败:\n{err}")

    if green and fill:
        fill_holes(out_dir)

    count = len([f for f in os.listdir(out_dir) if f.endswith(".png")])
    print(f"完成: 共导出 {count} 帧到 {os.path.abspath(out_dir)}")


def main(argv):
    VALUE_FLAGS = {"--color", "--similarity", "--blend"}
    args, i = [], 0
    while i < len(argv):  # 位置参数要跳过选项旗标和它们的值
        if argv[i] in VALUE_FLAGS:
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            args.append(argv[i])
            i += 1

    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    if not args:
        sys.exit(__doc__)
    video = args[0]
    out = args[1] if len(args) > 1 else os.path.join(
        "output", os.path.splitext(os.path.basename(video))[0], "frames")
    extract(video, out,
            green="--green" in argv,
            color=opt("--color", "0x00FF00"),
            similarity=opt("--similarity", "0.08"),
            blend=opt("--blend", "0.02"),
            fill="--no-fill" not in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
