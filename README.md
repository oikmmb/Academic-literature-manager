<div align="center">

# 📚 文献管家（LitManager）

**本地优先的学术文献管理桌面应用 —— 文献管理 · 细粒度批注 · AI 辅助阅读**

A local-first academic literature manager: annotation at word level, AI-powered reading, mind mapping, and more.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)]()
[![Tests](https://img.shields.io/badge/Tests-73%20passed-brightgreen.svg)]()

</div>

## ✨ 功能特性

### 📄 文献管理
- **PDF 导入**：拖入自动提取标题 / 作者 / DOI / 摘要，Crossref 联网补全元数据
- **四种分类维度**：发表时间 / 文献主题 / 第一作者 / 通讯作者，支持搜索与排序
- **补充材料**：正文与 SI / 附录独立管理，阅读器侧边栏一键切换
- **多文献同开**：顶部标签页切换，支持**双文献并排对比**（可拖分隔条）
- **数据本地化**：全部数据存本机（默认 F:\论文\data，可自定义），卸载重装不丢失

### ✍️ 细粒度批注
- 选中一个词 / 一句话 / 一段话即可添加笔记或高亮（4 色 + 透明度可调）
- **跨页选词**：自动排除页眉页脚，只保留正文
- **多段选区**：Shift + 拖动累积多段非连续选择（可跨页）
- 批注 800ms 防抖自动保存，退出强制落盘，崩溃也有兜底
- 重开文献锚定 100% 稳定（词级锚点 + PDF 内容指纹）

### 🤖 AI 辅助
- **AI 问答窗口**：多轮对话，选词问 / 框选截图问（多模态），支持 DeepSeek 及任意 OpenAI 兼容接口（GPT-4o / Qwen-VL / GLM-4V 等）
- **AI 思维导图**：一键梳理全文要点生成可编辑导图，节点可拖拽、画布无限缩放平移
- **划词翻译**：DeepSeek / 有道智云 / 百度翻译三提供商切换，本地缓存省费用
- **参考文献悬停**：鼠标停在正文 `[88]` 引用上 2 秒弹出对应条目，支持 `[88]-[90]` 范围

### 🔍 图片匹配
- 粘贴论文截图 / 拖入图片 → OCR 识别 → 本地库模糊匹配 Top3
- 未命中可联网 Crossref 补录为新文献

## 📦 安装

### 方式一：一键安装包（推荐）

从 [Releases](../../releases) 下载 `LitManager-Setup.exe`，双击安装。免管理员权限，自动创建桌面与开始菜单快捷方式，支持控制面板卸载。

> 注意：安装包未做商业代码签名，Windows SmartScreen 会提示"无法确认发布者"，点「更多信息 → 仍要运行」即可。

### 方式二：源码运行

```bat
git clone <repo-url>
cd lit-manager
python -m venv server\venv
server\venv\Scripts\pip install -r server\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
start.bat          :: 桌面窗口模式
```

### 构建安装包

```bat
build_exe.bat      :: PyInstaller 打包 + Inno Setup 编译 LitManager-Setup.exe
sign.ps1           :: （可选）签名安装包（需自备证书 cert.pfx）
```

## 🚀 快速上手

1. **导入文献**：文献库页 →「＋ 导入文献」→ 拖入 PDF → 确认元数据（可附补充材料）
2. **阅读批注**：选中文字 → 工具条：色板=高亮、✍=笔记、译=翻译、💬=问 AI；Shift+拖动=多段选择
3. **AI 功能**：先在「⚙ 设置」配置 DeepSeek Key（平台注册即得）或自定义 OpenAI 兼容接口
4. **图片匹配**：文献库页 →「🔍 图片匹配」→ Ctrl+V 粘贴截图
5. **导图**：阅读器 →「🧠 导图」→ AI 生成或手动搭建 → 左键拖节点、左键拖空白移动画布、Ctrl+滚轮缩放

## 🏗 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 · SQLite(WAL) |
| PDF | PyMuPDF（页渲染 + 词级文本层锚定） |
| OCR | RapidOCR（onnxruntime） |
| 前端 | 原生 JS（无框架无 CDN）· 词级 span 选区引擎 |
| 桌面 | pywebview（WebView2）· PyInstaller · Inno Setup |

**核心设计**：阅读器不用 PDF.js —— PyMuPDF 渲染页图 + 词级坐标层，注释锚点 `{页码, 词区间}` 与渲染解耦，重开 100% 稳定；扫描版 PDF 自动降级为页级笔记。

## 📁 项目结构

```
lit-manager/
├── server/
│   ├── app/
│   │   ├── main.py          # FastAPI 装配（含存量库迁移）
│   │   ├── models.py        # papers / annotations / supplements / mindmap / chat / references
│   │   ├── routers/         # papers reader annotations imports supplements
│   │   │                    # translate ocr mindmap chat refs crossref
│   │   └── services/        # pdf ocr matcher crossref translate chat_ai mindmap_ai refs
│   ├── tests/               # pytest，73 个测试
│   └── scripts/api_smoke.py # 端到端冒烟
├── web/                     # 前端静态页（原生 JS）
│   ├── index / reader / reader-host / import / match / settings
│   └── js/                  # reader(选区引擎) mindmap chat refs-tip 等
├── models/                  # OCR 模型（构建时收集，不入库）
├── start.py / start.bat     # 一键启动
├── build_exe.bat            # 构建 + 安装包编译
├── installer.iss            # Inno Setup 脚本
└── sign.ps1 / sign_all.ps1  # 签名脚本
```

## 🧪 测试

```bat
cd server
venv\Scripts\python -m pytest tests -q          :: 单元/接口测试（73 个）
venv\Scripts\python scripts\api_smoke.py        :: 对运行中服务的端到端冒烟
```

## ⚖️ 许可证与第三方

本项目代码以 **MIT 许可证** 发布（见 [LICENSE](LICENSE)）。

**依赖许可注意**：

- **PyMuPDF 为 AGPL-3.0 协议**：若你在闭源商业产品中分发本软件，需遵守 AGPL 条款（整体开源）或向 Artifex 购买商业许可。仅个人/内部/开源使用无碍
- 其余主要依赖均为宽松协议：FastAPI / SQLAlchemy / onnxruntime / rapidfuzz（MIT）、RapidOCR / OpenCV（Apache-2.0）、httpx（BSD）
- AI 功能（翻译 / 问答 / 导图）需用户自备第三方 API 凭据，本项目不收集、不上传任何用户数据

## 🙏 致谢

- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF 渲染与文本提取
- [RapidOCR](https://github.com/RapidAI/RapidOCR) — OCR 引擎
- [DeepSeek](https://platform.deepseek.com) — 默认 AI 模型

## ⚠️ 免责声明

本软件仅用于文献管理与学习辅助。AI 生成内容仅供参考，请以原文为准。
