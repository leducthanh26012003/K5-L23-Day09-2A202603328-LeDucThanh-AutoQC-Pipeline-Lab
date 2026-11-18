# Báo cáo Day 09 — Lê Đức Thanh, 2A202603328

> Số liệu lấy từ `submission/reports/` (lần chạy `make run` với cấu hình đã calibrate, `config_sha1` 931de84…) và `submission/calibration/`.

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10). Vào **224** ảnh; cửa vào loại **22** ảnh (hỏng, quá nhỏ, trùng, rò rỉ test), còn **202** ảnh được QC và xuất ra `export/clean_v1` dưới dạng **bản nháp, chưa phát hành**. Sau khi máy sửa và người duyệt mô phỏng 80 ảnh, **không còn lỗi bắt buộc** (0 ERROR), nhưng **38/202 ảnh = 18.8%** vẫn còn cảnh báo chưa ai duyệt, vượt ngưỡng Hold 10%: hàng đợi có 125 ảnh mà ngân sách chỉ 80.

## 2. Lỗi và phân việc
Từ `02_error_list_v1` (trước khi sửa; gồm cả 22 lỗi ở cửa vào). Số dòng = số issue, số ảnh = số ảnh khác nhau.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 ảnh | máy (loại ở cửa vào) | md5 trùng từng byte: chắc chắn, không cần người |
| DUP_IMAGE_NEAR | 4 ảnh | máy (loại ở cửa vào) | phash ≤ 10; đã mở xem các cặp khoảng cách 6 và 10 (mục 3) |
| LEAK_TEST | 5 ảnh | máy (loại ở cửa vào) | trùng ảnh kho test: giữ lại sẽ làm số đo test lạc quan |
| BAD_SIZE | 3 ảnh | máy (loại ở cửa vào) | cạnh ngắn < 250 px (quy tắc dự án) |
| CORRUPT_IMAGE | 2 ảnh | máy (loại ở cửa vào) | không mở được, không có gì để gán |
| BAD_CLASS_ID | 6 dòng / 6 ảnh | máy (`drop_line`) | id 93, 4, −1 không có lớp tương ứng: không đoán được lớp đúng nên xoá dòng |
| BAD_FORMAT | 3 dòng / 3 ảnh | máy (`drop_line`) | thiếu cột / `nan`: không dựng lại được box |
| BOX_ZERO | 4 dòng / 4 ảnh | máy (`drop_line`) | box rộng hoặc cao 0 |
| DUP_BOX | 7 dòng / 7 ảnh | máy (`drop_line`) | cùng lớp, IoU > 0.9 với dòng trước: giữ dòng đầu |
| BOX_OUT_OF_IMAGE | 8 dòng / 8 ảnh | máy (`clip_box`) | cắt về [0,1], giữ lớp; sửa cú pháp, không đổi nghĩa |
| BAD_CLASS_NAME | 2 issue / `data.yaml` | máy (`rename_classes`) | `names` viết sai: ghi lại theo `classes` của dự án |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn; không tạo file rỗng (rỗng = ảnh nền) |
| POSSIBLE_MISSING | 53 / 52 ảnh | **người** | model lớn thấy vật mà nhãn không có: chỉ là ý kiến thứ hai |
| POSSIBLE_WRONG_CLASS | 18 / 18 ảnh | **người** | car↔truck↔bus là lỗi ngữ nghĩa, quy tắc cú pháp không bắt được |
| POSSIBLE_LOOSE_BOX | 28 / 24 ảnh | **người** | đúng vật nhưng IoU với model < 0.5 |
| POSSIBLE_FALSE_POS | 29 / 27 ảnh | **người** | box nhãn không khớp vật nào model thấy |
| EMPTY_LABEL | 12 ảnh | **người** | file rỗng: ảnh nền thật hay quên gán? |
| BOX_TINY / BOX_HUGE | 6 dòng (4 ảnh) / 3 ảnh | **người** | quy tắc dự án, không có đáp án đúng/sai bằng máy |
| CLASS_RARE | 4 (cấp dataset) | **người** | lớp ít box: cần thêm dữ liệu, không sửa bằng nhãn |

