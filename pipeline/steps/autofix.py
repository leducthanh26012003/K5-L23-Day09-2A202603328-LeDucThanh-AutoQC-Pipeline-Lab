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
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # cộng mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fmt(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") if v else "0"


def _clip_line(text):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu sau khi cắt box không còn diện tích."""
    c, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    if x2 - x1 < 1e-6 or y2 - y1 < 1e-6:              # dưới độ chính xác 6 chữ số khi ghi ra: coi như không còn diện tích
        return None
    return f"{c} {_fmt((x1 + x2) / 2)} {_fmt((y1 + y2) / 2)} {_fmt(x2 - x1)} {_fmt(y2 - y1)}"


def _remove_image(ds, stem):
    img = ds.image_path(stem)
    lab = ds.label_path(stem)
    if img is None and not lab.exists():
        return None                                   # đã xoá ở lần trước: idempotent
    name = img.name if img is not None else "(không có ảnh)"
    if img is not None:
        img.unlink()
    if lab.exists():
        lab.unlink()
    ds._size_cache.pop(stem, None)
    return name


def _rename_classes(ds, cfg):
    d = {}
    if ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    old = ds.yaml_names()
    new = {i: n for i, n in enumerate(cfg["classes"])}
    if old == new:
        return None
    d["names"] = new
    ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return [old.get(i) for i in sorted(old)], list(cfg["classes"])


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) Lỗi cấp ảnh: xoá ảnh + nhãn khỏi ds (không bao giờ đụng data/raw: ds là bản sao làm việc).
    removed = set()
    for stem in sorted({i.image for i in errors if _is_remove(i.code)}):
        codes = sorted({i.code for i in errors if i.image == stem and _is_remove(i.code)})
        name = _remove_image(ds, stem)
        removed.add(stem)
        if name is not None:
            fixes.append({"image": stem, "line": "", "action": "remove_image",
                          "before": name, "after": f"đã xoá ảnh + nhãn ({', '.join(codes)})"})

    # 2) data.yaml: ghi lại names đúng danh sách lớp của dự án.
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        changed = _rename_classes(ds, cfg)
        if changed is not None:
            fixes.append({"image": "data.yaml", "line": "", "action": "rename_classes",
                          "before": str(changed[0]), "after": str(changed[1])})

    # 3) Lỗi dòng: gom theo file, dùng số dòng GỐC (kể cả dòng trống), ghi lại file MỘT lần.
    drop, clip = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.image in removed or not isinstance(i.line, int):
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(i.line)
        elif i.code in CLIP_CODES:
            clip[i.image].add(i.line)

    for stem in sorted(set(drop) | set(clip)):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        old_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines, changed = [], False
        for no, text in enumerate(old_lines, 1):
            if no in drop[stem]:                       # xoá thắng: dòng có cả lỗi xoá và lỗi cắt chỉ ghi 1 fix
                fixes.append({"image": stem, "line": no, "action": "drop_line", "before": text, "after": ""})
                changed = True
                continue
            if no in clip[stem]:
                try:
                    new = _clip_line(text)
                except ValueError:
                    new_lines.append(text)             # không parse được: để check vòng sau báo BAD_FORMAT
                    continue
                if new is None:
                    fixes.append({"image": stem, "line": no, "action": "drop_line", "before": text,
                                  "after": "(box nằm ngoài ảnh, không còn diện tích sau khi cắt)"})
                else:
                    fixes.append({"image": stem, "line": no, "action": "clip_box", "before": text, "after": new})
                    new_lines.append(new)
                changed = True
                continue
            new_lines.append(text)
        if changed:
            path.write_text("".join(l + "\n" for l in new_lines), encoding="utf-8")

    # 4) Ảnh chưa có nhãn: KHÔNG tạo file (rỗng = ảnh nền); chỉ ghi lại để chuyển người gán.
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        if not ds.label_path(stem).exists():
            fixes.append({"image": stem, "line": "", "action": "needs_label",
                          "before": "(không có file)", "after": "chuyển người gán"})
    return fixes
