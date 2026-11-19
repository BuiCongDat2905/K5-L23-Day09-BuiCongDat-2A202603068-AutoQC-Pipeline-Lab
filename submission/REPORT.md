# Báo cáo Day 09 — Bùi Công Đạt, 2A202603068

## 1. Kết luận trước

Pipeline kết luận **Release**: 0 lỗi bắt buộc, còn 20/202 ảnh cảnh báo chưa duyệt (9.90%) — dưới ngưỡng Hold 10% — mã thoát 0 và dataset được xuất. Lô vào có 224 ảnh thô; cửa vào loại 22 ảnh (2 hỏng, 3 quá nhỏ, 8 trùng từng byte, 4 trùng gần đúng, 5 rò rỉ từ kho test/val), còn 202 ảnh vào pipeline và 202 ảnh ra dataset (`manifest.n_images = 202`). Lý do chính: mọi lỗi bắt buộc đã được máy sửa tự động hoặc chuyển sang người duyệt, phần cảnh báo còn lại nằm dưới ngưỡng.

## 2. Lỗi và phân việc

Bảng dưới gom theo mã lỗi từ `02_error_list_v1.csv` — 176 issue ở vòng 1, gồm 58 lỗi bắt buộc và 118 cảnh báo, trên 21 mã. "Số" là số dòng lỗi; "ai sửa" là máy (tự sửa hoặc loại ở cửa vào) hay người (hàng đợi duyệt).

| Mã lỗi | Số dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| `POSSIBLE_MISSING` | 32 | người | model lớn thấy vật mà nhãn thiếu; chỉ cảnh báo vì model cũng có thể sai |
| `POSSIBLE_FALSE_POS` | 29 | người | box nhãn không khớp dự đoán nào; người quyết định xoá hay giữ |
| `POSSIBLE_WRONG_CLASS` | 14 | người | nhãn khác lớp dự đoán; sửa lớp cần người |
| `EMPTY_LABEL` | 12 | người | file nhãn rỗng; người gán lại |
| `POSSIBLE_LOOSE_BOX` | 12 | người | cùng vật nhưng IoU thấp; chỉnh box cần người |
| `BOX_OUT_OF_IMAGE` | 8 | máy | `clip_box`: cắt box về trong ảnh |
| `DUP_IMAGE_EXACT` | 8 | máy (cửa vào) | trùng từng byte; loại ảnh |
| `DUP_BOX` | 7 | máy | `drop_line`: bỏ dòng box lặp |
| `BOX_ASPECT` | 6 | người | box dài/hẹp bất thường (tỉ lệ > 6.0), WARN |
| `BOX_TINY` | 6 | người | cạnh ngắn < 12 px, WARN |
| `BAD_CLASS_ID` | 6 | máy | `drop_line`: id lớp ngoài 0..3 |
| `MISSING_LABEL_FILE` | 6 | người | `needs_label`: chuyển ảnh sang hàng người gán |
| `LEAK_TEST` | 5 | máy (cửa vào) | trùng ảnh kho test/val; loại để chống rò rỉ |
| `CLASS_RARE` | 4 | người | lớp hiếm (truck/bus) cần soát |
| `BOX_ZERO` | 4 | máy | `drop_line`: box có w <= 0 hoặc h <= 0 |
| `DUP_IMAGE_NEAR` | 4 | máy (cửa vào) | trùng gần đúng theo phash (khoảng cách 0, 6, 10) |
| `BOX_HUGE` | 3 | người | box chiếm quá 95% ảnh, WARN |
| `BAD_FORMAT` | 3 | máy | `drop_line`: dòng không đủ 5 cột số |
| `BAD_SIZE` | 3 | máy (cửa vào) | cạnh ngắn < 250 px; loại ảnh |
| `CORRUPT_IMAGE` | 2 | máy (cửa vào) | không mở được ảnh; loại |
| `BAD_CLASS_NAME` | 2 | máy | `rename_classes`: sửa map lớp trong `data.yaml` (1 thay đổi) |

Tổng cộng máy sửa 35 thay đổi (`03_fixes.csv`): `drop_line` 20, `clip_box` 8, `needs_label` 6, `rename_classes` 1. Sau vòng 2 còn 6 lỗi bắt buộc (`MISSING_LABEL_FILE`) và 114 cảnh báo.

