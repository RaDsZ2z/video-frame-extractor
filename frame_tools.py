"""挑帧辅助工具：总览拼图 / 帧差异分析 / 选中帧预览 GIF。

子命令:
    sheet    把帧目录里的所有帧拼成带帧编号的缩略图总览
    diff     计算相邻帧差异，找出静止区段和剧烈动作区段（含循环接缝）
    preview  把挑好的帧合成预览 GIF

用法:
    .venv/Scripts/python frame_tools.py sheet  帧目录 [-o 输出.png] [--cols 5] [--width 240]
    .venv/Scripts/python frame_tools.py diff   帧目录 [--chart 差异图.png]
    .venv/Scripts/python frame_tools.py preview 帧目录 "1-10,15,20-30:2" [--fps 12] [-o preview.gif]

    输出文件省略 -o/--chart 时，默认写到帧目录的上一级
    （如帧目录是 output/视频名/frames，产物就落在 output/视频名/ 下）

帧号写法（preview）:
    1-10     第 1 到 10 帧
    1-30:3   第 1 到 30 帧，每隔 3 帧取一帧
    1,5,9    单帧，逗号分隔，可与区间混用
"""

import csv
import os
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat


def _chart_font(size):
    """加载支持中文的字体，找不到时回退默认字体（中文会显示为方块）。"""
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
        try:
            return ImageFont.truetype(os.path.join(fonts_dir, name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def list_frames(frames_dir):
    """返回 [(帧号, 路径)]，按帧号排序。兼容 frame_00001.png 这类命名。"""
    items = []
    for f in os.listdir(frames_dir):
        m = re.match(r"frame_(\d+)\.png$", f)
        if m:
            items.append((int(m.group(1)), os.path.join(frames_dir, f)))
    if not items:
        sys.exit(f"{frames_dir} 里没有 frame_*.png，先运行 extract_frames.py")
    return sorted(items)


def cmd_sheet(frames_dir, out, cols, width):
    frames = list_frames(frames_dir)
    thumbs = []
    for num, path in frames:
        im = Image.open(path)
        h = int(im.height * width / im.width)
        im = im.resize((width, h))
        thumbs.append((num, im))

    cell_h = thumbs[0][1].height + 18  # 底部留帧号
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * cell_h), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for i, (num, im) in enumerate(thumbs):
        x, y = (i % cols) * width, (i // cols) * cell_h
        if im.mode == "RGBA":  # 透明帧衬洋红底，方便看清抠图效果
            bg = Image.new("RGB", im.size, (255, 0, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        sheet.paste(im.convert("RGB"), (x, y))
        draw.text((x + 4, y + im.height + 2), str(num), fill=(255, 255, 0))
    sheet.save(out)
    print(f"完成: {len(thumbs)} 帧 -> {os.path.abspath(out)} ({sheet.width}x{sheet.height})")


def frame_diffs(frames):
    """相邻帧平均像素差（0~255），返回 [(帧号a, 帧号b, 差值)]。
    最后额外附加一项"尾帧 vs 首帧"，即循环动画的接缝差异。"""
    diffs = []
    prev_num, prev_im = frames[0][0], Image.open(frames[0][1]).convert("L")
    first_num, first_im = prev_num, prev_im
    for num, path in frames[1:]:
        im = Image.open(path).convert("L")
        d = ImageStat.Stat(ImageChops.difference(prev_im, im)).mean[0]
        diffs.append((prev_num, num, d))
        prev_num, prev_im = num, im
    if len(frames) > 2:
        d = ImageStat.Stat(ImageChops.difference(prev_im, first_im)).mean[0]
        diffs.append((prev_num, first_num, d))   # 循环接缝: (尾帧号, 1, 差值)
    return diffs


def analyze_diff(frames_dir, chart):
    frames = list_frames(frames_dir)
    diffs = frame_diffs(frames)
    if not diffs:
        sys.exit("只有一帧，无法比较")
    vals = [d for _, _, d in diffs]
    mx, avg = max(vals), sum(vals) / len(vals)
    still_th = max(avg * 0.3, 0.5)   # 低于此值视为接近静止
    peak_th = avg * 2                # 高于此值视为剧烈变化

    parent = os.path.dirname(frames_dir.rstrip("/\\"))
    csv_path = os.path.join(parent, "frame_diffs.csv") if parent else "frame_diffs.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_a", "frame_b", "diff"])
        w.writerows(diffs)

    if chart:
        col = 8                      # 每列宽度
        label_h = 34                 # 底部编号区（最多 3 位数字竖排）
        plot_h = 130
        title_h = 50                 # 顶部标题/注释区
        w = max(len(diffs) * col, 200)
        h = title_h + plot_h + label_h
        img = Image.new("RGB", (w, h), (30, 30, 30))
        dr = ImageDraw.Draw(img)

        font = _chart_font(13)
        name = os.path.basename(os.path.dirname(os.path.abspath(frames_dir)))
        dr.text((4, 4), f"帧差异分析图 - {name}（共 {len(frames)} 帧）",
                fill=(240, 240, 240), font=font)
        dr.text((4, 21), "柱高=相邻帧灰度差(归一化)  绿=静止,可删冗余  黄=普通  红=剧烈,建议保留  末列=循环接缝(尾帧→首帧)",
                fill=(180, 180, 180), font=font)
        peak_pair = max(diffs, key=lambda t: t[2])
        dr.text((4, 37), f"均值 {avg:.2f}  最大 {mx:.2f}（{peak_pair[0]}-{peak_pair[1]}）",
                fill=(180, 180, 180), font=font)

        y0 = title_h + plot_h        # 柱子的底线
        for i, (a, _, d) in enumerate(diffs):
            bar_h = int(d / mx * (plot_h - 10)) if mx else 0
            color = (80, 200, 80) if d < still_th else ((255, 200, 60) if d <= peak_th else (255, 80, 80))
            dr.rectangle([i * col + 1, y0 - bar_h, i * col + col - 2, y0 - 1], fill=color)
            for j, ch in enumerate(str(a)):   # 编号竖排，如 32 -> 3 在上 2 在下
                dr.text((i * col + 1, y0 + 3 + j * 10), ch, fill=(200, 200, 200))
        dr.line([0, y0, w, y0], fill=(80, 80, 80))
        img.save(chart)

    return {
        "count": len(frames), "avg": round(avg, 2), "max": round(mx, 2),
        "still_th": round(still_th, 2), "peak_th": round(peak_th, 2),
        "still": [[a, b] for a, b, d in diffs if d < still_th],
        "peak": [[a, b] for a, b, d in diffs if d > peak_th],
        "csv": csv_path, "chart": chart,
    }


def cmd_diff(frames_dir, chart):
    info = analyze_diff(frames_dir, chart)
    print(f"共 {info['count']} 帧，平均差异 {info['avg']:.2f}，最大 {info['max']:.2f}")
    print(f"接近静止（diff < {info['still_th']:.2f}，可考虑删减冗余帧）:")
    print("  " + (", ".join(f"{a}-{b}" for a, b in info["still"]) or "无"))
    print(f"剧烈变化（diff > {info['peak_th']:.2f}，动作关键位置，建议保留）:")
    print("  " + (", ".join(f"{a}-{b}" for a, b in info["peak"]) or "无"))
    print(f"明细已写入 {info['csv']}")
    if chart:
        print(f"差异图已保存 {chart}（绿=静止 黄=普通 红=剧烈，横轴为帧序）")


def parse_spec(spec, valid_nums):
    nums = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+))?(?::(\d+))?", part)
        if not m:
            sys.exit(f"无法解析帧号: {part!r}，格式如 1-10,15,20-30:2")
        a, b, step = int(m.group(1)), m.group(2), int(m.group(3) or 1)
        nums.update(range(a, int(b) + 1, step) if b else [a])
    bad = sorted(nums - set(valid_nums))
    if bad:
        sys.exit(f"这些帧号不存在: {bad[:10]}{'...' if len(bad) > 10 else ''}")
    return sorted(nums)


