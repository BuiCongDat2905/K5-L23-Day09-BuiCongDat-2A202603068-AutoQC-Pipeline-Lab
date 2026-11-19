"""Test cho check thêm BOX_ASPECT (thưởng +3): box dài/hẹp bất thường.

File mới, tách khỏi `tests/test_label_format.py` (file đó bị ghim sha1).
"""
from pipeline.checks import label_format


def find(issues, code):
    return [(i.image, i.line) for i in issues if i.code == code]


def run(make_ds, cfg, lines, size=(640, 480)):
    ds = make_ds(images={"a": 1}, labels={"a": lines}, size=size)
    return label_format.run(ds, cfg)


def test_aspect_ratio_flags_strip_box(make_ds, cfg):
    # 0.5*640 = 320 px rộng, 0.02*480 = 9.6 px cao -> tỉ lệ 33.3
    assert find(run(make_ds, cfg, ["1 0.5 0.5 0.5 0.02"]), "BOX_ASPECT") == [("a", 1)]


def test_aspect_ratio_flags_tall_box(make_ds, cfg):
    # 0.02*640 = 12.8 px rộng, 0.5*480 = 240 px cao -> tỉ lệ 18.75
    assert find(run(make_ds, cfg, ["1 0.5 0.5 0.02 0.5"]), "BOX_ASPECT") == [("a", 1)]


def test_aspect_ratio_quiet_on_normal_box(make_ds, cfg):
    # 0.3*640 = 192, 0.4*480 = 192 -> tỉ lệ 1.0
    assert find(run(make_ds, cfg, ["1 0.5 0.5 0.3 0.4"]), "BOX_ASPECT") == []


def test_aspect_ratio_boundary_is_quiet(make_ds, cfg):
    # size (600, 400): 0.6*600 = 360 px, 0.15*400 = 60 px -> tỉ lệ đúng 6.0, không cờ (điều kiện là >)
    assert find(run(make_ds, cfg, ["1 0.5 0.5 0.6 0.15"], size=(600, 400)), "BOX_ASPECT") == []
    # 0.149*400 = 59.6 px -> tỉ lệ 6.04 > 6.0, có cờ
    assert find(run(make_ds, cfg, ["1 0.5 0.5 0.6 0.149"], size=(600, 400)), "BOX_ASPECT") == [("a", 1)]


def test_aspect_ratio_is_warn_only(make_ds, cfg):
    iss = run(make_ds, cfg, ["1 0.5 0.5 0.5 0.02"])
    assert all(i.severity == "warn" for i in iss if i.code == "BOX_ASPECT")


def test_aspect_ratio_reports_original_line_number_with_blank_lines(make_ds, cfg):
    iss = run(make_ds, cfg, ["1 0.5 0.5 0.2 0.3", "", "1 0.5 0.5 0.5 0.02"])
    assert find(iss, "BOX_ASPECT") == [("a", 3)]


def test_broken_line_does_not_stop_aspect_check(make_ds, cfg):
    iss = run(make_ds, cfg, ["garbage", "1 0.5 0.5 0.5 0.02"])
    assert find(iss, "BOX_ASPECT") == [("a", 2)]