Hàng đợi người duyệt: `05_review_queue.csv` xếp ảnh theo trọng số `review.weights` — `NEEDS_LABEL` = 10 đứng đầu, rồi `POSSIBLE_WRONG_CLASS` = 3, `POSSIBLE_MISSING` = 2, `POSSIBLE_FALSE_POS` = 2, `POSSIBLE_LOOSE_BOX` = 1.5. Hàng đợi có 104 ảnh nhưng ngân sách chỉ 80, nên người duyệt 80 ảnh đầu; 24 ảnh còn lại vẫn bị tính vào tỉ lệ cảnh báo của cổng. Trong 80 ảnh đã duyệt, người thay nhãn cho cả 80 (`06_review_log.csv`), xử lý được 6 ảnh `MISSING_LABEL_FILE` và phần lớn cảnh báo ngữ nghĩa; sau duyệt còn 36 cảnh báo trên 32 ảnh (`07_error_list_v3.csv`).

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | `DUP_IMAGE_NEAR`: P/R/F1 `1.00 / 0.50 / 0.67` → `1.00 / 0.67 / 0.80` | sweep 2..20: khoảng 4–14 cho cùng F1 0.80; 16 lên 0.91 nhưng bắt đầu loại nhầm ảnh khác trên lô thật; 20 tụt recall 0.33 do bỏ sót trùng thật. Chọn 12 = cuối vùng ổn định, precision giữ 1.00 |
| `second_opinion.conf` | 0.25 | **0.8** | `POSSIBLE_WRONG_CLASS`: `0.56 / 0.83 / 0.67` → `1.00 / 0.83 / 0.91`; `POSSIBLE_MISSING` recall `1.00` → `0.75`; `POSSIBLE_LOOSE_BOX` recall `0.40` → `0.20` | tăng conf để lọc cảnh báo rác (precision lên 1.00), đổi lại bỏ sót vật nhỏ và box lỏng; 0.8 vẫn dưới trần 0.85 của luật bài |

Một chỗ calibration có thể đánh lừa: calib chỉ có 39 ảnh, trong khi lô thật 224 ảnh. `conf = 0.8` làm `POSSIBLE_LOOSE_BOX` recall còn 0.20 và `POSSIBLE_MISSING` còn 0.75 — F1 của `WRONG_CLASS` (0.91) trông rất đẹp nhưng đổi lại là bỏ sót box lỏng và vật thiếu. Nguy hiểm hơn, kết luận Release đang sát ngưỡng: 9.90% so với 10%, biên chỉ 0.10 điểm phần trăm, chỉ cần lô chấm thêm 1 ảnh cảnh báo là Hold. Ngoài ra `phash = 12` loại 22 ảnh ở cửa vào; các cặp `DUP_IMAGE_NEAR` bị loại có phash 0, 6, 10, cần mở ảnh xem vì phash thấp vẫn có thể là hai ảnh khác nhau (nền giống, vật khác).

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

