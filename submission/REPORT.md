# Báo cáo Day 09 — Bùi Công Đạt - 2A202603068


## 1. Kết luận trước
    Pipeline kết luận **Release**: 0 lỗi bắt buộc, 20/202 ảnh còn cảnh báo chưa duyệt (9.90%) < ngưỡng 10%.
Lô vào 224 ảnh thô; cửa vào loại 22 (2 hỏng, 3 quá nhỏ, 8 trùng byte, 4 trùng gần đúng, 5 rò rỉ từ kho test/val),
còn 202 ảnh vào pipeline và 202 ảnh ra dataset. Lý do chính: mọi lỗi bắt buộc đã được máy sửa hoặc chuyển người duyệt,
tỉ lệ cảnh báo còn lại nằm dưới ngưỡng Hold.
## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (gom theo mã lỗi). Cột "ai sửa": **máy** (autofix) hay **người** (hàng đợi); chỉ ghi những mã có mặt trong lô của bạn.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| Mã lỗi | Số | Ai sửa | Vì sao |
|---|---:|---|---|
| `POSSIBLE_MISSING` | 32 | người | model lớn thấy vật mà nhãn thiếu; chỉ cảnh báo vì model cũng có thể sai |
| `POSSIBLE_FALSE_POS` | 29 | người | box nhãn không khớp dự đoán nào; người quyết định xoá hay giữ |
| `POSSIBLE_WRONG_CLASS` | 14 | người | nhãn khác lớp dự đoán; sửa lớp cần người |
| `EMPTY_LABEL` | 12 | người | file nhãn rỗng; người gán lại |
| `POSSIBLE_LOOSE_BOX` | 12 | người | cùng vật, IoU thấp; chỉnh box cần người |
| `BOX_OUT_OF_IMAGE` | 8 | máy | `clip_box`: cắt box về trong ảnh |
| `DUP_IMAGE_EXACT` | 8 | máy (cửa vào) | trùng từng byte; loại ảnh |
| `DUP_BOX` | 7 | máy | `drop_line`: bỏ dòng box lặp |
| `BOX_ASPECT` | 6 | người | check thưởng +3: box dài/hẹp bất thường, WARN |
| `BOX_TINY` | 6 | người | cạnh ngắn < 12 px, WARN |
| `BAD_CLASS_ID` | 6 | máy | `drop_line`: id lớp ngoài 0..3 |
| `MISSING_LABEL_FILE` | 6 | người | `needs_label`: chuyển ảnh sang hàng người gán |
| `LEAK_TEST` | 5 | máy (cửa vào) | trùng ảnh kho test/val; loại để chống rò rỉ |
| `CLASS_RARE` | 4 | người | lớp hiếm (truck/bus) cần soát |
| `BOX_ZERO` | 4 | máy | `drop_line`: box w/h <= 0 |
| `DUP_IMAGE_NEAR` | 4 | máy (cửa vào) | trùng gần đúng theo phash (khoảng cách 0, 6, 10) |
| `BOX_HUGE` | 3 | người | box chiếm > 95% ảnh, WARN |
| `BAD_FORMAT` | 3 | máy | `drop_line`: dòng không đủ 5 cột số |
| `BAD_SIZE` | 3 | máy (cửa vào) | cạnh ngắn < 250 px; loại ảnh |
| `CORRUPT_IMAGE` | 2 | máy (cửa vào) | không mở được ảnh; loại |
| `BAD_CLASS_NAME` | 2 | máy | `rename_classes`: sửa map lớp trong `data.yaml` (1 thay đổi) |