def cmd_preview(frames_dir, spec, fps, out):
    frames = list_frames(frames_dir)
    by_num = dict(frames)
    nums = parse_spec(spec, by_num.keys())
    images = []
    for n in nums:
        im = Image.open(by_num[n])
        if im.mode == "RGBA":  # 透明背景衬洋红，GIF 不好表现 alpha
            bg = Image.new("RGB", im.size, (255, 0, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        images.append(im.convert("RGB"))
    images[0].save(out, save_all=True, append_images=images[1:],
                   duration=int(1000 / fps), loop=0)
    print(f"完成: {len(images)} 帧 -> {os.path.abspath(out)} (fps={fps})")


def opt(argv, name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main():
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("sheet", "diff", "preview"):
        sys.exit(__doc__)
    cmd, frames_dir = argv[0], argv[1]
    parent = os.path.dirname(frames_dir.rstrip("/\\"))

    def default_out(name):  # 默认输出到帧目录的上一级（如 output/视频名/）
        return os.path.join(parent, name) if parent else name

    if cmd == "sheet":
        cmd_sheet(frames_dir, opt(argv, "-o", default_out("contact_sheet.png")),
                  opt(argv, "--cols", 5, int), opt(argv, "--width", 240, int))
    elif cmd == "diff":
        cmd_diff(frames_dir, opt(argv, "--chart", default_out("diff_chart.png")))
    else:
        if len(argv) < 3:
            sys.exit("preview 需要帧号参数，如: preview 帧目录 \"1-10,15\"")
        cmd_preview(frames_dir, argv[2], opt(argv, "--fps", 12, int),
                    opt(argv, "-o", default_out("preview.gif")))


if __name__ == "__main__":
    main()
