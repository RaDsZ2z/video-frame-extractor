# 视频序列帧提取工具

从视频生成到序列帧动画的完整流水线：先用视频生成模型（默认 MiniMax H3）以"参考图 + 提示词"生成绿幕视频，再抽成 PNG 帧序列（支持绿幕抠图），辅助挑选关键帧并预览动画效果，最终得到按顺序编号的透明底 PNG 帧序列，可直接导入任意引擎或工具使用。

## 环境准备

只需要 Python（3.10+），依赖清单见 `requirements.txt`（imageio-ffmpeg / pillow / numpy / scipy），ffmpeg 由 `imageio-ffmpeg` 包内置提供，无需单独安装：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux
```

下文命令均用 Windows 写法 `.venv/Scripts/python`，macOS/Linux 换成 `.venv/bin/python`。

## 第一步：生成与收纳视频

流水线从"参考图 + 提示词 → 视频"开始。默认用 MiniMax H3 的视频生成（网页版即可，不需要 API Key）。

### 网页生成（MiniMax H3）

1. 打开 MiniMax 开放平台网页端并登录，进入视频生成（H3）界面
2. 上传参考图（绿幕角色图），填入提示词（用下面的模板）
3. 参数建议：时长按一个完整动作循环取（走路常用 5 秒）；画面比例按最终用途（角色动画常见 16:9 或 1:1）；画质选最高；具体选项以网页实际为准
4. 生成后**先在视频层面验收**（见下方清单），不满意就换提示词/参数重生成，**不必抽帧**
5. 满意后下载 mp4，用 `src\ingest_video.py` 收纳进项目：

```bash
.venv/Scripts/python src\ingest_video.py 下载的.mp4 --name 走路循环 --open
```

- 不写 `--name` 就用源文件名；`--move` 表示移动而非复制；`--open` 收纳后自动打开视频预览；`--list` 查看已收纳视频
- 收纳后视频位于 `input/`（该目录不入库 git）

### 提示词模板（绿幕角色循环动画）

```text
参考图保持角色形象不变，角色在纯绿色背景前原地循环{动作}，
动作自然流畅、节奏均匀，首尾帧无缝衔接可循环播放，
固定镜头无运镜，绿幕背景纯净无杂物，全身入镜，光线均匀无阴影
```

`{动作}` 示例：走路、跑步、待机呼吸、攻击挥砍。

要点：**首尾帧衔接**是循环动画的关键（网页有循环选项务必开启）；**固定镜头无运镜**防止角色漂移导致滑步；**绿幕纯净均匀**决定抠图质量。

### 视频级验收清单（决定是否进入抽帧）

- 动作自然：走姿不僵硬、无滑步漂移、肢体无崩坏
- 循环接缝：循环播放时开头结尾看不出跳变
- 主体完整：脸/手/服饰无变形闪烁
- 绿幕干净：背景无杂物、颜色均匀、无明显阴影
- 时长充足：覆盖一个完整动作周期

全部通过 → 进入抽帧；任一不合格 → 回生成平台调整提示词/参数重来（别在坏视频上浪费抽帧时间）。

## 方式一：网页界面（推荐）

```bash
.venv/Scripts/python src\server.py
```

Windows 下也可以直接双击 `启动网页版.bat`。

启动后自动打开浏览器（默认 <http://127.0.0.1:8765>，`--port` 可改端口），页面上按三步操作：

1. **选择视频并抽帧** — 上传新 mp4（自动收纳进 `input/`，与 `ingest_video.py` 同一套命名规则），或直接选择 `input/` 里已有的视频；绿幕视频勾选"绿幕抠图"（可调整幕布颜色、容差、柔化），点击开始抽帧
2. **挑帧** — 抽完自动显示全部帧的缩略图网格，点击缩略图选中/取消；可用"生成总览拼图"看大图，用"帧差异分析"看静止/剧烈区段辅助判断；之前抽过的项目可从"打开项目"下拉框直接载入
3. **预览动画** — 设定帧率，生成预览 GIF 确认效果

满意后到 `output/<视频名>/frames/` 目录取选中的 `frame_XXXXX.png`（按文件名排序即正确播放顺序），导入你的引擎或项目即可。

> 网页版与命令行是同一套工具、共用同一套目录：视频都在 `input/`，产出都按视频名放在 `output/<视频名>/`，两种方式的中间结果互相可见、可接续使用。

## 方式二：命令行

### 1. 抽帧 `src\extract_frames.py`

```bash
# 普通视频
.venv/Scripts/python src\extract_frames.py 视频.mp4