Giải thích hàng đợi (điền đoạn):
```text
05_review_queue.csv xếp ảnh theo trọng số review.weights: NEEDS_LABEL=10 đứng đầu, rồi POSSIBLE_WRONG_CLASS=3,
POSSIBLE_MISSING=2, POSSIBLE_FALSE_POS=2, POSSIBLE_LOOSE_BOX=1.5. Hàng đợi có 104 ảnh nhưng ngân sách chỉ 80,
nên người duyệt 80 ảnh đầu; 24 ảnh còn lại vẫn bị tính vào tỉ lệ cảnh báo của cổng. Trong 80 ảnh đã duyệt,
người thay nhãn cho cả 80 (06_review_log.csv), xử lý được 6 ảnh MISSING_LABEL_FILE và phần lớn cảnh báo ngữ nghĩa;
sau duyệt còn 36 cảnh báo trên 32 ảnh (07_error_list_v3.csv).
```

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
| `duplicates.phash_dist` | 2 | **12** | `DUP_IMAGE_NEAR`: P/R/F1 `1.00 / 0.50 / 0.67` → `1.00 / 0.67 / 0.80` | sweep 2..20: 4–14 cùng F1 0.80, 16 lên 0.91 nhưng bắt đầu loại nhầm ảnh khác trên lô thật; 20 tụt recall 0.33 (bỏ sót trùng thật). Chọn 12 = cuối vùng ổn định, precision giữ 1.00 |
| `second_opinion.conf` | 0.25 | **0.8** | `POSSIBLE_WRONG_CLASS`: `0.56 / 0.83 / 0.67` → `1.00 / 0.83 / 0.91`; `POSSIBLE_MISSING` recall `1.00` → `0.75`; `POSSIBLE_LOOSE_BOX` recall `0.40` → `0.20` | tăng conf lọc bớt cảnh báo rác (precision 1.00), đổi lại bỏ sót vật nhỏ/box lỏng; vẫn dưới trần 0.85 của luật bài |
Một chỗ calibration có thể đánh lừa (điền đoạn):

```text
Calib chỉ có 39 ảnh, trong khi lô thật 224 ảnh. conf=0.8 làm POSSIBLE_LOOSE_BOX recall còn 0.20 và POSSIBLE_MISSING còn 0.75:
nhìn F1 của WRONG_CLASS (0.91) rất đẹp nhưng đổi lại là bỏ sót box lỏng/vật thiếu. Nguy hiểm hơn: kết luận Release
đang sát ngưỡng — 9.90% so với 10%, biên 0.10 điểm phần trăm; chỉ cần lô chấm thêm 1 ảnh cảnh báo là Hold.
Ngoài ra phash=12 loại 22 ảnh ở cửa vào; các cặp DUP_IMAGE_NEAR bị loại có phash 0, 6, 10 — phải mở ảnh xem,
vì phash thấp vẫn có thể là hai ảnh khác nhau (nền giống, vật khác).
```

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) Chứng minh gate chặn (dán nguyên văn):

```text
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
→ kết luận Rework, mã thoát 20, KHÔNG tạo work/exp_nb (không xuất dataset).
Lý do: không có người duyệt nên 6 ảnh MISSING_LABEL_FILE còn nguyên (img_0031, img_0053, img_0126, img_0135,
img_0170, img_0219); 07_error_list_v3.csv của lần chạy này có 120 issue gồm 6 lỗi bắt buộc MISSING_LABEL_FILE.
```

(b) Ít nhất 2 điểm mù, kèm bằng chứng (điền 2–3 ý):

```text
1. Box lỏng nhẹ: POSSIBLE_LOOSE_BOX cần IoU < 0.5; box lệch nhưng IoU >= 0.5 không bị cờ (07_error_list_v3 còn 7 cảnh báo loại này).
2. Nhầm lớp: POSSIBLE_WRONG_CLASS chỉ là WARN; lô này có 14 cảnh báo ở vòng 1, sau máy + người còn 1 — nhưng cổng vẫn có thể Release dù còn nhầm lớp, vì không phải lỗi bắt buộc.
3. Trùng biến đổi mạnh: phash=12 bỏ sót ảnh trùng đã qua lật/cắt/tăng sáng mạnh (recall 0.67 trên calib).
4. Ngưỡng BOX_TINY dùng cạnh ngắn (min(w,h) px) < 12, khác với bộ lọc CVAT "width < 20" — hai định nghĩa không thay thế nhau.
```

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Đã train trên GPU local (RTX 3050 6GB): `yolo26n.pt`, 20 epoch, `imgsz=640`, `batch=16`, 2 seed (0, 1); cùng val `gold_val` (40 ảnh) và cùng test (100 ảnh nhãn người). Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.721 ± 0.010 | 0.521 ± 0.009 | 0.800 ± 0.076 | 0.614 ± 0.034 |
| clean | 202 | 2 | 0.734 ± 0.004 | 0.508 ± 0.003 | 0.788 ± 0.014 | 0.634 ± 0.012 |

Chênh mAP50 (clean − raw) = **+0.013**: lớn hơn độ lệch giữa các seed (raw ±0.010, clean ±0.004), nhưng mAP50-95 lại **giảm** 0.013 (raw 0.521, clean 0.508) và chỉ có 2 seed. Kết luận trung thực: **chưa kết luận được** clean tốt hơn raw; cần ≥ 3–5 seed mới tách được tín hiệu khỏi nhiễu.

