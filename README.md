# paper-note

把一个论文 PDF 变成一份固定风格的中文 Markdown 阅读笔记 —— Codex skill。

给 Codex 一篇论文 PDF 和一个编号（比如 `0004C`），它会读完整篇论文，按既定大纲重组出一份批判性阅读笔记，并把论文里的图裁出来放进笔记的 `image/` 目录。

## 安装

装到 Codex 的技能目录下，让仓库根目录成为技能目录本身：

```bash
git clone https://github.com/YHYShiroha/paper-note.git ~/.codex/skills/paper-note
```

Windows PowerShell：

```powershell
git clone https://github.com/YHYShiroha/paper-note.git "$env:USERPROFILE\.codex\skills\paper-note"
```

更新技能就是拉取：

```bash
cd ~/.codex/skills/paper-note && git pull
```

## 依赖

- **Poppler**：`pdfinfo`、`pdftotext`、`pdftoppm`、`pdfimages` 需要在 PATH 上
  - Windows：`scoop install poppler` 或 `choco install poppler`
  - macOS：`brew install poppler`
  - Debian/Ubuntu：`sudo apt install poppler-utils`
- **Python 3**（脚本使用 `from __future__ import annotations`，3.8 及以上可用；实测 3.11）
- **Pillow**（可选，仅 `--trim` 用到）：`pip install pillow`

## 使用

在 Codex 里附上 PDF，然后说：

> 用 $paper-note 把这篇 PDF 整理成 0004C 的笔记

产出结构：

```
<编号>/
├── <编号>_<论文标题>.md
└── image/
    ├── image-1.png
    └── image-2.png
```

## 目录说明

| 文件 | 作用 |
| ---- | ---- |
| `SKILL.md` | 技能入口：工作流、命名规范、底线要求 |
| `references/note-outline.md` | 笔记大纲与每节必须包含的内容 |
| `references/writing-style.md` | 行文风格与格式细则 |
| `references/pdf-extraction.md` | 文本/图片提取流程、坐标换算与疑难处理 |
| `scripts/extract_pdf.py` | PDF 摸底、抽取文本、定位图表标题、裁剪图片 |
| `scripts/new_note.py` | 按命名规范创建笔记骨架 |
| `scripts/check_note.py` | 校验文件名、图片编号与引用是否一致 |

## License

MIT
