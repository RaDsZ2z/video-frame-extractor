"""挑帧辅助工具：总览拼图 / 帧差异分析 / 选中帧预览 GIF / 自动找循环段。

子命令:
    sheet    把帧目录里的所有帧拼成带帧编号的缩略图总览
    diff     计算相邻帧差异，找出静止区段和剧烈动作区段（含循环接缝）
    preview  把挑好的帧合成预览 GIF
    loop     自动寻找最佳循环段（动作周期+起点），输出报告、姿势拼接图和循环预览 GIF

用法:
    .venv/Scripts/python src/frame_tools.py sheet  帧目录 [-o 输出.png] [--cols 5] [--width 240]
    .venv/Scripts/python src/frame_tools.py diff   帧目录 [--chart 差异图.png]
    .venv/Scripts/python src/frame_tools.py preview 帧目录 "1-10,15,20-30:2" [--fps 12] [-o preview.gif]
    .venv/Scripts/python src/frame_tools.py loop   帧目录 [--min 4] [--max 60] [--fps 18]
                                                   [--strip 拼接图.png] [--gif 循环预览.gif]

    输出文件省略 -o/--chart/--strip/--gif 时，默认写到帧目录的上一级
    （如帧目录是 output/视频名/frames，产物就落在 output/视频名/ 下）

帧号写法（preview）:
    1-10     第 1 到 10 帧
    1-30:3   第 1 到 30 帧，每隔 3 帧取一帧
    1,5,9    单帧，逗号分隔，可与区间混用

loop 的原理:
    把所有帧缩成小灰度图后，枚举候选周期 T，比较"帧i vs 帧i+T"的平均差异，
    差异最小的 T 即动作周期；再在该周期下找接缝差异（帧s vs 帧s+T）最小的起点。
    若检测到规律性的重复帧（如每 4 帧重复 1 帧），会顺带报告去重建议。
"""

import csv
import os
import re
import sys
from collections import Counter

import numpy as np
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
        sys.exit(f"{frames_dir} 里没有 frame_*.png，先运行 src\\extract_frames.py")
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
            # 柱子至少 1px，避免全静态帧(mx=0)时画 0 高矩形报错
            bar_h = max(int(d / mx * (plot_h - 10)) if mx else 0, 1)
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


def _gif_ready(im):
    """GIF 不能表现 alpha，透明背景衬洋红。"""
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 0, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    return im.convert("RGB")


def _save_gif(images, out, fps):
    images[0].save(out, save_all=True, append_images=images[1:],
                   duration=int(1000 / fps), loop=0)


def cmd_preview(frames_dir, spec, fps, out):
    frames = list_frames(frames_dir)
    by_num = dict(frames)
    nums = parse_spec(spec, by_num.keys())
    images = [_gif_ready(Image.open(by_num[n])) for n in nums]
    _save_gif(images, out, fps)
    print(f"完成: {len(images)} 帧 -> {os.path.abspath(out)} (fps={fps})")


def _small_gray_arrays(frames, height=96):
    """全部帧缩成等比小灰度图（numpy float32 数组），用于快速相似度计算。"""
    arrays = []
    for _, path in frames:
        im = Image.open(path).convert("L")
        w = max(int(im.width * height / im.height), 1)
        arrays.append(np.asarray(im.resize((w, height)), dtype=np.float32))
    return np.stack(arrays)


def find_loop(arrays, min_t, max_t):
    """在帧序列里找最佳循环段。

    周期: 枚举 T ∈ [min_t, max_t]，"帧i vs 帧i+T"平均差异最小的 T 为动作周期
          （最小差异 15% 以内取最小的 T，避免选中倍数周期 2T/3T）。
    起点: 在该周期下取接缝差异（帧s vs 帧s+T）最小的 s。
    返回 None 表示帧数不足以在指定范围内搜索。
    """
    n = len(arrays)
    max_t = min(max_t, n - 1)
    if max_t < min_t:
        return None
    ranking = sorted(
        (float(np.abs(arrays[:-t] - arrays[t:]).mean()), t)
        for t in range(min_t, max_t + 1)
    )
    best = ranking[0][0]
    period = min(t for score, t in ranking if score <= best * 1.15)
    seams = np.abs(arrays[:-period] - arrays[period:]).mean(axis=(1, 2))
    start = int(seams.argmin())
    return {
        "period": period, "start": start, "seam": float(seams[start]),
        "adj_avg": float(np.abs(arrays[:-1] - arrays[1:]).mean()),
        "period_score": best,
        "baseline": float(np.mean([s for s, _ in ranking])),
        "ranking": ranking[:5],
    }


