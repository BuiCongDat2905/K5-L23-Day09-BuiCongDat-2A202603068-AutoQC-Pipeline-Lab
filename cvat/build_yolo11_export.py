#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chuan bi nguyen lieu CVAT cho phan thuong +2.

- Doc 20 anh uu tien dau tien tu submission/reports/05_review_queue.csv.
- Dong goi nhan YOLO thanh zip dung dinh dang YOLO 1.1 (CVAT import duoc).
- Doi chieu so box co width_px < 20 voi check BOX_TINY cua pipeline.

Script chi DOC tu submission/reports/ va work/run/ds/, chi GHI trong cvat/.
Chay tu thu muc goc repo:
    .venv\\Scripts\\python.exe -X utf8 cvat/build_yolo11_export.py
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Optional

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CVAT_DIR = ROOT / "cvat"
REPORTS_DIR = ROOT / "submission" / "reports"
DS_DIR = ROOT / "work" / "run" / "ds"
IMAGES_DIR = DS_DIR / "images"
LABELS_DIR = DS_DIR / "labels"

REVIEW_QUEUE = REPORTS_DIR / "05_review_queue.csv"
ERROR_LIST = REPORTS_DIR / "02_error_list_v1.csv"

OUT_ZIP = CVAT_DIR / "yolo11_priority20.zip"
OUT_JSON = CVAT_DIR / "box_tiny_vs_cvat.json"

CLASS_NAMES = ["car", "person", "truck", "bus"]
NUM_IMAGES = 20
TINY_WIDTH_PX = 20

# Thu tu co dinh trong zip de moi lan chay cho cung mot ket qua.
ZIP_DATE_TIME = (2026, 1, 1, 0, 0, 0)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Doc CSV bang module csv (message co chua dau phay)."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def priority_images(limit: int = NUM_IMAGES) -> list[str]:
    """Lay `limit` gia tri cot image dau tien cua review queue."""
    names: list[str] = []
    for row in read_csv_rows(REVIEW_QUEUE):
        name = (row.get("image") or "").strip()
        if not name:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def box_tiny_counts() -> dict[str, int]:
    """Dem so dong code == BOX_TINY theo tung anh."""
    counts: dict[str, int] = {}
    for row in read_csv_rows(ERROR_LIST):
        if (row.get("code") or "").strip() != "BOX_TINY":
            continue
        image = (row.get("image") or "").strip()
        if not image:
            continue
        counts[image] = counts.get(image, 0) + 1
    return counts


def find_image(stem: str) -> Optional[Path]:
    """Anh cua stem, uu tien .jpg roi den .png."""
    for ext in (".jpg", ".png"):
        candidate = IMAGES_DIR / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def load_label_bytes(stem: str) -> Optional[bytes]:
    """Byte nhan YOLO nguyen van, None neu thieu file."""
    path = LABELS_DIR / f"{stem}.txt"
    if not path.is_file():
        return None
    return path.read_bytes()


def parse_boxes(text: str) -> list[tuple[float, float, float, float]]:
    """Tra ve (cx, cy, w, h) chuan hoa cua tung dong hop le."""
    boxes: list[tuple[float, float, float, float]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            cx, cy, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        boxes.append((cx, cy, w, h))
    return boxes


def write_zip(entries: list[tuple[str, bytes]]) -> None:
    """Ghi zip on dinh: dung thu tu truyen vao, timestamp co dinh."""
    tmp = OUT_ZIP.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    tmp.replace(OUT_ZIP)


def main() -> int:
    CVAT_DIR.mkdir(parents=True, exist_ok=True)

    images = priority_images()
    tiny_by_image = box_tiny_counts()

    report_rows: list[dict[str, object]] = []
    zip_entries: list[tuple[str, bytes]] = []
    train_lines: list[str] = []

    total_boxes = 0
    total_tiny = 0
    total_pipeline_tiny = 0
    missing_labels: list[str] = []
    missing_images: list[str] = []

    for stem in images:
        label_bytes = load_label_bytes(stem)
        train_lines.append(f"obj_train_data/{stem}.jpg")

        image_path = find_image(stem)
        image_width: Optional[int] = None
        if image_path is None:
            missing_images.append(stem)
        else:
            with Image.open(image_path) as img:
                image_width = int(img.width)

        if label_bytes is None:
            missing_labels.append(stem)
            boxes_total: Optional[int] = None
            tiny_total: Optional[int] = None
        else:
            boxes = parse_boxes(label_bytes.decode("utf-8", errors="replace"))
            boxes_total = len(boxes)
            if image_width is None:
                tiny_total = None
            else:
                tiny_total = sum(
                    1 for _cx, _cy, w, _h in boxes if w * image_width < TINY_WIDTH_PX
                )
            zip_entries.append((f"obj_train_data/{stem}.txt", label_bytes))
            total_boxes += boxes_total
            if tiny_total is not None:
                total_tiny += tiny_total

        pipeline_tiny = tiny_by_image.get(stem, 0)
        total_pipeline_tiny += pipeline_tiny

        report_rows.append(
            {
                "image": stem,
                "boxes_total": boxes_total,
                "boxes_width_lt_20": tiny_total,
                "box_tiny_pipeline": pipeline_tiny,
            }
        )

    head_entries: list[tuple[str, bytes]] = [
        ("obj.names", ("\n".join(CLASS_NAMES) + "\n").encode("utf-8")),
        (
            "obj.data",
            (
                f"classes = {len(CLASS_NAMES)}\n"
                "train = train.txt\n"
                "names = obj.names\n"
                "backup = backup/\n"
            ).encode("utf-8"),
        ),
        ("train.txt", ("\n".join(train_lines) + "\n").encode("utf-8")),
    ]
    write_zip(head_entries + zip_entries)

    payload = {
        "filter": "width < 20",
        "images": report_rows,
        "totals": {
            "images": len(report_rows),
            "boxes_total": total_boxes,
            "boxes_width_lt_20": total_tiny,
            "box_tiny_pipeline": total_pipeline_tiny,
        },
    }
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"zip    : {OUT_ZIP} ({len(images)} anh, {len(zip_entries)} file nhan)")
    print(f"json   : {OUT_JSON}")
    print(
        "totals : boxes_total={0} boxes_width_lt_20={1} box_tiny_pipeline={2}".format(
            total_boxes, total_tiny, total_pipeline_tiny
        )
    )
    if missing_labels:
        print(f"missing labels: {', '.join(missing_labels)}")
    if missing_images:
        print(f"missing images: {', '.join(missing_images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
