# mdtopdf

将包含表格、代码块、PlantUML/Mermaid 图表的 Markdown 技术文档转换为单文件 PDF。

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

## 外部依赖（非 Python）

| 依赖 | 用途 | 获取方式 |
|------|------|----------|
| **GTK3 运行时**（Windows 必须） | WeasyPrint 图形后端 | [GTK3 Windows Installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) |
| JRE ≥ 8 + `plantuml.jar` | 本地 PlantUML 渲染 | [PlantUML 下载](https://plantuml.com/download) |
| Node.js ≥ 16 + `mmdc` | 本地 Mermaid 渲染 | `npm install -g @mermaid-js/mermaid-cli` |

> **最小安装**：只需安装 GTK3，其余图表通过在线服务渲染：
> ```bash
> mdtopdf input.md --plantuml-mode online --mermaid-mode online
> ```

## 快速使用

```bash
# 基本转换（输出到同目录 input.pdf）
mdtopdf input.md

# 指定输出路径
mdtopdf input.md output/document.pdf

# 转换前预览
mdtopdf input.md --preview

# 使用自定义 CSS
mdtopdf input.md --css my_theme.css

# 使用本地 PlantUML JAR
mdtopdf input.md --plantuml-jar /path/to/plantuml.jar

# 全在线模式（无需 Java/Node.js）
mdtopdf input.md --plantuml-mode online --mermaid-mode online

# 数学公式渲染策略（online/auto/latex2mathml）
mdtopdf input.md --math-mode online

# 在线公式节点链（一个失败继续尝试下一个）
mdtopdf input.md --math-mode online --math-online-providers codecogs_png,vercel_svg,mathnow_svg
mdtopdf input.md --math-online-timeout 12

# 关闭裸 LaTeX 兼容开关
mdtopdf input.md --no-math-bare-latex

# 详细日志
mdtopdf input.md -v
```

## 支持的 Markdown 元素

- **标准语法**：标题、段落、列表、引用、链接、图片、加粗/斜体
- **表格**：自动适配页宽，长内容可软换行
- **代码块 / 行内代码**：通过 Pygments 语法高亮，长行自动软换行
- **LaTeX 数学公式**：支持行内 `$...$` / `\(...\)` 与块级 `$$...$$` / `\[...\]`
- **PlantUML 图表**：时序图、类图、流程图等
- **Mermaid 图表**：流程图、时序图、甘特图等
- **YAML Front Matter**：文档标题、作者、日期

## Front Matter 配置

```yaml
---
title: "我的技术文档"
author: "张三"
date: "2026-03-30"
plantuml_mode: online   # 覆盖全局配置
custom_css: "./my_style.css"
---
```

## 配置文件

在 `~/.mdtopdf/config.yaml` 中设置个人默认配置：

```yaml
plantuml:
  mode: local
  jar_path: /opt/plantuml.jar

mermaid:
  mode: online

style:
  font_family: "Arial, 'Microsoft YaHei', sans-serif"

math:
  mode: online        # online | auto | latex2mathml
  online_timeout: 10
  online_providers: codecogs_png,vercel_svg,mathnow_svg
  enable_bare_latex: true
```

数学渲染策略说明：

- `online`：仅使用在线 API 链渲染，产出内联 base64 图片。
- `auto`：优先在线 API 链，其次 `latex2mathml`。
- `latex2mathml`：优先 `latex2mathml`；失败时尝试在线 API。

在线公式图片会并行拉取（不同公式并发请求），长文档转换会更快。

在线 API 节点标识：

- `codecogs_png` -> `https://latex.codecogs.com/png.image?...`
- `vercel_svg` -> `https://math.vercel.app/?from=...`
- `mathnow_svg` -> `https://math.now.sh?from=...`

## 开发

```bash
pip install -r requirements-dev.txt
pytest tests/                    # 运行测试
pytest --cov=mdtopdf tests/      # 带覆盖率
black mdtopdf/                   # 格式化
flake8 mdtopdf/                  # lint
```

## 项目结构

```
mdtopdf/
  main.py              # CLI 入口（click）
  core/
    parser.py          # Markdown 解析 + 图表拦截
    assembler.py       # HTML 组装 + 并发渲染
    pdf_generator.py   # WeasyPrint 封装
    previewer.py       # 系统预览器
    renderer/
      base.py          # DiagramRenderer ABC
      plantuml_renderer.py
      mermaid_renderer.py
  config/
    config_loader.py   # 多层配置合并
    models.py          # AppConfig dataclass
    default_config.yaml
  assets/
    styles/default.css
    templates/document.html
  utils/               # logger, temp_manager, file_utils
tests/
  fixtures/            # 示例 .md 文件
```
## 打包成 EXE（Windows）

```bash
# 激活虚拟环境
.venv\Scripts\Activate.ps1

```

```bash
# 默认：单文件 GUI EXE
python build_exe.py
```
```bash
# 文件夹模式（启动更快）
python build_exe.py --onedir
```

```bash
# 同时打包 CLI
python build_exe.py --with-cli
```

```bash
# 手动指定 GTK3（若自动检测失败）
python build_exe.py --gtk3-bin "C:\Program Files\GTK3-Runtime Win64\bin"
```