def detect_dups(adj_diffs):
    """检测规律性重复/混合帧（帧率转换每 g 帧插入 1 帧，如 18fps 拉成 24fps）。

    相邻帧差异序列在低差异点的间隔呈固定周期时判定存在该模式，
    返回 (间隔 gap, 低差异帧约数) 或 None。gap=4 表示约每 4 帧有 1 帧冗余。
    """
    d = np.asarray(adj_diffs, dtype=np.float32)
    n = len(d)
    if n < 12:
        return None
    best = None
    for g in range(2, 9):
        nb = n // g
        if nb < 3:
            break
        blocks = d[: nb * g].reshape(nb, g)
        mins = blocks.argmin(axis=1)          # 每块内差异最小的位置
        offset, cnt = Counter(mins.tolist()).most_common(1)[0]
        low = blocks[:, offset].mean()
        other = (blocks.sum() - blocks[:, offset].sum()) / (nb * (g - 1))
        # 低点位置要足够一致，且明显低于同块其他位置，才算规律插入帧
        if cnt >= nb * 0.7 and other > 0 and low < 0.6 * other:
            score = low / other
            if best is None or score < best[0]:
                best = (score, g, nb)
    if best is None:
        return None
    _, g, nb = best
    return g, nb


def classify_inserted_frames(adj_diffs, gap):
    """已确认存在"每 gap 帧 1 插入帧"模式后，逐帧定位插入帧（相位锁定 + ±1 窗口漂移）。

    返回的索引都是 0 基过渡索引 i，表示 frames[i]→frames[i+1] 这个过渡，
    插入/重复帧是其中的后一帧 frames[i+1]。分档：
      blend   diff < 0.6*中位数        -> 确认的混合帧
      suspect 0.6~0.8*中位数           -> 疑似混合帧（动作快时混合帧差异会变大）
    相位预期位置上两档都不满足时记为 missing（该处模式中断）。
    """
    d = np.asarray(adj_diffs, dtype=np.float32)
    med = float(np.median(d)) or 1.0
    phase = int(min(range(gap), key=lambda o: d[o::gap].mean()))
    blend, suspect, missing = [], [], []
    for i in range(phase, len(d), gap):
        lo, hi = max(i - 1, 0), min(i + 1, len(d) - 1)
        m = lo + int(np.argmin(d[lo:hi + 1]))
        v = float(d[m])
        if v < 0.6 * med:
            blend.append(m)
        elif v < 0.8 * med:
            suspect.append(m)
        else:
            missing.append(i)
    return {"blend": blend, "suspect": suspect, "missing": missing}


def nums_to_spec(nums):
    """[46,47,48,50] -> "46-48,50"，即 preview 帧号语法的逆运算。"""
    parts, start = [], None
    for prev, n in zip([-2] + list(nums), list(nums)):
        if n != prev + 1:
            if start is not None:
                parts.append(str(start) if start == prev else f"{start}-{prev}")
            start = n
    last = nums[-1]
    parts.append(str(start) if start == last else f"{start}-{last}")
    return ",".join(parts)