# 绿幕视频（背景转透明 PNG）
.venv/Scripts/python src\extract_frames.py 视频.mp4 --green

# 白幕/灰幕视频（自动改用 colorkey，无需额外参数）
.venv/Scripts/python src\extract_frames.py 视频.mp4 --green --color 0xFFFFFF

# 抠图效果不理想时调参数
.venv/Scripts/python src\extract_frames.py 视频.mp4 --green --color 0x65AC64 --similarity 0.05 --blend 0.02
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

### 2. 挑帧辅助 `src\frame_tools.py`

```bash
# 总览拼图：所有帧拼成带编号的大图
.venv/Scripts/python src\frame_tools.py sheet output/视频名/frames --cols 5 --width 240

# 帧差异分析：找出静止区段（可删冗余）和剧烈动作位置（建议保留），末列为循环接缝
.venv/Scripts/python src\frame_tools.py diff output/视频名/frames

# 选中帧预览 GIF
.venv/Scripts/python src\frame_tools.py preview output/视频名/frames "1-10,15,20-30:2" --fps 12
```

- 三个子命令的产物（contact_sheet.png / diff_chart.png / frame_diffs.csv /
  preview.gif）默认都写到帧目录的上一级，即 `output/<视频名>/` 下，可用
  `-o` / `--chart` 自定义

帧号写法：单帧 `5`，区间 `1-10`，带步长区间 `1-30:3`，逗号混用 `1-10,15,20-30:2`。

## 文件说明

| 文件 | 作用 |
|---|---|
| `src/` | 全部脚本与网页界面（代码目录，不散落在根目录） |
| `src/ingest_video.py` | 流水线第一步：收纳网页下载的生成视频进 `input/`，统一命名并提示下一步 |
| `src/extract_frames.py` | 抽帧 CLI（ffmpeg 抽帧 + chromakey/colorkey 抠图 + 孔洞填补） |
| `src/frame_tools.py` | 挑帧辅助 CLI（总览拼图 / 差异分析 / 预览 GIF） |
| `src/server.py` / `src/index.html` | 本地网页界面，整合以上全部功能（与命令行共用 `input/` 和 `output/`） |
| `启动网页版.bat` | Windows 双击启动网页版 |
| `requirements.txt` | Python 依赖清单，`pip install -r requirements.txt` 一键安装 |
| `input/` | 待处理的源视频目录（命令行收纳与网页上传都进这里，不入库 git） |
| `output/` | 所有产出，按视频名分目录（frames/ + 拼图 + 差异图 + CSV + 预览 GIF） |

## 提示

- 生成的视频效果差（动作崩坏、循环不接、绿幕脏）时直接回生成平台调整重试，不必抽帧；抠图质量（绿边、误抠）要抽帧后才能看出
- 抠图有问题（绿边、误抠）时，先重跑抽帧调 `--similarity`，别在坏帧上挑
- 视频帧率很高时（30/60fps），相邻帧往往高度重复，先跑 `diff` 看静止区段，或预览时用大步长（如 `1-120:4`）粗选再细挑
- 透明帧在总览拼图和预览 GIF 中会衬洋红色背景，方便检查抠图效果；实际 PNG 是透明底，不影响正常使用
