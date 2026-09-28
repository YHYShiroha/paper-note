---
name: paper-note
description: 把用户上传的论文 PDF 整理成固定风格的中文 Markdown 阅读笔记：按既定大纲重组论文内容，从 PDF 中提取论文原图放入 image/ 文件夹，并按编号规范命名输出（如 0004C/0004C_论文标题.md）。当用户给出论文 PDF 与编号并要求撰写「论文笔记 / paper note / 阅读笔记」时使用。
---

# Paper Note（论文笔记）

把一篇论文 PDF 变成一份可以直接归档的中文阅读笔记。笔记不是论文的翻译或缩写，而是按固定大纲重新组织的**批判性阅读记录**。

## 输入与交付物

用户会给出论文 PDF（通常还有编号，如 `0004C`）。缺编号时先问一次再动手，不要自己编号。

```
<笔记根目录>/<编号>/
├── <编号>_<论文标题>.md      # 笔记正文
└── image/
    ├── image-1.png
    ├── image-2.png
    └── ...
```

硬性命名规范：

- 标题用论文的原始标题（通常为英文）；删掉 `:`，其余 Windows 非法字符 `\ / * ? " < > |` 换成空格。
- 图片按**正文出现顺序**编号 `image-1`…`image-N`，连续不跳号；`image/` 里不允许留未引用的文件。
- 正文引用固定写成 `![image-1](image/image-1.png)`，**中括号里的文字必须与文件名主体一致**。
- 输出目录优先级：用户指定的位置 > `笔记/<编号>/`（当 PDF 位于 `原文/` 且同级存在 `笔记/`，这是本知识库的惯例）> PDF 所在目录。
- 只有**落成文件**的图片占用 `image-N` 编号。直接写在正文里的自绘图（markdown 表格、mermaid / plantuml 代码块）不占编号；一旦决定渲染成 PNG，就顺延取下一个编号。

## 工作流

### 1. 建骨架

```bash
python scripts/new_note.py --id 0004C --title "<论文原始标题>" --pdf "<论文.pdf>" \
    --short-name "<短名>" --venue "<会议/年份/页数>" --year <年份>
```

它会按命名规范创建 `<编号>/`、`image/` 和带大纲的 md 骨架。写入前确认 `--title` 是否与论文标题逐字一致。

### 2. 读 PDF：先文本，再定位图表

```bash
python scripts/extract_pdf.py info    "<论文.pdf>"
python scripts/extract_pdf.py text    "<论文.pdf>" -o "<工作目录>/text"
python scripts/extract_pdf.py captions "<论文.pdf>"
```

读完整文本（`text/full-text.md`）后再动笔。`captions` 给出每张图/表的标题行、页码和 bbox，是后面裁图的定位依据。

### 3. 抽图

先决定抽哪几张——通常值得抽的是：方法总览/架构图、核心算法或伪代码、主结果图、消融图、最关键的对照表。logo、装饰图、teaser、低分辨率图直接跳过；普通表格改写成 markdown 表格，只有结构复杂或依赖颜色时才抽图。

```bash
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<笔记目录>/image/image-1.png" --above-caption 3 --dpi 300
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<笔记目录>/image/image-2.png" --below-caption 4 --dpi 200
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<笔记目录>/image/image-3.png" --page 5 --bbox 54,300,298,560 --dpi 300 --trim
python scripts/extract_pdf.py images "<论文.pdf>" -o "<工作目录>/embedded"
```

`--above-caption N` 用于"图在标题上方"（最常见），`--below-caption N` 用于"标题在图上方"。论文里的图多数是矢量绘制，`crop`（页面裁剪）比 `images`（抽取内嵌位图）更常用；自动裁剪失效时用 `--page` + `--bbox` 手动给区域。

先把候选图裁到工作目录、逐张确认，再挑中的图按正文顺序落到 `<编号>/image/`。抽完必须**逐张看一眼**：图是否完整、有没有带进相邻栏的正文、字够不够清楚。不合格就调 bbox 或提高 dpi 重抽，不要带着残缺图继续写。细节、坐标换算和疑难处理见 `references/pdf-extraction.md`。

### 4. 写笔记

动笔前读这两份参考：

- `references/note-outline.md`：大纲层级、每节必须包含的内容、图表分配。
- `references/writing-style.md`：语言、术语、语气、排版规则和可复用的段落写法。

按大纲把内容重组出来，而不是顺着论文段落翻译。笔记的价值在于**结论、机制、证据、判断**，不在于复述。

### 5. 自查

```bash
python scripts/check_note.py "<笔记根目录>/<编号>"
```

检查文件名、图片命名连续性、引用与文件是否一一对应。报告为 0 error 才算完成；随后再通读一遍正文，确认没有编造的数字或结论。

## 底线

- **不编造**。论文没写的数字、结论、对比、引用都不要出现在笔记里；拿不准就写论文实际说了什么。
- 数字、模型名、数据集名、阈值、页码要精确到可以直接回查。
- 不逐段翻译，不写"实验充分""方法新颖"这类空泛评价。
- 图片必须目视验证过再插入；正文要说明这张图在讲什么，而不是只丢一张图。
- 交付前用 `check_note.py` 收尾，并把最终的文件路径、笔记文件名、图片数量报告给用户。

## 参考文件

| 文件 | 何时读 |
| ---- | ------ |
| `references/note-outline.md` | 写笔记前（必读）：大纲与每节内容要求 |
| `references/writing-style.md` | 写笔记前（必读）：行文风格与格式细则 |
| `references/pdf-extraction.md` | 抽图前：提取流程、坐标换算、失败处理 |
