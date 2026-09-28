#!/usr/bin/env python3
"""PDF ingestion helper for paper notes.

Wraps the Poppler tools (pdfinfo / pdftotext / pdftoppm / pdfimages) so that
text, page renders, embedded images and figure crops can be produced through
one predictable interface.

Commands
--------
info      <pdf>
text      <pdf> -o <dir> [--pages 3-7,9] [--layout]
captions  <pdf> [--json]
pages     <pdf> -o <dir> [--pages 3-7] [--dpi 150]
images    <pdf> -o <dir> [--pages 3-7] [--min-px 120] [--min-bytes 4000]
crop      <pdf> -o <out.png> --page 4 --bbox x0,y0,x1,y1 [--dpi 300] [--pad 8] [--trim]
crop      <pdf> -o <out.png> --above-caption 3 [--dpi 300] [--pad 8] [--trim]
crop      <pdf> -o <out.png> --below-caption 3 [--dpi 300] [--pad 8] [--trim]

Page numbers are 1-based. Coordinates are PDF points (1/72 inch), the same
unit used by `pdftotext -bbox-layout`.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CAPTION_RE = re.compile(
    r"^\s*(?P<kind>Fig(?:ure)?s?\.?|Tab(?:le)?s?\.?|[图圖表])\s*(?P<num>\d+)\s*[:.]\s*\S",
    re.IGNORECASE,
)
PAGE_RE = re.compile(r"<page\b([^>]*)>(.*?)</page>", re.DOTALL)
LINE_RE = re.compile(r"<line\b([^>]*)>(.*?)</line>", re.DOTALL)
WORD_RE = re.compile(r"<word\b([^>]*)>(.*?)</word>", re.DOTALL)
ATTR_RE = re.compile(r"([A-Za-z]+)=\"([^\"]*)\"")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Windows consoles default to a legacy codepage (e.g. cp936); force UTF-8 so
# paper titles and captions never crash the process.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def die(message: str) -> "None":
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(2)


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        die(
            f"'{name}' not found on PATH. Install Poppler "
            "(pdftotext/pdftoppm/pdfimages/pdfinfo) and retry."
        )
    return path


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = run(cmd)
    if proc.returncode != 0:
        die(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    pages: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            first, last = int(start), int(end)
            pages.update(range(first, last + 1))
        else:
            pages.add(int(chunk))
    chosen = sorted(p for p in pages if 1 <= p <= total)
    if not chosen:
        die(f"--pages {spec!r} selects nothing in a {total}-page document")
    return chosen


def pdf_info(pdf: Path) -> dict[str, str]:
    proc = run_checked([tool("pdfinfo"), str(pdf)])
    info: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            info[key.strip()] = value.strip()
    return info


def page_count(pdf: Path) -> int:
    raw = pdf_info(pdf).get("Pages", "")
    if not raw.isdigit():
        die(f"could not read page count for {pdf}")
    return int(raw)


def page_size(pdf: Path) -> tuple[float, float]:
    raw = pdf_info(pdf).get("Page size", "")
    match = re.search(r"([\d.]+)\s*x\s*([\d.]+)", raw)
    if not match:
        return 612.0, 792.0
    return float(match.group(1)), float(match.group(2))


def parse_layout(pdf: Path) -> list[dict]:
    """Return [{page, width, height, lines: [{text, bbox}]}] using -bbox-layout.

    Parsed with regexes rather than an XML parser: pdftotext emits raw control
    characters inside <word> elements, which makes the document ill-formed.
    """
    proc = run_checked([tool("pdftotext"), "-bbox-layout", str(pdf), "-"])
    document = CTRL_RE.sub("", proc.stdout)
    pages = []
    for page_index, (page_attrs, page_body) in enumerate(PAGE_RE.findall(document), start=1):
        attrs = dict(ATTR_RE.findall(page_attrs))
        lines = []
        for line_attrs, line_body in LINE_RE.findall(page_body):
            line_attr = dict(ATTR_RE.findall(line_attrs))
            words = []
            boxes: list[list[float]] = []
            for word_attrs, word_text in WORD_RE.findall(line_body):
                text = html.unescape(word_text).strip()
                if not text:
                    continue
                word_attr = dict(ATTR_RE.findall(word_attrs))
                words.append(text)
                boxes.append(
                    [
                        float(word_attr.get("xMin", 0.0)),
                        float(word_attr.get("yMin", 0.0)),
                        float(word_attr.get("xMax", 0.0)),
                        float(word_attr.get("yMax", 0.0)),
                    ]
                )
            text = " ".join(w for w in words if w)
            if not text:
                continue
            if boxes:
                bbox = [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
            else:
                bbox = [
                    float(line_attr.get("xMin", 0.0)),
                    float(line_attr.get("yMin", 0.0)),
                    float(line_attr.get("xMax", 0.0)),
                    float(line_attr.get("yMax", 0.0)),
                ]
            lines.append({"text": text, "bbox": bbox})
        pages.append(
            {
                "page": page_index,
                "width": float(attrs.get("width", 0.0)),
                "height": float(attrs.get("height", 0.0)),
                "lines": lines,
            }
        )
    return pages


def content_lines(page: dict) -> list[dict]:
    """Drop running heads and footers so they never merge with a figure block."""
    top = 60.0
    bottom = page["height"] - 45.0
    return [ln for ln in page["lines"] if ln["bbox"][1] >= top and ln["bbox"][3] <= bottom]


def caption_block(lines: list[dict], anchor: dict) -> list[float]:
    """Extend a caption line over its continuation lines (same column, tight spacing)."""
    x0, y0, x1, y1 = anchor["bbox"]
    bottom = y1
    changed = True
    while changed:
        changed = False
        for line in lines:
            lx0, ly0, lx1, ly1 = line["bbox"]
            if not (ly0 >= bottom - 1.0 and ly0 - bottom < 6.0):
                continue
            overlap = min(lx1, x1) - max(lx0, x0)
            if overlap > 0.5 * max(1.0, lx1 - lx0):
                bottom = ly1
                changed = True
    return [x0, y0, x1, bottom]


def find_captions(pdf: Path, pages: list[dict] | None = None) -> list[dict]:
    pages = pages if pages is not None else parse_layout(pdf)
    captions = []
    for page in pages:
        lines = content_lines(page)
        for line in lines:
            match = CAPTION_RE.match(line["text"])
            if not match:
                continue
            captions.append(
                {
                    "page": page["page"],
                    "kind": match.group("kind").rstrip("."),
                    "number": int(match.group("num")),
                    "bbox": line["bbox"],
                    "block_bbox": caption_block(lines, line),
                    "text": line["text"][:200],
                }
            )
    return captions


def is_figure_caption(caption: dict) -> bool:
    kind = caption["kind"].lower()
    return kind.startswith(("fig", "图", "圖"))


def column_bounds(page: dict, caption_bbox: list[float]) -> tuple[list[dict], float, float]:
    """Pick the column that holds this caption and return its text extent."""
    lines = content_lines(page)
    x0, _, x1, _ = caption_bbox
    if (x1 - x0) > 0.6 * page["width"]:
        return lines, x0, x1
    mid = page["width"] / 2.0
    gutter = 12.0
    if x0 < mid:
        selected = [ln for ln in lines if ln["bbox"][0] < mid and ln["bbox"][2] <= mid + gutter]
    else:
        selected = [ln for ln in lines if ln["bbox"][0] >= mid - gutter]
    if not selected:
        return lines, x0, x1
    left = min(min(ln["bbox"][0], x0) for ln in selected)
    right = max(max(ln["bbox"][2], x1) for ln in selected)
    return selected, left, right


def body_run_lines(lines: list[dict], col_left: float, col_width: float) -> list[dict]:
    """Lines that belong to a run of running text (>=3 evenly spaced wide lines)."""
    candidates = []
    for line in sorted(lines, key=lambda ln: ln["bbox"][1]):
        x0, y0, x1, y1 = line["bbox"]
        wide = (x1 - x0) >= 0.55 * col_width
        flush = (x0 - col_left) <= 15.0
        normal_size = (y1 - y0) <= 14.0
        if wide and flush and normal_size:
            candidates.append(line)
    runs: list[list[dict]] = []
    current: list[dict] = []
    for line in candidates:
        if current and 1.0 <= line["bbox"][1] - current[-1]["bbox"][3] <= 8.0:
            current.append(line)
        else:
            if len(current) >= 3:
                runs.append(current)
            current = [line]
    if len(current) >= 3:
        runs.append(current)
    return [line for run in runs for line in run]


def overlaps_horizontal(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[1]) - max(a[0], b[0]) > 0.0


def region_for_caption(pdf: Path, index: int, side: str) -> tuple[int, list[float]]:
    """Crop region around one caption: the block 'above' or 'below' its caption text."""
    pages = parse_layout(pdf)
    captions = find_captions(pdf, pages)
    if not 1 <= index <= len(captions):
        die(f"caption index {index} is out of range (1..{len(captions)})")
    caption = captions[index - 1]
    page = next(p for p in pages if p["page"] == caption["page"])
    lines, left, right = column_bounds(page, caption["bbox"])
    column = [left, right]
    col_width = max(1.0, right - left)
    body = body_run_lines(lines, left, col_width)

    if side == "above":
        limit = caption["bbox"][1]
        bounds = [54.0]
        bounds += [ln["bbox"][3] for ln in body if ln["bbox"][3] < limit - 1.0]
        bounds += [
            other["block_bbox"][3]
            for other in captions
            if other is not caption
            and other["page"] == caption["page"]
            and other["block_bbox"][3] < limit - 1.0
            and overlaps_horizontal(other["block_bbox"], column)
        ]
        top = max(bounds) + 4.0
        bottom = limit - 2.0
    else:
        limit = caption["block_bbox"][3]
        bounds = [page["height"] - 60.0]
        bounds += [ln["bbox"][1] for ln in body if ln["bbox"][1] > limit + 1.0]
        bounds += [
            other["bbox"][1]
            for other in captions
            if other is not caption
            and other["page"] == caption["page"]
            and other["bbox"][1] > limit + 1.0
            and overlaps_horizontal(other["block_bbox"], column)
        ]
        top = limit + 4.0
        bottom = min(bounds) - 4.0
    if bottom <= top:
        die(
            f"no {'space above' if side == 'above' else 'space below'} caption {index} "
            "(the page layout defeats the heuristic); pass an explicit --bbox instead"
        )
    return caption["page"], [left, top, right, bottom]


def cmd_info(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    info = pdf_info(pdf)
    total = page_count(pdf)
    width, height = page_size(pdf)
    sample = run([tool("pdftotext"), "-f", "1", "-l", "1", str(pdf), "-"])
    chars = len(sample.stdout.strip())
    print(f"file            : {pdf}")
    print(f"pages           : {total}")
    print(f"page size (pt)  : {width:g} x {height:g}")
    print(f"producer        : {info.get('Producer', '?')}")
    print(f"page-1 text     : {chars} chars extracted")
    if chars < 200:
        print("note            : little or no text layer; expect a scanned PDF")
        print("                  -> render pages and read them as images (see 'pages')")
    captions = find_captions(pdf)
    figures = [c for c in captions if c["kind"].lower().startswith(("fig", "图", "圖"))]
    tables = [c for c in captions if c["kind"].lower().startswith(("tab", "表"))]
    print(f"captions        : {len(figures)} figure-like, {len(tables)} table-like")
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    total = page_count(pdf)
    pages = parse_pages(args.pages, total)
    chunks = []
    for page in pages:
        flags = ["-layout"] if args.layout else []
        proc = run_checked(
            [tool("pdftotext"), *flags, "-f", str(page), "-l", str(page), str(pdf), "-"]
        )
        body = proc.stdout.replace("\x0c", "").strip("\n")
        (out / f"page-{page:03d}.txt").write_text(body, encoding="utf-8")
        chunks.append(f"\n<!-- ===== page {page} ===== -->\n\n{body}\n")
    combined = out / "full-text.md"
    combined.write_text("".join(chunks), encoding="utf-8")
    print(f"wrote {combined} ({len(pages)} pages)")
    return 0


def cmd_captions(args: argparse.Namespace) -> int:
    captions = find_captions(Path(args.pdf))
    if args.json:
        print(json.dumps(captions, ensure_ascii=False, indent=2))
        return 0
    for index, cap in enumerate(captions, start=1):
        x0, y0, x1, y1 = cap["bbox"]
        print(
            f"[{index:3d}] p{cap['page']:<3d} {cap['kind']} {cap['number']:<3d} "
            f"bbox=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}) "
            f"block=({cap['block_bbox'][1]:.1f}..{cap['block_bbox'][3]:.1f})  {cap['text'][:80]}"
        )
    return 0


def render(
    pdf: Path,
    page: int,
    dpi: int,
    crop: tuple[int, int, int, int] | None,
    prefix: Path,
) -> Path:
    cmd = [tool("pdftoppm"), "-png", "-r", str(dpi), "-f", str(page), "-l", str(page)]
    if crop:
        x, y, w, h = crop
        cmd += ["-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h)]
    cmd += [str(pdf), str(prefix)]
    run_checked(cmd)
    produced = sorted(prefix.parent.glob(prefix.name + "*.png"))
    if not produced:
        die("pdftoppm produced no output")
    return produced[0]


def cmd_pages(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    total = page_count(pdf)
    for page in parse_pages(args.pages, total):
        with tempfile.TemporaryDirectory() as tmp:
            produced = render(pdf, page, args.dpi, None, Path(tmp) / "page")
            target = out / f"page-{page:03d}.png"
            shutil.copyfile(produced, target)
        print(f"wrote {target}")
    return 0


def image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError:
        return 0, 0
    with Image.open(path) as img:
        return img.size


def cmd_images(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    total = page_count(pdf)
    pages = parse_pages(args.pages, total)
    manifest = []
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "img"
        cmd = [tool("pdfimages"), "-png", "-p", "-f", str(pages[0]), "-l", str(pages[-1]), str(pdf), str(prefix)]
        run_checked(cmd)
        for candidate in sorted(prefix.parent.glob(prefix.name + "-*.png")):
            name = candidate.stem
            parts = name.split("-")
            page = int(parts[-2])
            index = int(parts[-1])
            if page not in pages:
                continue
            size = candidate.stat().st_size
            width, height = image_size(candidate)
            if width and max(width, height) < args.min_px:
                continue
            if size < args.min_bytes:
                continue
            target = out / f"p{page:03d}-{index:03d}.png"
            shutil.copyfile(candidate, target)
            manifest.append(
                {
                    "page": page,
                    "index": index,
                    "file": target.name,
                    "width": width,
                    "height": height,
                    "bytes": size,
                }
            )
    (out / "embedded-images.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"extracted {len(manifest)} embedded raster images into {out}")
    print("NOTE: most paper figures are vector art; if this folder looks like")
    print("      fragments or icons, use the 'crop' command on a page render.")
    return 0


def cmd_crop(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    selectors = [
        args.bbox is not None,
        args.above_caption is not None,
        args.below_caption is not None,
    ]
    if sum(selectors) != 1:
        die("give exactly one of --bbox, --above-caption or --below-caption")
    page = args.page
    if args.above_caption is not None:
        page, bbox = region_for_caption(pdf, args.above_caption, "above")
    elif args.below_caption is not None:
        page, bbox = region_for_caption(pdf, args.below_caption, "below")
    else:
        try:
            bbox = tuple(float(v) for v in args.bbox.split(","))
        except ValueError:
            die("--bbox expects four comma-separated numbers: x0,y0,x1,y1")
        if len(bbox) != 4:
            die("--bbox expects four comma-separated numbers: x0,y0,x1,y1")
    if page is None:
        die("--page is required with --bbox")
    total = page_count(pdf)
    if not 1 <= page <= total:
        die(f"--page {page} is out of range (1..{total})")

    width, height = page_size(pdf)
    x0, y0, x1, y1 = bbox
    x0 = max(0.0, min(x0, x1) - args.pad)
    y0 = max(0.0, min(y0, y1) - args.pad)
    x1 = min(width, max(x0, x1) + args.pad)
    y1 = min(height, max(y0, y1) + args.pad)
    scale = args.dpi / 72.0
    crop = (
        int(round(x0 * scale)),
        int(round(y0 * scale)),
        max(1, int(round((x1 - x0) * scale))),
        max(1, int(round((y1 - y0) * scale))),
    )
    with tempfile.TemporaryDirectory() as tmp:
        produced = render(pdf, page, args.dpi, crop, Path(tmp) / "crop")
        shutil.copyfile(produced, out)
    if args.trim:
        trim_whitespace(out)
    size = image_size(out)
    print(f"wrote {out}  page={page}  px={size[0]}x{size[1]}  dpi={args.dpi}")
    print("VERIFY this image visually before using it in a note.")
    return 0


def trim_whitespace(path: Path, threshold: int = 245) -> None:
    try:
        from PIL import Image
    except ImportError:
        print("[WARN] Pillow not available; --trim ignored", file=sys.stderr)
        return
    with Image.open(path) as img:
        gray = img.convert("L")
        mask = gray.point(lambda v: 0 if v > threshold else 255)
        box = mask.getbbox()
        if not box:
            return
        cropped = img.crop(box)
        cropped.save(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="page count, page size, text-layer check, caption counts")
    p_info.add_argument("pdf")
    p_info.set_defaults(func=cmd_info)

    p_text = sub.add_parser("text", help="extract text per page plus a combined full-text.md")
    p_text.add_argument("pdf")
    p_text.add_argument("-o", "--out", required=True)
    p_text.add_argument("--pages", help="e.g. 1-4,9 (default: all)")
    p_text.add_argument("--layout", action="store_true", help="keep the visual layout (-layout)")
    p_text.set_defaults(func=cmd_text)

    p_cap = sub.add_parser("captions", help="list Figure/Table captions with page and bbox")
    p_cap.add_argument("pdf")
    p_cap.add_argument("--json", action="store_true")
    p_cap.set_defaults(func=cmd_captions)

    p_pages = sub.add_parser("pages", help="render whole pages to PNG")
    p_pages.add_argument("pdf")
    p_pages.add_argument("-o", "--out", required=True)
    p_pages.add_argument("--pages", help="e.g. 1-4,9 (default: all)")
    p_pages.add_argument("--dpi", type=int, default=150)
    p_pages.set_defaults(func=cmd_pages)

    p_img = sub.add_parser("images", help="extract embedded raster images")
    p_img.add_argument("pdf")
    p_img.add_argument("-o", "--out", required=True)
    p_img.add_argument("--pages")
    p_img.add_argument("--min-px", type=int, default=120, help="skip images smaller than this on both sides")
    p_img.add_argument("--min-bytes", type=int, default=4000)
    p_img.set_defaults(func=cmd_images)

    p_crop = sub.add_parser("crop", help="crop a figure region out of a page render")
    p_crop.add_argument("pdf")
    p_crop.add_argument("-o", "--out", required=True)
    p_crop.add_argument("--page", type=int)
    p_crop.add_argument("--bbox", help="x0,y0,x1,y1 in PDF points")
    p_crop.add_argument("--above-caption", type=int, help="crop the area above caption N (see 'captions')")
    p_crop.add_argument("--below-caption", type=int, help="crop the area below caption N (see 'captions')")
    p_crop.add_argument("--dpi", type=int, default=300)
    p_crop.add_argument("--pad", type=float, default=6.0, help="padding in PDF points")
    p_crop.add_argument("--trim", action="store_true", help="trim uniform white margins afterwards")
    p_crop.set_defaults(func=cmd_crop)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
