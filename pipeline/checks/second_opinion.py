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


CHECK = "second_opinion"


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] của các dòng parse được và có id lớp hợp lệ (dòng hỏng bỏ qua, không chết)."""
    out = []
    for no, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= b[0] < len(ds.classes):
            out.append((no, b))
    return out


def _name(ds, c):
    return ds.classes[c] if 0 <= c < len(ds.classes) else str(c)


def run(ds, cfg, preds=None):
    p = cfg["second_opinion"]
    conf_min, min_area = p["conf"], p["min_area_px"]
    fp_conf, iou_missing, iou_match, iou_loose = p["fp_conf"], p["iou_missing"], p["iou_match"], p["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or ds.read_label_lines(stem) is None:
            continue                                   # không có ý kiến thứ hai, hoặc chưa có file nhãn (check khác báo)
        size = ds.image_size(stem)
        if size is None:
            continue                                   # ảnh hỏng: check images báo
        W, H = size
        labels = _labels_with_lines(ds, stem)
        rows = []
        for r in preds[stem]:
            try:
                c, conf, cx, cy, w, h = int(r[0]), float(r[1]), *map(float, r[2:6])
            except (TypeError, ValueError, IndexError):
                continue
            rows.append((c, conf, (cx, cy, w, h)))

        # (1) Mỗi dự đoán tin cậy và đủ lớn sinh tối đa MỘT issue: MISSING / LOOSE_BOX / WRONG_CLASS.
        for c, conf, box in rows:
            if conf < conf_min or box[2] * W * box[3] * H < min_area:
                continue
            cands = [(iou_xywh(box, lb[1:]), lb[0], no) for no, lb in labels]
            cands = [x for x in cands if x[0] >= iou_missing]
            if not cands:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {_name(ds, c)} (conf {conf:.2f}) nhưng nhãn không có box nào ở đó",
                                    extra={"conf": round(conf, 4), "pred_cls": c}))
                continue
            same = [x for x in cands if x[1] == c]
            if same:
                best = max(same, key=lambda x: x[0])
                if best[0] < iou_loose:
                    issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box {_name(ds, c)} ở dòng {best[2]} lệch/lỏng so với model (IoU {best[0]:.2f})",
                                        extra={"conf": round(conf, 4), "iou": round(best[0], 4), "label_line": best[2]}))
                continue                               # nhãn đúng lớp đã phủ vật này
            other = max(cands, key=lambda x: x[0])
            if other[0] >= iou_match:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"dòng {other[2]} gán {_name(ds, other[1])} nhưng model thấy {_name(ds, c)} "
                                    f"(conf {conf:.2f}, IoU {other[0]:.2f})",
                                    extra={"conf": round(conf, 4), "iou": round(other[0], 4), "pred_cls": c,
                                           "label_cls": other[1], "label_line": other[2]}))
            # chỉ có nhãn khác lớp với IoU trong [iou_missing, iou_match): mơ hồ, không cờ

        # (2) Box nhãn không khớp vật nào model thấy (conf >= fp_conf, KHÔNG lọc diện tích, không xét lớp).
        fp_boxes = [box for _, conf, box in rows if conf >= fp_conf]
        for no, lb in labels:
            best = max((iou_xywh(lb[1:], b) for b in fp_boxes), default=0.0)
            if best < iou_missing:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box {_name(ds, lb[0])} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                                    line=no, extra={"iou": round(best, 4)}))
    return issues
