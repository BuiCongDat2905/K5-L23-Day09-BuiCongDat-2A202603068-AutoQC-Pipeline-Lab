"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]
    conf_min = so["conf"]
    min_area_px = so["min_area_px"]
    fp_conf = so["fp_conf"]
    iou_missing = so["iou_missing"]
    iou_match = so["iou_match"]
    iou_loose = so["iou_loose"]
    n_classes = len(ds.classes)

    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    for img_path in ds.image_files():
        stem = img_path.stem
        if stem not in preds:
            continue
        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue
        size = ds.image_size(stem)
        if size is None:
            continue
        W, H = size

        labels = []                       # [(line_no, cls, box)]
        for line_no, text in raw_lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            if not 0 <= cls < n_classes:
                continue
            labels.append((line_no, cls, (cx, cy, w, h)))

        rows = preds[stem] or []
        # dự đoán đủ tin cậy + đủ lớn: dùng cho MISSING / LOOSE / WRONG_CLASS
        strong = []
        for r in rows:
            p_cls, p_conf, cx, cy, w, h = r[0], r[1], r[2], r[3], r[4], r[5]
            if p_conf < conf_min:
                continue
            if (w * W) * (h * H) < min_area_px:
                continue
            strong.append((int(p_cls), (cx, cy, w, h), float(p_conf)))

        for p_cls, box, p_conf in strong:
            cands = [(l_cls, iou_xywh(box, l_box)) for _, l_cls, l_box in labels
                     if iou_xywh(box, l_box) >= iou_missing]
            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    "model thấy vật mà nhãn không có box", extra={"conf": p_conf}))
                continue
            same = [iou for l_cls, iou in cands if l_cls == p_cls]
            if same:
                best_same = max(same)
                if best_same < iou_loose:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        "đúng vật nhưng box lỏng/lệch", extra={"iou": round(best_same, 4)}))
                continue
            best_other = max(iou for _, iou in cands)
            if best_other >= iou_match:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    "model đoán lớp khác cho cùng vật", extra={"iou": round(best_other, 4)}))

        # dự đoán yếu hơn (>= fp_conf) vẫn đủ để bác bỏ FALSE_POS
        weak_boxes = [(r[2], r[3], r[4], r[5]) for r in rows if r[1] >= fp_conf]
        for line_no, _, l_box in labels:
            if all(iou_xywh(l_box, p_box) < iou_missing for p_box in weak_boxes):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    "box nhãn không khớp dự đoán nào của model", line_no))

    return issues
