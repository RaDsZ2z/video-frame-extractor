# 视频序列帧提取工具

从视频生成到序列帧动画的完整流水线：先用视频生成模型以"参考图 + 提示词"生成绿幕视频，再抽成 PNG 帧序列（支持绿幕抠图），辅助挑选关键帧并预览动画效果，最终得到按顺序编号的透明底 PNG 帧序列，可直接导入任意引擎或工具使用。

提供网页界面和命令行两种使用形式，二者是同一套工具、共用同一套目录。

## 环境准备

只需要 Python（3.10+），依赖清单见 `requirements.txt`（imageio-ffmpeg / pillow / numpy / scipy），ffmpeg 由 `imageio-ffmpeg` 包内置提供，无需单独安装：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux
```

## 使用

详细文档见 [USAGE.md](USAGE.md)，分两部分：第一部分面向使用者（流程与网页界面操作），第二部分面向 AI / 自动化（目录、命令行与 HTTP 接口约定）。
