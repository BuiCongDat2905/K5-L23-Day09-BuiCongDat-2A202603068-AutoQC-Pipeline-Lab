"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"CORRUPT_IMAGE", "BAD_SIZE", "LEAK_TEST"}


def _is_remove(code: str) -> bool:
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE")


def _remove_image(ds, stem: str) -> None:
    p = ds.image_path(stem)
    if p is not None and p.exists():
        p.unlink()
    lab = ds.label_path(stem)
    if lab.exists():
        lab.unlink()


def _clip(box):
    """Cắt box (cx, cy, w, h) về [0,1]. None nếu không còn diện tích."""
    cx, cy, w, h = box
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= 0 or nh <= 0:
        return None
    return ((x1 + x2) / 2, (y1 + y2) / 2, nw, nh)


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]
    if not errors:
        return fixes

    # 1) cấp file: xoá ảnh (làm trước, để issue của ảnh đã xoá không làm gì)
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            _remove_image(ds, i.image)
            removed.add(i.image)
            fixes.append({"image": i.image, "line": i.line, "action": "remove_image",
                          "before": f"{i.image} (+ nhãn)", "after": "(đã xoá khỏi dataset)"})

    # 2) data.yaml: ghi lại names đúng cfg["classes"]
    for i in errors:
        if i.code == "BAD_CLASS_NAME":
            before = ds.yaml_path.read_text(encoding="utf-8") if ds.yaml_path.exists() else ""
            data = yaml.safe_load(before) or {} if before else {}
            data["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append({"image": "data.yaml", "line": None, "action": "rename_classes",
                          "before": before.strip() or "(không có file)",
                          "after": ", ".join(cfg["classes"])})
            break

    # 3) ảnh chưa có nhãn: không bịa nhãn, chỉ ghi log chuyển người
    for i in errors:
        if i.code == "MISSING_LABEL_FILE":
            fixes.append({"image": i.image, "line": None, "action": "needs_label",
                          "before": "(không có file)", "after": "chuyển người gán"})

    # 4) cấp dòng: gom theo file, ghi lại MỘT lần (giữ số dòng gốc, kể cả dòng trống)
    drop: dict[str, set[int]] = defaultdict(set)
    clip: dict[str, set[int]] = defaultdict(set)
    for i in errors:
        if i.image in removed or i.line is None:
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(i.line)
        elif i.code in CLIP_CODES:
            clip[i.image].add(i.line)

    for stem in sorted(set(drop) | set(clip)):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8", errors="replace").splitlines()
        kept, changes = [], []
        for line_no, text in enumerate(original, 1):
            if line_no in drop[stem]:
                changes.append({"image": stem, "line": line_no, "action": "drop_line",
                                "before": text, "after": "(xoá)"})
                continue
            if line_no in clip[stem]:
                try:
                    cls, cx, cy, w, h = parse_yolo_line(text)
                except ValueError:
                    changes.append({"image": stem, "line": line_no, "action": "drop_line",
                                    "before": text, "after": "(xoá)"})
                    continue
                clipped = _clip((cx, cy, w, h))
                if clipped is None:                     # cắt xong không còn diện tích
                    changes.append({"image": stem, "line": line_no, "action": "drop_line",
                                    "before": text, "after": "(xoá)"})
                    continue
                new_text = f"{cls} {clipped[0]} {clipped[1]} {clipped[2]} {clipped[3]}"
                changes.append({"image": stem, "line": line_no, "action": "clip_box",
                                "before": text, "after": new_text})
                kept.append(new_text)
                continue
            kept.append(text)
        path.write_text("".join(l + "\n" for l in kept), encoding="utf-8")
        fixes.extend(changes)

    return fixes