Máy tự sửa **35** thay đổi (`03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 1 `rename_classes`, 6 `needs_label`), cộng 22 ảnh loại ở cửa vào; mọi thay đổi có cột trước → sau, `data/raw` không bị đụng.

Hàng đợi `05_review_queue.csv` xếp theo **tổng trọng số** của các mã trên ảnh (`review.weights`: NEEDS_LABEL 10, WRONG_CLASS 3, MISSING 2, FALSE_POS 2, FIXED_DROP_LINE 2, LOOSE_BOX 1.5…). Đầu hàng là img_0020 (11.5: một dòng bị xoá + MISSING + WRONG_CLASS), rồi 6 ảnh chưa có nhãn (10.0), rồi các ảnh có WRONG_CLASS / MISSING. Với ngân sách 80 ảnh, người duyệt xem được **74 ảnh có cờ ngữ nghĩa**: đủ 18/18 ảnh WRONG_CLASS, 50/52 ảnh MISSING, nhưng chỉ 12/23 ảnh FALSE_POS và 8/24 ảnh LOOSE_BOX (mẫu số theo `04_error_list_v2`, sau sửa tự động). 45 ảnh chưa duyệt chủ yếu là LOOSE_BOX (16) và FALSE_POS (11), trọng số thấp (ảnh thứ 80 có ưu tiên 3.34, ảnh thứ 81 là 3.33).

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | DUP_IMAGE_NEAR: 1.00 / 0.50 → 1.00 / 0.67 (EXACT giữ 1.00 / 1.00) | Lỗi này bị **xoá ảnh** nên ưu tiên precision. Trên calib, 4–14 cho cùng 1.00 / 0.67; 16 cho recall 0.83. Trên raw, khoảng cách nhỏ nhất giữa các ảnh khác byte chỉ có 0, 2, 6, 10 rồi **nhảy lên 16** (9 cặp). Chọn 10: bắt được cặp img_0061/img_0186 (khoảng cách 10, cùng cảnh ghế đá bị cắt và đổi sáng) mà vẫn cách xa cụm 16 |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG_CLASS 0.56 / 0.83 → 0.62 / 0.83; MISSING 0.50 / 1.00 → 0.57 / 1.00; LOOSE_BOX 0.29 / 0.40 → 0.20 / 0.20; FALSE_POS 0.31 / 1.00 (không đổi, dùng `fp_conf`) | Cảnh báo cho người nên ưu tiên **recall**. 0.6 giữ nguyên recall MISSING 1.00 và WRONG_CLASS 0.83 nhưng ít cờ giả hơn; hàng đợi raw giảm 143 → 125 ảnh. Không chọn 0.8 dù nó cho Release (hàng đợi 102, 7.9%): recall MISSING tụt còn 0.75 (sót 2/8 vật thiếu nhãn), tức là Release nhờ máy kiểm "mù" hơn. Cái giá: LOOSE_BOX recall giảm 2/5 → 1/5 |

**Một chỗ calibration đánh lừa:** trên calib, `phash_dist = 16` có precision 1.00 và recall cao nhất, nên nếu chỉ nhìn bảng sweep sẽ chọn 16. Nhưng trên raw có 9 cặp ở khoảng cách 16; mở 3 cặp raw–raw thì **2 cặp là ảnh khác hẳn nhau**: img_0008 (trượt tuyết) với img_0011 (tennis), img_0113 (người ngồi bàn) với img_0177 (lướt sóng); chỉ img_0074/img_0084 là trùng thật. 6 cặp còn lại ở khoảng cách 16 là ảnh raw với ảnh **test**, sẽ bị loại thành LEAK_TEST. Calib chỉ có 39 ảnh nên không có cặp "khác nhau mà phash gần" để phạt FP; ngưỡng đẹp trên calib sẽ xoá nhầm ảnh tốt trên raw.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt): sau sửa tự động còn **6 lỗi bắt buộc MISSING_LABEL_FILE** (máy không bịa nhãn), kết luận **REWORK — "còn 6 lỗi bắt buộc (MISSING_LABEL_FILE): phải sửa trước khi xuất"**, **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)" và thư mục `work/exp_nb` **không được tạo**. Với ngân sách 80, 6 ảnh đó được người gán (NEEDS_LABEL ở đầu hàng đợi) nên lỗi bắt buộc về 0 và kết luận chuyển thành Hold.

**(b) Điểm mù có bằng chứng.**
1. **Ảnh trùng biến đổi mạnh:** img_0074 và img_0084 là cùng một cảnh (cắt / dịch khung) nhưng phash cách 16 > 10, nên **cả hai vẫn ở trong dataset**. Ngưỡng nào bắt được cặp này cũng sẽ gộp nhầm img_0008/img_0011.
2. **Box lỏng nhẹ:** ở conf 0.6, POSSIBLE_LOOSE_BOX trên calib chỉ bắt **1/5** lỗi chèn (recall 0.20); trên raw còn **16 ảnh LOOSE_BOX chưa duyệt** vì trọng số thấp. Box phình to mà model cũng vẽ hơi rộng sẽ lọt.
3. **Nhầm lớp mà model lớn cũng nhầm:** WRONG_CLASS trên calib vẫn sót 1/6 (recall 0.83) ở mọi mức conf. Ngược lại model cũng báo nhầm trên nhãn người: sau khi 80 ảnh đã được **thay bằng nhãn người**, `07_error_list_v3` vẫn còn 11 MISSING, 10 FALSE_POS, 4 LOOSE_BOX, 3 WRONG_CLASS trên chính các ảnh đã duyệt, tức ý kiến thứ hai có nhiều cờ giả.
4. **Rò rỉ test bị biến đổi mạnh:** 6 ảnh raw có phash cách ảnh test đúng 16, không bị coi là LEAK_TEST ở ngưỡng 10. Tôi không mở ảnh test để phân xử (RULES: không dùng test để chọn ngưỡng), nên nếu có ca rò rỉ thật trong số này thì pipeline không biết.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Train trên Colab (GPU T4) bằng `notebooks/day09_train_compare.ipynb`: `yolo26n.pt`, 20 epoch, imgsz 640, batch 16, seed 0 và 1; cùng val (`gold_val`, 40 ảnh) và cùng test (100 ảnh). `raw` train trên 224 ảnh với nhãn gốc; `clean` train trên 202 ảnh của bản xuất nháp (`manifest_sha1` 3c5b86f…, khớp `export/clean_v1`).

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

Chênh mAP50 (clean − raw) = **−0.025**, bằng đúng độ lệch giữa 2 seed của `clean` (±0.025: seed 0 được 0.718, chỉ kém raw 0.008; seed 1 được 0.683). Với 2 seed, khác biệt mAP50 **nằm trong nhiễu**. mAP50-95 chênh −0.024, lớn hơn độ lệch giữa seed (±0.004 / ±0.008), nhưng 2 seed là quá ít để khẳng định. Theo lớp, gần như **toàn bộ** chênh lệch nằm ở `truck`: AP50 trung bình raw 0.648, clean 0.538 (−0.111, chia cho 4 lớp ≈ −0.028 mAP50); car (0.738 / 0.738), person (0.822 / 0.823), bus (0.695 / 0.703) gần như bằng nhau. AP `truck` của clean tự nó đã lệch 0.10 giữa 2 seed (0.590 / 0.486).

**Kết luận trung thực:** **không có bằng chứng** dữ liệu sau pipeline cho model tốt hơn dữ liệu gốc; trên mAP50 chưa kết luận được bên nào hơn, trên mAP50-95 raw nhỉnh hơn một chút nhưng chưa đủ seed và raw có lợi thế không công bằng (giả thuyết 1).

Giả thuyết và cách kiểm:
1. **Rò rỉ test trong raw:** pipeline đã phát hiện 5 ảnh raw trùng ảnh test (`LEAK_TEST`: img_0049↔test_033, img_0101↔test_039, img_0167↔test_044, img_0174↔test_085, img_0221↔test_009). `raw` được "xem trước" 5/100 ảnh test nên điểm test của raw bị thổi phồng; `clean` đã loại 5 ảnh này. Kiểm: chấm lại cả hai model trên 95 ảnh test còn lại (bỏ 5 ảnh trên), hoặc train thêm một biến thể raw bỏ 5 ảnh rò rỉ.
2. **Lớp `truck` ít mẫu nên rất nhiễu:** clean có 41 box truck, raw 32 (`class_stats.csv` và nhãn gốc); test chỉ 100 ảnh. Chênh lệch 0.11 AP truck cùng cỡ với độ lệch 0.10 giữa 2 seed của clean. Kiểm: chạy ≥ 5 seed, đếm số truck trong test, so AP truck theo từng seed.
3. **Nhãn clean còn lỗi hoặc khác quy ước của test:** 45 ảnh trong hàng đợi chưa được duyệt (16 LOOSE_BOX, 11 FALSE_POS), và người duyệt đã đổi nhiều box car → truck (car 122 → 101, truck 32 → 41) có thể theo quy ước khác nhãn test. Kiểm: train biến thể `oracle` (nhãn người, chặn trên) và mở các ảnh có đổi lớp truck.
4. **Raw thực tế train trên ít hơn 224 ảnh:** nhãn gốc có id lớp lạ (−1 ×2, 4 ×2, 7, 93) mà Ultralytics thường bỏ cả ảnh; điều này đáng lẽ làm raw **kém** đi, nên nếu raw vẫn ngang clean thì giả thuyết 1 càng đáng kiểm. Kiểm: đọc cảnh báo ảnh/nhãn hỏng ở ô 6 của notebook (lần chạy này tôi chưa ghi lại số đó).

Việc tiếp theo: duyệt nốt hàng đợi để clean không còn là bản nháp, chấm lại trên test bỏ 5 ảnh rò rỉ, thêm seed và biến thể `oracle` trước khi nói pipeline có giúp train hay không.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: Hold.** Không Rework vì không còn lỗi bắt buộc; không Release vì 38/202 = 18.8% ảnh còn cảnh báo chưa duyệt ≥ 10%. Để thành Release cần **duyệt thêm ít nhất 18 ảnh** trong 38 ảnh còn cảnh báo (để số ảnh còn cảnh báo chưa duyệt ≤ 20/202 = 9.9% < 10%), ưu tiên 16 ảnh LOOSE_BOX và 11 ảnh FALSE_POS; không được hạ `second_opinion.conf` để hàng đợi "vừa" ngân sách (mục 3).

**(b) Dùng AI viết code (Claude):**
- **Prompt chính:** đưa docstring của từng stub (đầu vào/đầu ra, bảng mã lỗi, các ca biên), file test tương ứng và `common.py`; yêu cầu đọc ngưỡng từ `cfg`, không đọc `data/review_reference`, `data/test/labels`, `MANIFEST.csv`, không ghi cứng tên ảnh, không ghi vào `data/raw`.
- **Cách kiểm:** chạy test từng module (14, 10, 11, 15 test) rồi cả bộ 79 test; chạy `python -m pipeline.run` trên 224 ảnh để chắc không chết với dữ liệu thật; đối chiếu `03_fixes.csv` (20 drop + 8 clip khớp 6+3+4+7 lỗi xoá và 8 lỗi tràn); đọc từng dòng tìm thao tác xoá/ghi file.
- **Một lần AI sai:** bản đầu của `autofix` chỉ xoá box khi `x2 <= x1`; box sau khi cắt mà rộng < 0.000001 sẽ được ghi ra thành `0` (làm tròn 6 chữ số), tức tạo ra một box rỗng mới. Test không bắt được; phát hiện khi đọc lại code và sửa thành `< 1e-6`.
