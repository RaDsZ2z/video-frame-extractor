# 视频序列帧提取工具

把 mp4 视频抽成 PNG 帧序列（支持绿幕抠图），辅助挑选关键帧并预览动画效果，最终把选中的 PNG 导入 Godot 4.x 制作序列帧动画（SpriteFrames）。

## 环境准备

只需要 Python（3.10+）和两份依赖，ffmpeg 由 `imageio-ffmpeg` 包内置提供，无需单独安装：

```bash
python -m venv .venv
.venv/Scripts/pip install imageio-ffmpeg pillow numpy scipy      # Windows
# .venv/bin/pip install imageio-ffmpeg pillow numpy scipy        # macOS/Linux
```

下文命令均用 Windows 写法 `.venv/Scripts/python`，macOS/Linux 换成 `.venv/bin/python`。

## 方式一：网页界面（推荐）

```bash
.venv/Scripts/python server.py
```

Windows 下也可以直接双击 `启动网页版.bat`。

启动后自动打开浏览器（默认 <http://127.0.0.1:8765>，`--port` 可改端口），页面上按三步操作：

1. **上传视频并抽帧** — 选择 mp4，绿幕视频勾选"绿幕抠图"（可调整幕布颜色、容差、柔化），点击开始抽帧
2. **挑帧** — 抽完自动显示全部帧的缩略图网格，点击缩略图选中/取消；可用"生成总览拼图"看大图，用"帧差异分析"看静止/剧烈区段辅助判断
3. **预览动画** — 设定帧率，生成预览 GIF 确认效果

满意后到 `workspace/frames/` 目录，把选中的 `frame_XXXXX.png` 拖进 Godot 的 SpriteFrames 即可。

> 网页版的中间产物都在 `workspace/` 下（上传的视频、帧、拼图、GIF），可随时整个删除。

## 方式二：命令行

### 1. 抽帧 `extract_frames.py`

```bash
# 普通视频
.venv/Scripts/python extract_frames.py 视频.mp4

# 绿幕视频（背景转透明 PNG）
.venv/Scripts/python extract_frames.py 视频.mp4 --green

# 白幕/灰幕视频（自动改用 colorkey，无需额外参数）
.venv/Scripts/python extract_frames.py 视频.mp4 --green --color 0xFFFFFF

# 抠图效果不理想时调参数
.venv/Scripts/python extract_frames.py 视频.mp4 --green --color 0x65AC64 --similarity 0.05 --blend 0.02
```

- 默认输出到 `output/<视频名>/frames/`（也可在视频名后加第二个参数自定义目录），
  文件名为 `frame_00001.png` 起顺序编号
- `--color`：幕布真实颜色（建议用取色器从视频画面里取，实际绿幕往往不
  是纯绿）
- `--similarity`：容差，建议 0.03~0.1。**注意 ffmpeg 的容差很敏感，0.15
  以上基本会把主体一起抠掉**；绿边残留小幅调大、误抠主体调小
- `--blend`：边缘柔化（默认 0.02）
- 幕布有彩色（绿幕等）时用 chromakey 抠色度 + 去绿色溢边；幕布是灰白黑
  等无彩色时自动改用 colorkey 按 RGB 距离抠
- 抠图后默认做"孔洞填补"：不与图像边缘连通的透明区域恢复不透明，保护
  主体上的亮色部位（如白色眼睛、高光）不被误抠成洞；不需要可加 `--no-fill`

### 2. 挑帧辅助 `frame_tools.py`

```bash
# 总览拼图：所有帧拼成带编号的大图
.venv/Scripts/python frame_tools.py sheet output/视频名/frames --cols 5 --width 240

# 帧差异分析：找出静止区段（可删冗余）和剧烈动作位置（建议保留），末列为循环接缝
.venv/Scripts/python frame_tools.py diff output/视频名/frames

# 选中帧预览 GIF
.venv/Scripts/python frame_tools.py preview output/视频名/frames "1-10,15,20-30:2" --fps 12
```

- 三个子命令的产物（contact_sheet.png / diff_chart.png / frame_diffs.csv /
  preview.gif）默认都写到帧目录的上一级，即 `output/<视频名>/` 下，可用
  `-o` / `--chart` 自定义

帧号写法：单帧 `5`，区间 `1-10`，带步长区间 `1-30:3`，逗号混用 `1-10,15,20-30:2`。

## 导入 Godot（4.x）

1. 把选中的 PNG 拷进 Godot 项目目录
2. 场景中新建 `AnimatedSprite2D`，在 SpriteFrames 面板里"从文件添加帧"，多选这些 PNG（按文件名排序即正确播放顺序）
3. 设置动画 FPS（可用预览 GIF 时的帧率作参考），勾选循环

## 文件说明

| 文件 | 作用 |
|---|---|
| `extract_frames.py` | 抽帧 CLI（ffmpeg 抽帧 + chromakey/colorkey 抠图 + 孔洞填补） |
| `frame_tools.py` | 挑帧辅助 CLI（总览拼图 / 差异分析 / 预览 GIF） |
| `server.py` / `index.html` | 本地网页界面，整合以上全部功能 |
| `启动网页版.bat` | Windows 双击启动网页版 |
| `output/` | 所有产出，按视频名分目录（frames/ + 拼图 + 差异图 + CSV + 预览 GIF） |
| `workspace/` | 网页版运行时的中间产物目录，可随时删除 |

## 提示

- 抠图有问题（绿边、误抠）时，先重跑抽帧调 `--similarity`，别在坏帧上挑
- 视频帧率很高时（30/60fps），相邻帧往往高度重复，先跑 `diff` 看静止区段，或预览时用大步长（如 `1-120:4`）粗选再细挑
- 透明帧在总览拼图和预览 GIF 中会衬洋红色背景，方便检查抠图效果；实际 PNG 是透明底，不影响 Godot 使用
