#!/usr/bin/env python3
"""Create the note folder scaffold with the required naming convention.

Usage
-----
  new_note.py --id 0004C --title "Paper: Title" --pdf <paper.pdf> [--out <dir>]
  new_note.py --id 0004C --title "Paper: Title" --pdf <paper.pdf> --out <dir> --force

Produces:
  <out>/<id>/<id>_<sanitized title>.md
  <out>/<id>/image/

When --out is omitted the script looks for the knowledge-base layout used by
this user: a PDF inside an `原文/` folder that has a sibling `笔记/` folder.
In that case the note goes to `笔记/<id>/`. Otherwise it falls back to the
folder that contains the PDF.

The created Markdown file only contains headings and empty tables. Write the
note body by following references/note-outline.md and references/writing-style.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ILLEGAL = r'[\\/*?"<>|]'

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def die(message: str) -> "None":
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(2)


def sanitize_title(title: str) -> str:
    """Drop characters that are illegal in Windows file names."""
    cleaned = title.replace(":", "")
    cleaned = re.sub(ILLEGAL, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        die("title becomes empty after sanitizing; pass a usable --title")
    return cleaned


def resolve_out(pdf: Path | None, explicit: str | None, note_id: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if pdf is None:
        return Path.cwd() / note_id
    pdf_dir = pdf.parent.resolve()
    if pdf_dir.name in {"原文", "pdf", "PDF"} and (pdf_dir.parent / "笔记").is_dir():
        return pdf_dir.parent / "笔记" / note_id
    if (pdf_dir / "笔记").is_dir():
        return pdf_dir / "笔记" / note_id
    return pdf_dir / note_id


SKELETON = """# {short_name} 论文笔记

> 原文：*{title}*
> 阅读版本：{venue}

---

## 基本信息

| 项目 | 内容 |
| ---- | ---- |
| **标题** | {title} |
| **作者** |  |
| **年份** | {year} |
| **会议/期刊** |  |
| **代码/数据** |  |
| **关键词** |  |

---

## 摘要（Abstract）

### 主要目的

### 方法

### 结果

### 结论

---

## 引言（Introduction）

### 研究背景与问题

### 现有研究与其不足

### 主要贡献

---

## 方法（Method）

### 一、威胁模型

### 二、系统总览

### 三、核心组件

### 四、完整算法

---

## 实验（Experiments）

### 实验设计

### RQ1：

---

## 结论（Conclusion）

### 主要结论

### 研究贡献

### 局限与未来工作

---

## 个人反思（Personal Reflection）

### 论文优点

### 论文缺点

### 论文难点

### 与自己研究的关联

### 这篇论文最有价值的点

### 对当前课题有什么启发
"""


def cmd_new(args: argparse.Namespace) -> int:
    note_id = args.id.strip()
    if not note_id:
        die("--id must not be empty")
    pdf = Path(args.pdf).expanduser().resolve() if args.pdf else None
    if pdf is not None and not pdf.is_file():
        die(f"PDF not found: {pdf}")

    title = sanitize_title(args.title)
    short_name = args.short_name or title.split()[0].rstrip(":")
    out_dir = resolve_out(pdf, args.out, note_id)
    note_dir = out_dir if out_dir.name == note_id else out_dir / note_id
    md_path = note_dir / f"{note_id}_{title}.md"

    if note_dir.exists() and not args.force:
        if md_path.exists():
            die(f"{md_path} already exists (use --force to overwrite)")
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "image").mkdir(exist_ok=True)

    if not md_path.exists() or args.force:
        md_path.write_text(
            SKELETON.format(
                short_name=short_name,
                title=title,
                venue=args.venue,
                year=args.year,
            ),
            encoding="utf-8",
        )

    print(f"note folder : {note_dir}")
    print(f"note file   : {md_path}")
    print(f"image folder: {note_dir / 'image'}")
    print("next        : extract text/figures, then write the note body")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", required=True, help="note id, e.g. 0004C")
    parser.add_argument("--title", required=True, help="paper title (sanitized automatically)")
    parser.add_argument("--pdf", help="source PDF; used to pick the output folder")
    parser.add_argument("--out", help="explicit output directory (the <id>/ folder is created inside it)")
    parser.add_argument("--short-name", help="short name used in the H1 title, e.g. AttriGuard")
    parser.add_argument("--venue", default="", help="venue/year line, e.g. 'USENIX Security 26 (PDF, 21 pages)'")
    parser.add_argument("--year", default="", help="publication year for the info table")
    parser.add_argument("--force", action="store_true", help="overwrite an existing note file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return cmd_new(args)


if __name__ == "__main__":
    sys.exit(main())