(a) Cửa chặn hoạt động đúng: chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` cho kết luận **Rework**, mã thoát **20**, và **không** tạo thư mục `work/exp_nb` (không xuất dataset). Nguyên nhân: không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` còn nguyên (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`); `07_error_list_v3.csv` của lần chạy này có 120 issue, trong đó 6 lỗi bắt buộc `MISSING_LABEL_FILE`.

(b) Ít nhất 2 điểm mù, kèm bằng chứng:

1. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` chỉ bắt khi IoU < 0.5; box lệch nhưng IoU >= 0.5 không bị cờ. `07_error_list_v3.csv` vẫn còn 7 cảnh báo loại này.
2. **Nhầm lớp:** `POSSIBLE_WRONG_CLASS` chỉ là WARN. Lô này có 14 cảnh báo ở vòng 1, sau máy và người còn 1 — nhưng cổng vẫn có thể Release dù còn nhầm lớp, vì đây không phải lỗi bắt buộc.
3. **Trùng biến đổi mạnh:** `phash = 12` bỏ sót ảnh trùng đã qua lật/cắt/tăng sáng mạnh (recall 0.67 trên calib).
4. **Khác định nghĩa box nhỏ:** `BOX_TINY` dùng cạnh ngắn `min(w, h) · px < 12`, khác bộ lọc CVAT `width < 20` — hai định nghĩa không thay thế nhau.

## 5. Train: raw vs clean

Đã train trên GPU local (RTX 3050 6GB): `yolo26n.pt`, 20 epoch, `imgsz = 640`, `batch = 16`, 2 seed (0, 1); cùng val `gold_val` (40 ảnh) và cùng test (100 ảnh nhãn người). Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.721 ± 0.010 | 0.521 ± 0.009 | 0.800 ± 0.076 | 0.614 ± 0.034 |
| clean | 202 | 2 | 0.734 ± 0.004 | 0.508 ± 0.003 | 0.788 ± 0.014 | 0.634 ± 0.012 |

Chênh mAP50 (clean − raw) = **+0.013**, lớn hơn độ lệch giữa các seed (raw ±0.010, clean ±0.004), nhưng mAP50-95 lại **giảm** 0.013 (raw 0.521, clean 0.508) và chỉ có 2 seed. Kết luận trung thực: **chưa kết luận được** clean tốt hơn raw; cần ≥ 3–5 seed mới tách được tín hiệu khỏi nhiễu.

AP50 theo lớp (trung bình 2 seed): `car` 0.724 → 0.737; `person` 0.835 → 0.833; `truck` 0.636 → 0.643; `bus` 0.679 → 0.722. `truck` dao động rất mạnh giữa seed (raw: 0.719 và 0.553), nên chênh lệch tổng chủ yếu đến từ lớp hiếm chứ không phải chất lượng dữ liệu.

Hai giả thuyết và cách kiểm: (1) `raw` còn ảnh trùng/rò rỉ với tập test trong 224 ảnh, làm điểm raw bị thổi — kiểm bằng số ảnh cửa vào đã loại (`01_intake.csv`: 8 trùng byte, 4 trùng gần đúng, 5 rò rỉ test/val); (2) `clean` ít ảnh hơn (202) và còn 24 ảnh hàng đợi chưa duyệt nên nhãn máy chưa được người sửa hết — kiểm bằng biến thể `auto`/`oracle` của `materialize_dataset.py`; (3) test chỉ 100 ảnh nên nhiễu cao — kiểm bằng chạy thêm seed.

## 6. Quyết định và ghi chú AI

(a) **Quyết định cuối: giữ Release** — 0 lỗi bắt buộc, 20/202 ảnh còn cảnh báo chưa duyệt (9.90%) dưới ngưỡng 10%, mã thoát 0, dataset đã xuất 202 ảnh. Không cần làm gì thêm để thành Release. Nếu rơi vào Hold/Rework thì phải giảm số ảnh cảnh báo chưa duyệt (duyệt thêm ảnh trong hàng đợi) hoặc xử lý hết lỗi bắt buộc (6 ảnh `MISSING_LABEL_FILE`); **không** được nới `warn_ratio_hold` hay tắt check để đổi kết luận. Rủi ro đã biết: biên chỉ 0.10 điểm phần trăm, và 24 ảnh hàng đợi chưa duyệt vẫn tính vào tỉ lệ cảnh báo.

(b) **Ghi chú AI** — có dùng AI (DeepSeek agent) hỗ trợ viết code và chạy kiểm:

- Prompt chính: giao từng việc một, kèm brief ghi rõ file được sửa, đặc tả/docstring và tiêu chí kiểm, ví dụ "khôi phục check `BOX_ASPECT`, chỉ sửa `pipeline/checks/label_format.py`, để `tests/test_box_ratio.py` xanh".
- Cách kiểm code AI: đọc lại `git diff`, đối chiếu docstring và test có sẵn, chạy `pytest -q` (86 passed), rồi chạy `python -m pipeline.run` trên lô thật và so số trong `submission/reports/` (Release, 20/202, 36 cảnh báo ở vòng 3).
- Một lần AI sai: AI báo check `BOX_ASPECT` đã có, nhưng code không có trong `pipeline/checks/label_format.py`; chạy `pytest` thấy 5 failed ở `tests/test_box_ratio.py`, phải viết lại khối `BOX_ASPECT` (ngưỡng 6.0, WARN) thì test mới xanh.

**Check thêm `BOX_ASPECT`:** cờ khi `max(w_px, h_px) / min(w_px, h_px) > 6.0` (box dài/hẹp bất thường), severity **WARN** vì box dài/hẹp có thể là vật thật (cột, người đứng xa). Có 6 dòng `BOX_ASPECT` ở `02_error_list_v1.csv` và 3 dòng ở `07_error_list_v3.csv`; góp phần vào 20/202 ảnh cảnh báo (9.90%). Test riêng `tests/test_box_ratio.py` gồm 7 ca: box ngang, box dọc, box thường, biên đúng 6.0, 6.04, chỉ WARN, giữ số dòng gốc. Ngưỡng để trong code vì `configs/pipeline.yaml` bị ghim; không đăng ký ở `pipeline/checks/__init__.py` vì file đó ghim sha1.

**CVAT (tùy chọn, chưa thực hiện):** chưa thao tác UI CVAT nên chưa có ảnh chụp màn hình. Nguyên liệu đã chuẩn bị: `cvat/labels.json` (project `Raw`, 4 nhãn + `can_review`), `cvat/yolo11_priority20.zip` (annotations YOLO 1.1 cho 20 ảnh đầu `05_review_queue.csv`), `cvat/box_tiny_vs_cvat.json`. Đo trực tiếp từ nhãn 20 ảnh: 60 box, 10 box có `width < 20` px; riêng 20 ảnh này pipeline báo 0 `BOX_TINY` — không phải lỗi, vì `BOX_TINY` dùng cạnh ngắn `min(w, h) · px < 12` còn bộ lọc CVAT chỉ xét `width`. Ảnh có box khớp bộ lọc: `img_0020` (4/8 box), `img_0199` (4/10), `img_0078` (1/2), `img_0022` (1/1). `can_review`: người gán bật cho ca khó; pipeline dùng tín hiệu tương tự qua `second_opinion.conf` và `review.weights` để xếp ưu tiên hàng đợi.
