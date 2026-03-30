---
title: "基础示例文档"
author: "测试作者"
date: "2026-03-30"
---

# 标题一

这是一段**加粗**文本和*斜体*文本，以及`内联代码`。

## 表格示例

| 列 A | 列 B | 列 C |
|------|:----:|-----:|
| 左对齐 | 居中 | 右对齐 |
| 数据 1 | 数据 2 | 数据 3 |
| 较长的数据内容 | 中等 | 99 |

## 代码块示例

```python
def hello(name: str) -> str:
    """返回问候语。"""
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(hello("World"))
```

```bash
# 安装依赖
pip install -r requirements.txt

# 运行转换
mdtopdf input.md output.pdf --verbose
```

## 引用与列表

> 这是一段引用文本。
> 支持多行引用。

### 无序列表
- 第一项
- 第二项
  - 嵌套项 A
  - 嵌套项 B
- 第三项

### 有序列表
1. 步骤一
2. 步骤二
3. 步骤三

## 分割线

---

## 链接与强调

访问 [GitHub](https://github.com) 了解更多。

~~删除线文本~~，**加粗**，*斜体*，***粗斜体***。

