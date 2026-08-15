# 视频序列帧提取工具

从视频生成到序列帧动画的完整流水线：先用视频生成模型以"参考图 + 提示词"生成绿幕视频，再抽成 PNG 帧序列（支持绿幕抠图），辅助挑选关键帧并预览动画效果，最终得到按顺序编号的透明底 PNG 帧序列，可直接导入任意引擎或工具使用。

提供网页界面和命令行两种使用形式，二者是同一套工具、共用同一套目录。

## 功能特性

- **抽帧抠图**：ffmpeg 抽帧，绿幕/白幕等纯色背景一键抠成透明 PNG（chromakey/colorkey 自动切换，孔洞填补保护主体亮色部位）
- **挑帧辅助**：带帧编号的总览拼图、帧差异分析（找静止/剧烈区段）、选中帧预览 GIF
- **自动找循环**：自动识别动作周期和最佳循环段，输出接缝评分与循环预览；能检测帧率转换产生的重复/混合帧并给出去重建议
- **网页界面**：上传视频 → 抽帧 → 点选帧 → 预览，全程浏览器操作；另提供 HTTP 接口供 AI / 自动化调用

## 环境准备

只需要 Python（3.10+），依赖清单见 `requirements.txt`（imageio-ffmpeg / pillow / numpy / scipy），ffmpeg 由 `imageio-ffmpeg` 包内置提供，无需单独安装：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux
```

## 快速开始

1. 把 mp4 放进 `input/` 目录
2. 双击 `启动网页版.bat`（等价于 `.venv/Scripts/python src/server.py`），浏览器里按"抽帧 → 挑帧 → 预览"三步操作
3. 产物都在 `output/<视频名>/` 下，最终交付 `frames/` 里选中的 PNG

命令行示例：

```bash
.venv/Scripts/python src/extract_frames.py input/奔跑.mp4 --green   # 抽帧 + 绿幕抠图
.venv/Scripts/python src/frame_tools.py loop output/奔跑/frames      # 自动找循环段
```

## 使用

详细文档见 [USAGE.md](USAGE.md)，分两部分：第一部分面向使用者（流程与网页界面操作），第二部分面向 AI / 自动化（目录、命令行与 HTTP 接口约定）。
