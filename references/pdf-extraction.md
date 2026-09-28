# PDF 读取与图片提取

## 依赖

Poppler：`pdfinfo`、`pdftotext`、`pdftoppm`、`pdfimages`；`--trim` 需要 Pillow。全部命令通过 `scripts/extract_pdf.py` 调用，避免临时手写参数。Windows 上如果这些工具不在 PATH，先装 Poppler 再重试。

## 步骤

**1. 摸底**

```bash
python scripts/extract_pdf.py info "<论文.pdf>"
```

给出页数、页面尺寸、文本层字符数、图/表标题数量。`page-1 text` 字符数很低说明是扫描版（见下方"常见问题"）。

**2. 抽文本**

```bash
python scripts/extract_pdf.py text "<论文.pdf>" -o "<工作目录>/text"
```

生成逐页 `page-NNN.txt` 和合并的 `full-text.md`（带 `<!-- ===== page N ===== -->` 分隔）。先读完整文本再写笔记；正文中出现的图表编号要记下来，后面按编号找图。

**3. 定位图表**

```bash
python scripts/extract_pdf.py captions "<论文.pdf>"
```

每行给出 `[序号] 页码 类型 编号 bbox=...` 和标题正文，`--json` 可输出结构化结果。序号用于 `--above-caption N`。

**4. 选图**

优先抽：方法总览/架构图、核心算法或伪代码、主结果图、消融图、自适应/鲁棒性图。跳过：logo、装饰图、teaser、低分辨率图、正文表格。表格一般改写成 markdown 表格。

**5. 抽图**

两条路径，先试 `crop`：

```bash
# A. 图在标题上方（最常见的版式）：自动取该栏上方区域
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<工作目录>/fig3.png" --above-caption 3 --dpi 300

# B. 标题在图上方（部分期刊的图、绝大多数表格）：取下方区域
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<工作目录>/tbl1.png" --below-caption 4 --dpi 200

# C. 手动指定区域（跨栏/跨页大图，或自动结果不理想时）
python scripts/extract_pdf.py crop "<论文.pdf>" -o "<工作目录>/fig1.png" \
    --page 2 --bbox 54,120,558,330 --dpi 200 --trim

# D. 图本身是整块内嵌位图时，先抽取再挑
python scripts/extract_pdf.py images "<论文.pdf>" -o "<工作目录>/embedded"
```

自动裁剪的算法：

1. caption 连同紧邻的续行（间距 < 6 pt 且横向重叠）合并成 **caption block**；
2. 宽度按 caption 所在栏取：caption block 宽于页宽 60% 视为跨栏图，否则按左/右栏；
3. 边界取该栏内最近的**正文段落**下缘、相邻 caption block 的边界、或页边距；
4. 正文段落通过与图内标签的差异识别——连续 ≥3 行、行宽 ≥ 栏宽 55%、左端与栏边对齐、行距规整。图里的坐标轴标签和图例因此不会被误判成正文边界，版式正常的论文能得到干净的区域。

**自动裁剪只是起点，结果必须目视确认**；版式异常（跨页图、一个区域含多张图、正文与图同栏交错）时改用 `--bbox` 手动给区域。工具会把最终区域打印出来，便于核对。

**6. 校验并落盘**

逐张看图，确认：图完整（没有缺边）、没有混入相邻栏正文或其它图的标题、文字可读、没有大片空白。不满足就提高 `--dpi`（含小字的流程图用 300，一般图 200）、加 `--trim`、或改用 `--bbox` 重抽。

按正文出现顺序命名为 `image-1`…`image-N`，放进 `<编号>/image/`，正文引用写 `![image-1](image/image-1.png)`。

## 坐标与换算

- `captions` 与 `--bbox` 用的都是 PDF point（1/72 inch），原点在左上、y 轴向下，与 `pdftotext -bbox-layout` 一致。
- 像素 = point × dpi / 72。200 dpi 约 2.78 px/pt，300 dpi 约 4.17 px/pt。
- 常见页面宽度：Letter 612 pt、A4 595 pt。双栏论文单栏宽约 240–250 pt。
- 无坐标可用时，先用 `pages` 渲染整页（`--dpi 150`），目视量出大致比例再换算成 point。

## 常见问题

| 现象 | 处理 |
| ---- | ---- |
| `info` 提示文本层字符很少 | 扫描版 PDF。用 `pages --dpi 200` 渲染后按页读图，图片仍用 `crop` 从渲染页提取 |
| 裁出来的图混入正文 | 标题在图上方的版式改用 `--below-caption`；仍不准就手动 `--bbox`，边界取正文最后一行之下 |
| 自动裁剪报 "no space above/below caption" | 该页版式超出启发式判断，改用 `--bbox` |
| 裁出来的区域太小 | 多半是图与正文同栏交错；用 `pages` 渲染整页定位后手动给 `--bbox` |
| 图跨两栏 | 用整页宽 bbox；若横跨两页，分别裁成两张图并各给一段说明 |
| 文字太糊 | `--dpi` 提到 300–400 重抽；仍糊就保留原样并在笔记中说明 |
| 抽出的是黑块或全白 | 该区域可能是矢量遮罩或半透明层，改变 bbox 或提高 dpi；仍失败就换成整页截图 |
| 图有大量白边 | 加 `--trim`（需要 Pillow） |
| `captions` 找不到图题 | 文本层可能缺编号；用 `pages` 渲染目视定位，再手动给 `--bbox` |
| 文件太大 | 一般图用 200 dpi；单张控制在 1 MB 以内 |

## 图片质量底线

- 图上文字在 100% 缩放时能看清，否则重抽。
- 不留论文页眉、页脚、页码、邻栏正文。
- 同一篇笔记里所有图片的清晰度基本一致。