def save_strip(frames, nums, out, width=240):
    """把循环段的帧拼成单行姿势条（带帧编号），风格同 sheet。"""
    by_num = dict(frames)
    thumbs = []
    for n in nums:
        im = Image.open(by_num[n])
        h = int(im.height * width / im.width)
        im = im.resize((width, h))
        if im.mode == "RGBA":  # 透明帧衬洋红底
            bg = Image.new("RGB", im.size, (255, 0, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        thumbs.append((n, im.convert("RGB")))
    cell_h = thumbs[0][1].height + 18
    strip = Image.new("RGB", (width * len(thumbs), cell_h), (40, 40, 40))
    draw = ImageDraw.Draw(strip)
    for i, (n, im) in enumerate(thumbs):
        strip.paste(im, (i * width, 0))
        draw.text((i * width + 4, im.height + 2), str(n), fill=(255, 255, 0))
    strip.save(out)


def analyze_loop(frames_dir, min_t, max_t, fps, strip, gif):
    """找循环段并产出拼接图/预览 GIF，返回结构化报告（供 CLI 打印和网页接口复用）。"""
    frames = list_frames(frames_dir)
    arrays = _small_gray_arrays(frames)
    info = find_loop(arrays, min_t, max_t)
    if info is None:
        sys.exit(f"帧数太少，无法在 [{min_t}, {max_t}] 范围内搜索循环")
    period, start, seam, adj_avg = info["period"], info["start"], info["seam"], info["adj_avg"]
    nums = [frames[i][0] for i in range(start, start + period)]

    has_period = info["period_score"] <= info["baseline"] * 0.8
    warning = None if has_period else \
        "未检测到明显周期性，给出的是相对最优的一段，素材可能本身不是循环动画"
    ratio = seam / adj_avg if adj_avg else 0
    grade = "优秀，接缝不超过普通相邻帧差异" if ratio <= 1.0 else (
        "良好" if ratio <= 1.5 else "接缝明显大于普通相邻差异，循环可能有跳变，请人工确认拼接图")
    if not has_period:
        grade = grade.rstrip("）") + "，但因无周期性该评分意义有限）"

    adj_diffs = [float(d) for d in np.abs(arrays[:-1] - arrays[1:]).mean(axis=(1, 2))]
    dup = detect_dups(adj_diffs)
    dup_msg = None
    blend_nums, suspect_nums, missing_nums = [], [], []
    clean_nums, clean_spec = None, None
    if dup:
        gap, cnt = dup
        total = len(frames) * (gap - 1) // gap
        dup_msg = (f"检测到规律插入帧: 约每 {gap} 帧有 1 帧重复/混合帧（约 {cnt} 处，"
                   f"帧率转换痕迹），去重后约 {total} 帧")
        if period % gap == 0:
            dup_msg += f"；单个循环内约 {period * (gap - 1) // gap} 个不同姿势"
        cls = classify_inserted_frames(adj_diffs, gap)
        # 过渡索引 i 的插入帧是 frames[i+1]
        blend_nums = [frames[i + 1][0] for i in cls["blend"]]
        suspect_nums = [frames[i + 1][0] for i in cls["suspect"]]
        missing_nums = [frames[i + 1][0] for i in cls["missing"]]
        clean_nums = [n for n in nums if n not in set(blend_nums)]
        if 0 < len(clean_nums) < len(nums):
            clean_spec = nums_to_spec(clean_nums)
    # 近乎完全复制的重复帧（diff < 1.0，与周期模式无关，典型如开头定格）
    dup_nums = [frames[i + 1][0] for i, v in enumerate(adj_diffs)
                if v < 1.0 and frames[i + 1][0] not in set(blend_nums)]

    by_num = dict(frames)
    save_strip(frames, nums, strip)
    _save_gif([_gif_ready(Image.open(by_num[n])) for n in nums], gif, fps)
    return {
        "count": len(frames), "adj_avg": round(adj_avg, 2),
        "has_period": has_period, "warning": warning,
        "period": period, "start_num": nums[0], "end_num": nums[-1],
        "seam": round(seam, 2), "ratio": round(ratio, 2), "grade": grade,
        "ranking": [[t, round(s, 2)] for s, t in info["ranking"]],
        "dup_msg": dup_msg,
        "blend_frames": blend_nums, "suspect_frames": suspect_nums,
        "missing_frames": missing_nums,
        "dup_frames": dup_nums,
        "clean_frames": clean_nums, "clean_spec": clean_spec,
        "fps": fps, "strip": strip, "gif": gif,
    }


def cmd_loop(frames_dir, min_t, max_t, fps, strip, gif):
    info = analyze_loop(frames_dir, min_t, max_t, fps, strip, gif)
    print(f"共 {info['count']} 帧，平均相邻差异 {info['adj_avg']:.2f}")
    if info["warning"]:
        print(f"警告: {info['warning']}")
    print(f"最佳循环: 第 {info['start_num']}-{info['end_num']} 帧，共 {info['period']} 帧，"
          f"接缝差异 {info['seam']:.2f}（{info['grade']}）")
    print("周期候选（T=周期帧数，分数越低姿势越像）:")
    print("  " + "  ".join(f"T={t} {s:.2f}" for t, s in info["ranking"]))
    if info["dup_msg"]:
        print(info["dup_msg"])
        if info["blend_frames"]:
            print(f"  确认混合帧（{len(info['blend_frames'])} 个）: "
                  + ",".join(map(str, info["blend_frames"])))
        if info["suspect_frames"]:
            print(f"  疑似混合帧（{len(info['suspect_frames'])} 个，差异不够低，建议人工确认）: "
                  + ",".join(map(str, info["suspect_frames"])))
        if info["missing_frames"]:
            print(f"  规律位置但未检出低差异（该处模式中断，未计入）: "
                  + ",".join(map(str, info["missing_frames"])))
        if info["clean_spec"]:
            print(f"  循环内剔除确认混合帧后（{len(info['clean_frames'])} 帧）: {info['clean_spec']}")
    if info["dup_frames"]:
        print(f"近乎完全重复的帧（{len(info['dup_frames'])} 个，非周期模式，如开头定格）: "
              + ",".join(map(str, info["dup_frames"])))
    print(f"姿势拼接图已保存 {os.path.abspath(strip)}")
    print(f"循环预览 GIF 已保存 {os.path.abspath(gif)} (fps={fps})")
    print(f"验证没问题后可用: preview {frames_dir} \"{info['start_num']}-{info['end_num']}\" 重新导出")
    if info["clean_spec"]:
        print(f"导出剔除混合帧的循环: preview {frames_dir} \"{info['clean_spec']}\"")


def opt(argv, name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main():
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("sheet", "diff", "preview", "loop"):
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
    elif cmd == "loop":
        cmd_loop(frames_dir, opt(argv, "--min", 4, int), opt(argv, "--max", 60, int),
                 opt(argv, "--fps", 18, int),
                 opt(argv, "--strip", default_out("loop_strip.png")),
                 opt(argv, "--gif", default_out("loop_preview.gif")))
    else:
        if len(argv) < 3:
            sys.exit("preview 需要帧号参数，如: preview 帧目录 \"1-10,15\"")
        cmd_preview(frames_dir, argv[2], opt(argv, "--fps", 12, int),
                    opt(argv, "-o", default_out("preview.gif")))


if __name__ == "__main__":
    main()
