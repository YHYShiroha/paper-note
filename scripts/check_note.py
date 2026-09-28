#!/usr/bin/env python3
"""Check a finished note folder against the naming and image conventions.

Usage
-----
  check_note.py <note-folder-or-md-file>

Verifies:
  * the folder holds exactly one Markdown file, named <id>_<title>.md
  * an image/ folder exists
  * every image reference is relative, under image/, and forward-slashed
  * the alt text inside ![alt](path) equals the file name without extension
  * image files are named image-1 .. image-N in document order, no gaps
  * every file in image/ is actually referenced

Exit code is 1 when at least one error is reported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
NAME_RE = re.compile(r"^image-(?P<num>\d+)\.(?P<ext>png|jpg|jpeg|gif|webp)$", re.IGNORECASE)
ILLEGAL = re.compile(r'[\\/*?"<>|]')

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def check(target: Path) -> Report:
    report = Report()
    if target.is_file():
        note_dir = target.parent
        md_files = [target]
    else:
        note_dir = target
        md_files = sorted(p for p in note_dir.glob("*.md") if p.is_file())

    if not note_dir.is_dir():
        report.error(f"not a folder or file: {target}")
        return report

    note_id = note_dir.name
    image_dir = note_dir / "image"

    if len(md_files) != 1:
        report.error(f"expected exactly one .md file in {note_dir}, found {len(md_files)}")
    if not image_dir.is_dir():
        report.error(f"missing image folder: {image_dir}")
    if not md_files:
        return report

    md = md_files[0]
    if ILLEGAL.search(md.name):
        report.error(f"note file name contains illegal characters: {md.name}")
    if not md.stem.startswith(f"{note_id}_"):
        report.error(f"note file '{md.name}' does not start with '{note_id}_'")

    text = md.read_text(encoding="utf-8")
    refs = list(IMAGE_RE.finditer(text))
    if not refs:
        report.warn("no image references found in the note")

    seen: list[str] = []
    for match in refs:
        alt = match.group("alt").strip()
        raw_path = match.group("path").strip()
        if "://" in raw_path:
            report.error(f"remote image reference is not allowed: {raw_path}")
            continue
        if raw_path.startswith("/") or re.match(r"^[A-Za-z]:", raw_path):
            report.error(f"absolute image path is not allowed: {raw_path}")
            continue
        if "\\" in raw_path:
            report.error(f"use forward slashes in image paths: {raw_path}")
            continue
        if not raw_path.startswith("image/"):
            report.error(f"image must live under image/: {raw_path}")
            continue
        name = Path(raw_path).name
        stem = Path(name).stem
        if alt != stem:
            report.error(f"alt text '{alt}' does not match file name '{name}'")
        if not NAME_RE.match(name):
            report.error(f"image file must be named image-<n>.<ext>: {name}")
        resolved = (note_dir / raw_path).resolve()
        if not resolved.is_file():
            report.error(f"referenced image is missing: {raw_path}")
        seen.append(stem.lower())

    numbered = [s for s in seen if s.startswith("image-")]
    if numbered:
        expected = [f"image-{i}" for i in range(1, len(numbered) + 1)]
        if numbered != expected:
            report.error(f"image numbering must be sequential in document order; got {numbered}")
    else:
        report.note("no image-<n> files referenced")

    if image_dir.is_dir():
        on_disk = sorted(p.stem.lower() for p in image_dir.iterdir() if p.is_file())
        for stem in on_disk:
            if stem not in seen:
                report.error(f"file in image/ is never referenced: {stem}")
        stray = [s for s in on_disk if not s.startswith("image-")]
        if stray:
            report.error(f"unexpected file names in image/: {stray}")
        report.note(f"image/ holds {len(on_disk)} file(s); note references {len(numbered)}")

    return report


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_note.py <note-folder-or-md-file>", file=sys.stderr)
        return 2
    report = check(Path(sys.argv[1]).expanduser())
    for item in report.errors:
        print(f"ERROR   {item}")
    for item in report.warnings:
        print(f"WARN    {item}")
    for item in report.notes:
        print(f"OK      {item}")
    if report.errors:
        print(f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"\nOK: conventions satisfied ({len(report.warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
