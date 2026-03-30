---
title: "含图表的示例文档"
author: "图表测试"
---

# 系统架构文档

本文档展示 PlantUML 和 Mermaid 图表的渲染效果。

## PlantUML 时序图

```plantuml
@startuml
actor 用户
participant "CLI" as CLI
participant "Parser" as P
participant "Assembler" as A
participant "PDFGenerator" as PDF

用户 -> CLI: mdtopdf input.md
CLI -> P: parse(input.md)
P --> CLI: ParseResult
CLI -> A: assemble(ParseResult)
A --> CLI: HTML 字符串
CLI -> PDF: generate_file(html)
PDF --> CLI: output.pdf
CLI --> 用户: ✓ 已生成 PDF
@enduml
```

## Mermaid 流程图

```mermaid
flowchart TD
    A[输入 .md 文件] --> B[Parser 解析]
    B --> C{含图表?}
    C -- 是 --> D[渲染图表]
    C -- 否 --> E[组装 HTML]
    D --> E
    E --> F[WeasyPrint]
    F --> G[输出 PDF]
```

## PlantUML 类图

```plantuml
@startuml
abstract class DiagramRenderer {
  +render(diagram: Diagram): RenderResult
}

class PlantUMLRenderer {
  -_local: LocalJARStrategy
  -_online: OnlineServiceStrategy
  +render(diagram: Diagram): RenderResult
}

class MermaidRenderer {
  -_local: LocalMMDCStrategy
  -_online: MermaidInkStrategy
  +render(diagram: Diagram): RenderResult
}

DiagramRenderer <|-- PlantUMLRenderer
DiagramRenderer <|-- MermaidRenderer
@enduml
```

## Mermaid 甘特图

```mermaid
gantt
    title 开发里程碑
    dateFormat  YYYY-MM-DD
    section Phase 1 MVP
    项目骨架       :done,    p1, 2026-03-01, 3d
    Markdown 解析  :done,    p2, 2026-03-04, 4d
    图表渲染       :active,  p3, 2026-03-08, 5d
    PDF 生成       :         p4, 2026-03-13, 3d
    section Phase 2
    预览功能       :         p5, 2026-03-16, 4d
    单元测试       :         p6, 2026-03-20, 5d
```

## 与代码块混合

正常代码块不受影响：

```python
class HTMLAssembler:
    def assemble(self, parse_result):
        render_results = self._render_diagrams(parse_result.diagrams)
        return self._build_html(render_results)
```

| 渲染引擎 | 本地模式 | 在线模式 |
|----------|----------|----------|
| PlantUML | java -jar plantuml.jar | plantuml.com |
| Mermaid  | mmdc CLI | mermaid.ink |

