# Markdown 转 PDF 工具 — 系统设计文档

| 字段     | 内容                    |
| -------- | ----------------------- |
| 文档版本 | v1.0                    |
| 创建日期 | 2026-03-30              |
| 状态     | 草稿                    |
| 参考文档 | `CRD/crd.md` v1.0       |

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术选型与方案论证](#2-技术选型与方案论证)
3. [系统架构设计](#3-系统架构设计)
4. [模块详细设计](#4-模块详细设计)
5. [数据流程设计](#5-数据流程设计)
6. [配置体系设计](#6-配置体系设计)
7. [CLI 接口设计](#7-cli-接口设计)
8. [错误处理设计](#8-错误处理设计)
9. [样式与排版设计](#9-样式与排版设计)
10. [项目目录结构](#10-项目目录结构)
11. [依赖清单](#11-依赖清单)
12. [非功能性需求实现方案](#12-非功能性需求实现方案)
13. [开发里程碑](#13-开发里程碑)

---

## 1. 系统概述

### 1.1 目标

开发一款基于 Python 的命令行工具，将包含表格、代码块、PlantUML/Mermaid 图表的 Markdown 技术文档，通过"**Markdown → HTML（中间态）→ PDF**"的转换管道，输出格式完整、图表可视、适合归档与打印的单文件 PDF。

### 1.2 核心转换思路

```
.md 文件
   │
   ▼
[1] 解析层：提取 YAML Front Matter + 解析 Markdown 语法树
   │
   ▼
[2] 渲染层：图表渲染（PlantUML / Mermaid）+ 代码高亮（Pygments）
   │
   ▼
[3] 组装层：将渲染结果注入 HTML 模板 + 注入 CSS 样式
   │
   ▼
[4] 输出层：HTML → PDF（WeasyPrint） → 预览 / 保存
```

**选择 HTML 作为中间态**的原因：
- HTML + CSS 是最成熟的富文本排版描述体系，可精确控制字体、颜色、表格边框、分页等。
- `WeasyPrint` 可将标准 HTML/CSS 高质量转换为 PDF，无需外部二进制工具。
- 调试和样式定制均可在浏览器中直接验证，降低排查难度。

---

## 2. 技术选型与方案论证

### 2.1 Markdown 解析

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **Python-Markdown** | 成熟稳定，扩展体系完整（tables、fenced_code、codehilite、meta） | 速度略慢 | ✅ **采用** |
| mistune | 速度极快，AST 可扩展 | 扩展生态不如 Python-Markdown | 备选 |
| pandoc（外部） | 功能最全 | 需额外安装，难以嵌入 Python 流程 | ❌ 排除 |

**决策**：采用 `python-markdown`，启用扩展：`tables`、`fenced_code`、`codehilite`、`meta`、`toc`、`attr_list`。

### 2.2 代码语法高亮

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **Pygments** | 与 Python-Markdown `codehilite` 原生集成，支持 500+ 语言 | — | ✅ **采用** |
| highlight.js | 前端方案，效果好 | 需要 JS 运行时，WeasyPrint 不执行 JS | ❌ 排除 |

**决策**：使用 Pygments，通过 `codehilite` 扩展在解析阶段生成带 CSS 类名的 HTML，样式以内联 CSS 注入。

### 2.3 PlantUML 渲染

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **本地 JAR**（`java -jar plantuml.jar`） | 离线，速度快，功能最全 | 需要 JRE + 下载 JAR | ✅ **主要方案** |
| PlantUML 在线服务（`plantuml.com`） | 无需本地依赖 | 依赖网络，存在信息安全风险 | ✅ **备用方案** |
| `plantuml` Python 库 | Python 封装 | 底层仍依赖 JAR | 辅助封装 |

**决策**：两种模式均支持，通过配置文件切换；默认优先使用本地 JAR，JAR 不可用时降级到在线服务。

### 2.4 Mermaid 渲染

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **`mermaid-py` + Puppeteer** | 本地渲染，质量高 | 需要 Node.js + Chromium | ✅ **主要方案** |
| **Mermaid.ink API** | 无需本地依赖 | 依赖网络 | ✅ **备用方案** |
| `@mermaid-js/mermaid-cli`（mmdc） | 官方工具，效果最佳 | 需要 Node.js 环境 | 同主要方案统一处理 |

**决策**：本地优先调用 `mmdc`（Node.js 运行时）；若 Node.js 不可用，则调用 `mermaid.ink` 在线接口。两种模式均可在配置文件中强制指定。

### 2.5 HTML → PDF 转换

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **WeasyPrint** | 纯 Python，CSS3 支持优秀，CJK 友好，维护活跃 | 对 JS 不执行（已在上游处理完毕，不影响本项目） | ✅ **采用** |
| pdfkit + wkhtmltopdf | 渲染效果接近浏览器 | wkhtmltopdf 已停止维护，Windows 安装繁琐 | ❌ 排除 |
| reportlab | 完全可编程 | 需手动处理所有排版逻辑，开发成本极高 | ❌ 排除 |
| xhtml2pdf | 轻量 | CSS 支持有限，CJK 渲染较差 | ❌ 排除 |

**决策**：采用 `WeasyPrint`，配合 `cairocffi` 提供图形后端。Windows 下需安装 GTK 运行时（通过官方安装包一键完成）。

### 2.6 预览功能

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **生成临时 PDF + 系统默认查看器** | 零依赖，Windows 原生支持，所见即所得 | 预览与主程序解耦，无法内嵌 | ✅ **MVP 方案** |
| tkinter + PDF 渲染库（如 `pymupdf`） | 内嵌 GUI，交互更丰富 | 开发成本较高，为可选需求 | ✅ **增强方案（后期迭代）** |

**决策**：MVP 使用 `os.startfile()` 打开临时 PDF；后期可扩展为 tkinter + `PyMuPDF` 的内嵌预览窗口。

### 2.7 配置与 CLI

| 职责 | 选型 | 理由 |
|------|------|------|
| CLI 框架 | `click` | API 简洁，自动生成帮助信息，支持子命令扩展 |
| YAML 解析 | `PyYAML` | 标准库，解析 Front Matter 及外部配置文件 |
| Front Matter 提取 | `python-frontmatter` | 专门处理 Markdown 文件头的 YAML 元数据 |

---

## 3. 系统架构设计

### 3.1 分层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLI 入口层（main.py）                      │
│              click CLI → 参数校验 → 分发至 Pipeline              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                       配置层（Config Layer）                      │
│   default_config.yaml ← config.yaml ← Front Matter ← CLI args   │
│                 （优先级从低到高，逐层覆盖）                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    核心处理管道（Core Pipeline）                   │
│                                                                   │
│  ┌──────────┐   ┌───────────────────────────────────────────┐    │
│  │  Parser  │   │              Renderer（渲染层）             │    │
│  │ 解析层   │──▶│  PlantUMLRenderer  MermaidRenderer         │    │
│  │          │   │  CodeHighlighter   (Pygments)              │    │
│  └──────────┘   └───────────────────────────────────────────┘    │
│        │                          │                              │
│        └──────────────┬───────────┘                              │
│                       ▼                                          │
│              ┌──────────────────┐                                │
│              │   Assembler      │                                │
│              │  HTML 组装层     │                                │
│              │  CSS 注入 / 模板 │                                │
│              └────────┬─────────┘                                │
│                       │                                          │
│              ┌────────▼─────────┐                                │
│              │  PDFGenerator    │                                │
│              │  WeasyPrint      │                                │
│              └────────┬─────────┘                                │
│                       │                                          │
│              ┌────────▼─────────┐   ┌──────────────────┐        │
│              │   Previewer      │──▶│  系统 PDF 查看器  │        │
│              │  (可选预览)      │   │  os.startfile()  │        │
│              └────────┬─────────┘   └──────────────────┘        │
│                       │                                          │
│              ┌────────▼─────────┐                                │
│              │   FileOutput     │                                │
│              │   最终 PDF 保存  │                                │
│              └──────────────────┘                                │
└──────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    横切关注点（Cross-Cutting）                     │
│          Logger（日志）  ErrorHandler（错误处理）                  │
│          TempManager（临时文件管理）  FileUtils（文件工具）        │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 关键设计原则

1. **管道模式（Pipeline Pattern）**：各处理阶段职责单一，前一阶段输出是后一阶段输入，便于测试与替换。
2. **策略模式（Strategy Pattern）**：图表渲染器（PlantUML/Mermaid）抽象为统一接口 `DiagramRenderer`，本地/在线模式通过策略类切换，对上层透明。
3. **降级容错（Graceful Degradation）**：任意图表渲染失败时，降级保留原始代码块文本，不中断整体转换流程。
4. **配置分层覆盖**：默认配置 → 用户配置文件 → Front Matter → CLI 参数，优先级逐层升高。

---

## 4. 模块详细设计

### 4.1 `core/parser.py` — 解析模块

**职责**：读取 `.md` 文件，提取 YAML Front Matter，将 Markdown 正文转换为 HTML（含占位符）。

**接口**：
```python
class MarkdownParser:
    def parse(self, filepath: str) -> ParseResult:
        """
        返回 ParseResult：
          - metadata: dict          # YAML Front Matter 键值对
          - html_body: str          # 经 Python-Markdown 转换的 HTML（图表块为占位符）
          - diagrams: list[Diagram] # 识别出的图表对象列表
        """
```

**处理细节**：
- 使用 `python-frontmatter` 分离 Front Matter 与正文。
- 注册自定义 Markdown 扩展 `DiagramExtension`，在 fenced_code 处理阶段拦截 `plantuml` 和 `mermaid` 代码块，替换为 `<div class="diagram-placeholder" data-id="uuid">` 占位符，并将原始代码存入 `diagrams` 列表。
- 其余 fenced_code 块（非图表）交由 `codehilite`（Pygments）处理。

**关键扩展机制**：

```
Markdown 源码
   │
   ▼ FencedCodeExtension（改造版）
   │
   ├── lang in {plantuml, mermaid} → 写入 diagrams 列表，输出占位 div
   └── lang 为其他           → Pygments 高亮，输出 <div class="highlight">
```

---

### 4.2 `core/renderer/base.py` — 渲染器基类

```python
from abc import ABC, abstractmethod

class DiagramRenderer(ABC):
    @abstractmethod
    def render(self, code: str, diagram_type: str) -> RenderResult:
        """
        返回 RenderResult：
          - success: bool
          - image_data: bytes | None  # PNG/SVG 二进制
          - image_format: str         # "png" | "svg"
          - error_message: str | None
        """
```

---

### 4.3 `core/renderer/plantuml_renderer.py` — PlantUML 渲染器

**策略一：本地 JAR 模式**
```
render(code) → 写入临时 .puml 文件
             → subprocess: java -jar plantuml.jar -tpng <file>
             → 读取输出 PNG → 返回 image_data
```

**策略二：在线服务模式**
```
render(code) → 对代码进行 deflate 压缩 + base64url 编码
             → GET http://www.plantuml.com/plantuml/png/<encoded>
             → 返回响应体（PNG 二进制）
```

**切换逻辑**：
```python
class PlantUMLRenderer(DiagramRenderer):
    def __init__(self, config: PlantUMLConfig):
        if config.mode == "local":
            self._strategy = LocalJARStrategy(config.jar_path)
        else:
            self._strategy = OnlineServiceStrategy(config.server_url)
```

---

### 4.4 `core/renderer/mermaid_renderer.py` — Mermaid 渲染器

**策略一：本地 mmdc 模式**
```
render(code) → 写入临时 .mmd 文件
             → subprocess: mmdc -i <file> -o <output.png> -b white
             → 读取输出 PNG → 返回 image_data
```

**策略二：Mermaid.ink API 模式**
```
render(code) → base64url 编码代码
             → GET https://mermaid.ink/img/<encoded>
             → 返回响应体（PNG 二进制）
```

---

### 4.5 `core/assembler.py` — HTML 组装模块

**职责**：将 `ParseResult` 与各图表的 `RenderResult` 合并，生成完整的独立 HTML 字符串。

**处理步骤**：
1. 遍历 `diagrams` 列表，调用对应渲染器。
2. 渲染成功 → 将图片数据编码为 Base64 Data URI，替换 HTML 中的占位符 `div` 为 `<img src="data:image/png;base64,...">` 标签。
3. 渲染失败 → 将占位符替换为带警告样式的原始代码块 `<pre class="diagram-error">`，并记录 WARNING 日志。
4. 从配置中读取（或使用默认）CSS 样式，以 `<style>` 标签内联注入，保证 PDF 为自包含文件。
5. 填充 HTML 模板（`<html><head><body>`），注入元数据（title、author 等）。

**输出**：完整的独立 HTML 字符串（无外部资源引用）。

---

### 4.6 `core/pdf_generator.py` — PDF 生成模块

**职责**：使用 WeasyPrint 将 HTML 字符串转换为 PDF 文件。

```python
class PDFGenerator:
    def generate(self, html: str, output_path: str) -> None:
        from weasyprint import HTML, CSS
        HTML(string=html).write_pdf(output_path)

    def generate_to_bytes(self, html: str) -> bytes:
        """用于生成临时预览，不写磁盘"""
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
```

**分页控制**（通过 CSS @page 规则）：
- 代码块、表格设置 `page-break-inside: avoid`，避免被截断。
- 图片设置 `page-break-inside: avoid`。
- 标题（h1~h3）设置 `page-break-after: avoid`，避免孤立标题。

---

### 4.7 `core/previewer.py` — 预览模块

**MVP 实现**：
```python
class Previewer:
    def preview(self, pdf_bytes: bytes) -> None:
        """将 PDF 写入临时文件并用系统默认查看器打开"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = f.name
        os.startfile(tmp_path)  # Windows 原生调用
        # 注册程序退出时清理临时文件
        self._register_cleanup(tmp_path)
```

**增强实现（后期迭代）**：
- 基于 `tkinter` 构建独立预览窗口。
- 使用 `PyMuPDF`（fitz）将 PDF 页面渲染为图像，展示在 `Canvas` 控件中。
- 支持滚动翻页、缩放（鼠标滚轮 / 按钮）。
- 提供"确认保存"/"取消"按钮，用户确认后再写入最终 PDF。

---

### 4.8 `config/config_loader.py` — 配置加载模块

**职责**：合并各层配置，向全系统暴露唯一 `AppConfig` 对象。

```python
@dataclass
class AppConfig:
    # PDF 元数据
    title: str = ""
    author: str = ""
    # 页面设置
    page_size: str = "A4"
    margin_top: str = "2.5cm"
    margin_bottom: str = "2.5cm"
    margin_left: str = "2.5cm"
    margin_right: str = "2.5cm"
    # 样式
    custom_css_path: str | None = None
    font_family: str = "Arial, 'Noto Sans CJK SC', sans-serif"
    # PlantUML
    plantuml_mode: str = "local"          # "local" | "online"
    plantuml_jar_path: str = "plantuml.jar"
    plantuml_server_url: str = "http://www.plantuml.com/plantuml"
    # Mermaid
    mermaid_mode: str = "local"           # "local" | "online"
    mermaid_mmdc_path: str = "mmdc"
    mermaid_ink_url: str = "https://mermaid.ink/img"
    # 输出
    preview: bool = False
    output_path: str | None = None
```

**合并优先级**（从低到高）：
```
default_config.yaml → ~/.mdtopdf/config.yaml → Front Matter → CLI 参数
```

---

### 4.9 `utils/` — 工具模块

| 文件 | 职责 |
|------|------|
| `logger.py` | 初始化 `logging`，提供统一 Logger（支持 `--verbose` 控制级别） |
| `temp_manager.py` | 管理临时目录生命周期，程序退出时自动清理 |
| `file_utils.py` | 文件路径规范化、扩展名校验、输出路径推导（同目录、同名 `.pdf`） |

---

## 5. 数据流程设计

### 5.1 主流程时序图

```
用户 → CLI → ConfigLoader → MarkdownParser → Assembler → PDFGenerator → FileOutput
                 │               │
                 │           DiagramRenderer（PlantUML / Mermaid）
                 │
                 └──────────────────────────────────────────────▶ Previewer（可选）
```

### 5.2 核心处理流程（详细步骤）

```
Step 1  CLI 接收参数：input.md, [output.pdf], [--preview], [--config], [--verbose]

Step 2  ConfigLoader：
        加载 default_config.yaml
        → 若存在 ~/.mdtopdf/config.yaml，覆盖合并
        → 若 CLI 指定 --config <file>，覆盖合并
        → 输出：base_config

Step 3  MarkdownParser：
        读取 input.md 文件内容
        → 使用 python-frontmatter 分离 front_matter 和 body
        → front_matter 覆盖 base_config（标题、作者等元数据）
        → 对 body 应用 Python-Markdown 解析（含自定义扩展）
        → 输出：ParseResult { html_body, diagrams[] }

Step 4  DiagramRendering（并行可优化）：
        对 ParseResult.diagrams 中每个 Diagram：
          → 根据 diagram.type 选择 PlantUMLRenderer / MermaidRenderer
          → 调用 renderer.render(diagram.code)
          → 成功 → image_data（bytes） + format
          → 失败 → error_message，记录 WARNING 日志

Step 5  Assembler：
        遍历 diagrams，将占位 div 替换为：
          → 成功：<img src="data:image/png;base64,...">
          → 失败：<pre class="diagram-error">原始代码</pre> + 错误提示标注
        注入 CSS（默认 + 用户自定义）
        填充 HTML 模板（title、author、body）
        → 输出：html_string（完整自包含 HTML）

Step 6  PDFGenerator（预览模式）：
        若 --preview 启用：
          html_string → WeasyPrint → pdf_bytes（内存）
          → Previewer.preview(pdf_bytes) → 临时文件 → os.startfile()
          → 等待用户确认（可选交互）

Step 7  PDFGenerator（最终输出）：
        html_string → WeasyPrint → output.pdf
        → 输出完成日志：已生成 output.pdf（文件大小）

Step 8  TempManager.cleanup() → 删除所有临时文件
```

### 5.3 图表渲染降级逻辑

```
DiagramRenderer.render(code)
        │
        ▼
  主策略可用？（JAR 存在 / mmdc 可找到）
        │
    Yes │         No
        ▼          ▼
  执行渲染    备用策略可用？（网络可达）
        │          │
    成功 │      Yes │         No
        ▼          ▼          ▼
  返回图片    执行在线渲染  返回失败结果
                   │          │
               成功 │      失败 │
                   ▼          ▼
             返回图片    返回失败结果
                              │
                              ▼
                    Assembler 保留原始代码块
                    + WARNING 日志输出
```

---

## 6. 配置体系设计

### 6.1 默认配置文件 `config/default_config.yaml`

```yaml
# PDF 页面设置
page:
  size: A4
  margin:
    top: 2.5cm
    bottom: 2.5cm
    left: 2.5cm
    right: 2.5cm

# 排版样式
style:
  font_family: "Arial, 'Noto Sans CJK SC', sans-serif"
  font_size: 12pt
  line_height: 1.6
  code_font_family: "'Courier New', Consolas, monospace"
  code_font_size: 10pt
  custom_css: null

# PlantUML 渲染配置
plantuml:
  mode: local              # local | online
  jar_path: plantuml.jar   # 相对于工作目录或绝对路径
  server_url: "http://www.plantuml.com/plantuml"
  timeout: 30              # 秒

# Mermaid 渲染配置
mermaid:
  mode: local              # local | online
  mmdc_path: mmdc          # Node.js CLI 工具
  ink_url: "https://mermaid.ink/img"
  timeout: 30              # 秒
  background_color: white

# 预览设置
preview:
  enabled: false
  auto_close: false        # 预览后是否自动关闭并保存

# 输出设置
output:
  default_suffix: .pdf
  open_after_export: false
```

### 6.2 Markdown Front Matter 支持字段

```yaml
---
title: "我的技术文档"
author: "张三"
date: "2026-03-30"
page_size: A4              # 可覆盖全局配置
custom_css: "./my_style.css"
plantuml_mode: online      # 仅本文档使用在线 PlantUML
---
```

---

## 7. CLI 接口设计

### 7.1 命令语法

```
mdtopdf [OPTIONS] INPUT_FILE [OUTPUT_FILE]
```

### 7.2 参数说明

| 参数 / 选项 | 类型 | 默认值 | 说明 |
|-------------|------|--------|------|
| `INPUT_FILE` | 必填参数 | — | 输入 `.md` / `.markdown` 文件路径 |
| `OUTPUT_FILE` | 可选参数 | 同输入目录、同名 `.pdf` | 输出 PDF 文件路径 |
| `--preview / --no-preview` | 标志 | `--no-preview` | 生成前用系统查看器预览 |
| `--config <path>` | 路径 | 无 | 指定外部配置文件 |
| `--plantuml-jar <path>` | 路径 | `plantuml.jar` | 覆盖 PlantUML JAR 路径 |
| `--plantuml-mode <mode>` | 枚举（local/online） | `local` | PlantUML 渲染模式 |
| `--mermaid-mode <mode>` | 枚举（local/online） | `local` | Mermaid 渲染模式 |
| `--css <path>` | 路径 | 无 | 自定义 CSS 文件 |
| `--open` | 标志 | 关闭 | 完成后自动打开 PDF |
| `--verbose / -v` | 标志 | 关闭 | 显示详细处理日志 |
| `--version` | 标志 | — | 显示版本号 |
| `--help` | 标志 | — | 显示帮助信息 |

### 7.3 典型用法示例

```bash
# 基本转换（输出为 input.pdf，与 input.md 同目录）
mdtopdf input.md

# 指定输出路径
mdtopdf input.md output/document.pdf

# 转换前预览
mdtopdf input.md --preview

# 使用自定义 CSS + 本地 PlantUML JAR
mdtopdf input.md --css theme.css --plantuml-jar /opt/plantuml.jar

# 使用在线渲染模式（无本地依赖）
mdtopdf input.md --plantuml-mode online --mermaid-mode online

# 详细日志输出
mdtopdf input.md -v
```

---

## 8. 错误处理设计

### 8.1 错误分类与处理策略

| 错误类型 | 触发场景 | 处理策略 | 日志级别 |
|----------|----------|----------|----------|
| 输入文件不存在 | `INPUT_FILE` 路径无效 | 立即终止，输出明确错误信息，exit(1) | ERROR |
| 输入文件格式错误 | 扩展名非 .md / .markdown | 警告后继续处理（尝试按 Markdown 解析） | WARNING |
| Front Matter 解析失败 | YAML 语法错误 | 忽略 Front Matter，使用默认配置继续 | WARNING |
| PlantUML 渲染失败 | JAR 不存在 / 代码错误 / 网络超时 | 降级保留原始代码块文本，继续 | WARNING |
| Mermaid 渲染失败 | mmdc 不存在 / 代码错误 / 网络超时 | 降级保留原始代码块文本，继续 | WARNING |
| CSS 文件不存在 | `--css` 指定路径无效 | 忽略自定义 CSS，使用默认样式继续 | WARNING |
| PDF 生成失败 | WeasyPrint 内部错误 / 磁盘写入失败 | 立即终止，输出错误信息，exit(1) | ERROR |
| 输出目录不存在 | OUTPUT_FILE 父目录不存在 | 自动创建目录后继续 | INFO |

### 8.2 日志格式

```
[LEVEL] [TIMESTAMP] [MODULE] message

示例：
[INFO]  2026-03-30 10:23:01 [Parser]   已解析 input.md (3 个图表，2 个代码块)
[INFO]  2026-03-30 10:23:02 [PlantUML] 渲染图表 1/3 完成 (diagram_abc123.png, 45.2 KB)
[WARN]  2026-03-30 10:23:05 [Mermaid]  图表 2/3 渲染失败 (mmdc 未找到，尝试在线服务)
[WARN]  2026-03-30 10:23:08 [Mermaid]  图表 2/3 在线渲染超时，已降级为原始代码块
[INFO]  2026-03-30 10:23:09 [PDF]      已生成 output.pdf (1.23 MB)
```

### 8.3 图表渲染失败时的 PDF 显示效果

渲染失败的图表将在 PDF 中以如下方式呈现：

```
┌─────────────────────────────────────────────┐
│  ⚠  图表渲染失败（mermaid）                  │
│  错误信息：mmdc 命令未找到                   │
│                                             │
│  原始代码：                                  │
│  graph TD                                   │
│      A --> B                                │
└─────────────────────────────────────────────┘
```

---

## 9. 样式与排版设计

### 9.1 默认 CSS 设计要点（`assets/styles/default.css`）

```css
/* 页面设置 */
@page {
    size: A4;
    margin: 2.5cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}

/* CJK 字体支持 */
body {
    font-family: Arial, "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    font-size: 12pt;
    line-height: 1.6;
    color: #333;
}

/* 表格样式 */
table {
    border-collapse: collapse;
    width: 100%;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #ccc;
    padding: 6px 12px;
}
th { background-color: #f5f5f5; font-weight: bold; }

/* 代码块样式（Pygments 高亮容器） */
.highlight {
    background-color: #f8f8f8;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 12px;
    overflow-x: auto;
    page-break-inside: avoid;
}
.highlight pre {
    font-family: "Courier New", Consolas, monospace;
    font-size: 10pt;
    margin: 0;
}

/* 图表图片 */
.diagram-img {
    display: block;
    max-width: 100%;
    margin: 12px auto;
    page-break-inside: avoid;
}

/* 渲染失败的图表占位 */
.diagram-error {
    background-color: #fff3cd;
    border: 1px solid #ffc107;
    border-left: 4px solid #ff9800;
    padding: 12px;
    page-break-inside: avoid;
}

/* 分页控制 */
h1, h2, h3 { page-break-after: avoid; }
img { page-break-inside: avoid; }
```

### 9.2 字体说明

| 场景 | Windows 推荐字体 |
|------|-----------------|
| 中文正文 | Microsoft YaHei（微软雅黑）或 Noto Sans CJK SC |
| 英文正文 | Arial |
| 代码块 | Consolas 或 Courier New |

> **注意**：WeasyPrint 在 Windows 下通过系统字体目录自动查找字体，中文字体需确保系统已安装。

---

## 10. 项目目录结构

```
MdToPdf/
├── mdtopdf/                        # 主包
│   ├── __init__.py
│   ├── main.py                     # CLI 入口（click）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── parser.py               # Markdown 解析模块
│   │   ├── assembler.py            # HTML 组装模块
│   │   ├── pdf_generator.py        # PDF 生成模块
│   │   ├── previewer.py            # 预览模块
│   │   └── renderer/
│   │       ├── __init__.py
│   │       ├── base.py             # DiagramRenderer 抽象基类
│   │       ├── plantuml_renderer.py
│   │       └── mermaid_renderer.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── config_loader.py        # 配置合并逻辑
│   │   ├── models.py               # AppConfig dataclass
│   │   └── default_config.yaml     # 默认配置
│   ├── assets/
│   │   ├── styles/
│   │   │   └── default.css         # 默认 PDF 样式
│   │   └── templates/
│   │       └── document.html       # HTML 文档模板
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       ├── temp_manager.py
│       └── file_utils.py
├── tests/                          # 单元测试
│   ├── test_parser.py
│   ├── test_plantuml_renderer.py
│   ├── test_mermaid_renderer.py
│   ├── test_assembler.py
│   └── fixtures/                   # 测试用 .md 文件
├── docs/
│   ├── system_design.md            # 本文档
│   └── user_guide.md               # 用户手册（待编写）
├── CRD/
│   └── crd.md
├── requirements.txt                # 运行时依赖
├── requirements-dev.txt            # 开发依赖
├── setup.py / pyproject.toml       # 打包配置
└── README.md
```

---

## 11. 依赖清单

### 11.1 运行时依赖（`requirements.txt`）

| 包名 | 版本约束 | 用途 |
|------|----------|------|
| `click` | >=8.0 | CLI 框架 |
| `Markdown` | >=3.5 | Markdown 解析（Python-Markdown） |
| `python-frontmatter` | >=1.0 | YAML Front Matter 提取 |
| `Pygments` | >=2.16 | 代码语法高亮 |
| `WeasyPrint` | >=60.0 | HTML → PDF 转换 |
| `PyYAML` | >=6.0 | YAML 配置文件解析 |
| `requests` | >=2.31 | 在线渲染器 HTTP 调用 |
| `Pillow` | >=10.0 | 图像处理（SVG → PNG 等辅助） |
| `Jinja2` | >=3.1 | HTML 模板渲染 |

### 11.2 外部环境依赖（非 Python 包）

| 依赖 | 版本要求 | 用途 | 必须性 |
|------|----------|------|--------|
| JRE（Java） | ≥ 8 | 运行 PlantUML JAR | 本地 PlantUML 必须 |
| `plantuml.jar` | 最新版 | PlantUML 渲染引擎 | 本地 PlantUML 必须 |
| Node.js | ≥ 16 | 运行 mmdc（Mermaid CLI） | 本地 Mermaid 必须 |
| `@mermaid-js/mermaid-cli` | ≥ 10 | Mermaid 渲染引擎 | 本地 Mermaid 必须 |
| GTK3 运行时（Windows） | — | WeasyPrint 图形后端 | WeasyPrint 必须 |

> 若使用全在线模式（`plantuml_mode: online` + `mermaid_mode: online`），则仅需 GTK3 运行时，无需 Java 和 Node.js。

### 11.3 开发依赖（`requirements-dev.txt`）

| 包名 | 用途 |
|------|------|
| `pytest` | 单元测试框架 |
| `pytest-cov` | 代码覆盖率 |
| `black` | 代码格式化 |
| `flake8` | 代码规范检查 |
| `mypy` | 类型检查 |

---

## 12. 非功能性需求实现方案

### 12.1 准确性

- Markdown 解析采用成熟的 Python-Markdown，严格遵循 CommonMark 规范及扩展。
- 图表渲染优先使用官方工具（PlantUML JAR / mmdc），保证输出与官方一致。
- HTML 中间态可独立在浏览器中验证，便于排查渲染偏差。

### 12.2 性能

- 图表渲染可并发执行（`concurrent.futures.ThreadPoolExecutor`），多图表文档显著提速。
- WeasyPrint 单次 PDF 生成调用，无需多次 I/O。
- 临时图片文件使用 Base64 内联，避免 WeasyPrint 反复读写磁盘。
- 估算性能基准（4 核 CPU，Windows 10）：
  - 无图表文档（10 页）：< 5 秒
  - 含 5 个图表文档（15 页）：< 30 秒（本地渲染）/ < 60 秒（在线渲染）

### 12.3 易用性

- CLI 参数简洁，最简用法仅需提供输入文件路径。
- 所有错误信息使用自然语言描述，并提示可能的解决方案。
- 通过 `--verbose` 可查看详细处理日志，便于调试。
- `--help` 输出完整参数说明与用法示例。

### 12.4 Windows 兼容性

- 所有路径处理使用 `pathlib.Path`，自动处理 Windows 路径分隔符。
- 临时文件使用 `tempfile` 模块，遵守 Windows 临时目录规范。
- 子进程调用（Java / Node.js）使用 `subprocess.run` 并指定 `shell=False` 防止注入。
- 字体查找通过 WeasyPrint 的 Windows 字体目录自动完成。
- `os.startfile()` 为 Windows 原生 API，预览功能无需额外依赖。

---

## 13. 开发里程碑

### Phase 1 — MVP（核心功能）

| 任务 | 交付物 |
|------|--------|
| 搭建项目骨架与 CLI 框架 | `main.py`，`config/` 模块，`utils/` 模块 |
| Markdown 解析 + 代码高亮 | `parser.py`，代码高亮 CSS |
| 表格渲染 | 通过 `tables` 扩展 + CSS 验证 |
| PlantUML 本地 JAR 渲染 | `plantuml_renderer.py`（本地策略） |
| Mermaid 在线渲染 | `mermaid_renderer.py`（在线策略） |
| HTML → PDF（WeasyPrint） | `assembler.py`，`pdf_generator.py`，`default.css` |
| 错误降级与日志 | 图表渲染失败保留代码块 + WARNING 日志 |

### Phase 2 — 增强功能

| 任务 | 交付物 |
|------|--------|
| 预览功能（系统查看器） | `previewer.py`（MVP 版） |
| PlantUML 在线服务支持 | `plantuml_renderer.py`（在线策略） |
| Mermaid 本地 mmdc 支持 | `mermaid_renderer.py`（本地策略） |
| YAML Front Matter 元数据 | `config_loader.py` 合并逻辑完善 |
| 自定义 CSS 支持 | Assembler 注入逻辑 |
| 页脚页码 | `@page` CSS 规则 |

### Phase 3 — 完善与打包

| 任务 | 交付物 |
|------|--------|
| 单元测试覆盖 | `tests/` 目录，覆盖率 ≥ 70% |
| tkinter 增强预览窗口 | `previewer.py`（增强版），PyMuPDF 集成 |
| 打包为 Windows EXE | PyInstaller 配置，含 GTK 依赖打包 |
| 用户手册 | `docs/user_guide.md` |

---

*文档结束*