AP50 theo lớp (TB 2 seed) — `car` 0.724 → 0.737; `person` 0.835 → 0.833; `truck` 0.636 → 0.643; `bus` 0.679 → 0.722. `truck` dao động rất mạnh giữa seed (raw: 0.719 và 0.553), nên chênh lệch tổng chủ yếu đến từ lớp hiếm chứ không phải chất lượng dữ liệu.

≥ 2 giả thuyết và cách kiểm: (1) `raw` còn ảnh trùng/rò rỉ với tập test trong 224 ảnh, làm điểm raw bị thổi — kiểm bằng số ảnh cửa vào đã loại (`01_intake.csv`: 8 trùng byte, 4 trùng gần đúng, 5 rò rỉ test/val). (2) `clean` ít ảnh hơn (202) và còn 24 ảnh hàng đợi chưa duyệt nên nhãn máy chưa được người sửa hết — kiểm bằng biến thể `auto`/`oracle` của `materialize_dataset.py`. (3) Test chỉ 100 ảnh nên nhiễu cao — kiểm bằng chạy thêm seed.

## 6. Quyết định và ghi chú AI
TODO(học viên): (a) quyết định cuối; nếu Hold/Rework cần làm gì để thành Release? (b) Dùng AI viết code? Ghi 3 dòng: prompt chính, cách bạn kiểm code AI, 1 lần AI sai. Không dùng: ghi "không dùng".

*(Thưởng +2, tùy chọn)* CVAT: lọc `width < 20`, ảnh/số box khớp, đối chiếu `BOX_TINY` (xem docs/CVAT_FILTER.md), 1 câu về `can_review`.

(a) Quyết định:

```text
Giữ Release. Không cần sửa gì thêm để thành Release, nhưng biên rất mỏng (9.90% vs 10%): muốn chắc hơn thì giảm cảnh báo,
không được nới warn_ratio_hold hay tắt check. Rủi ro đã biết: 24 ảnh hàng đợi chưa duyệt vẫn tính vào tỉ lệ cảnh báo.
```

(b) 3 dòng AI (thay bằng trải nghiệm thật; nếu không dùng AI thì ghi "không dùng"):

```text
- Prompt chính: "<prompt bạn đã dùng>".
- Cách kiểm code AI: đọc lại diff, đối chiếu docstring/test, chạy pytest và pipeline trên lô thật.
- Một lần AI sai: "<lỗi thật + cách phát hiện>".
```

Phần thưởng +3 (ghi kèm mục 6):
```text
Check thêm BOX_ASPECT trong pipeline/checks/label_format.py: cờ khi max(w_px,h_px)/min(w_px,h_px) > 6.0, severity WARN
(vì box dài/hẹp có thể là vật thật). Có 6 dòng BOX_ASPECT ở 02_error_list_v1.csv và 3 dòng ở 07_error_list_v3.csv;
đẩy tỉ lệ cảnh báo từ 8.91% lên 9.90%. Test riêng: tests/test_box_ratio.py (7 ca). Ngưỡng để trong code vì
configs/pipeline.yaml bị ghim, và không đăng ký ở pipeline/checks/__init__.py vì file đó bị ghim sha1.
```

Phần thưởng +2 CVAT (mục 6(b) theo `docs/CVAT_FILTER.md`) — cần tự thao tác UI + ảnh chụp:

```text
- File để import annotations: cvat/yolo11_priority20.zip (YOLO 1.1: obj.names, obj.data, train.txt, obj_train_data/*.txt)
  cho 20 ảnh đầu 05_review_queue.csv; cvat/labels.json để tạo project Raw.
- Số liệu đã đo sẵn trong cvat/box_tiny_vs_cvat.json: 20 ảnh, 60 box, 10 box có width < 20 px;
  riêng 20 ảnh này pipeline báo 0 dòng BOX_TINY. Ảnh có box khớp bộ lọc: img_0020 (4/8 box), img_0199 (4/10), img_0078 (1/2), img_0022 (1/1).
- Giải thích chênh lệch: CVAT lọc "width < 20", pipeline BOX_TINY dùng CẠNH NGẮN min(w,h)*px < 12 → CVAT bắt rộng hơn;
  ngoài ra trong 20 ảnh ưu tiên không có ảnh nào bị BOX_TINY, nên 10 vs 0 không phải lỗi.
- Một câu can_review: người gán bật can_review cho ca khó; pipeline dùng tín hiệu tương tự qua second_opinion.conf
  và review.weights để xếp ưu tiên hàng đợi.
- Kèm ảnh chụp màn hình bộ lọc + danh sách box (bắt buộc).