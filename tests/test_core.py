from screen_mng import core
from screen_mng.win32 import Monitor, Window

MONS = [
    Monitor(1, r"\.\DISPLAY1", True, (0, 0, 1920, 1080), (0, 0, 1920, 1040), 1),
    Monitor(2, r"\.\DISPLAY2", False, (-1080, 0, 0, 1920), (-1080, 0, 0, 1920), 2),
]


def test_zone_rect():
    work = (0, 0, 1920, 1040)
    assert core.zone_rect("full", work) == work
    assert core.zone_rect("top", (-1080, 0, 0, 1920)) == (-1080, 0, 0, 960)
    assert core.zone_rect("bottom", (-1080, 0, 0, 1920)) == (-1080, 960, 0, 1920)
    assert core.zone_rect("right-third", work) == (1280, 0, 1920, 1040)
    assert core.zone_rect([0.25, 0, 0.5, 1], work) == (480, 0, 1440, 1040)
    # 相邻区域无缝衔接
    assert core.zone_rect("left-third", (0, 0, 1000, 10))[2] == core.zone_rect("center-third", (0, 0, 1000, 10))[0]


def test_rect_to_zone():
    work = (0, 0, 1920, 1040)
    assert core.rect_to_zone((0, 0, 960, 1040), work) == "left"
    assert core.rect_to_zone((961, 0, 1920, 1039), work) == "right"
    assert core.rect_to_zone((100, 100, 500, 500), work) == [0.0521, 0.0962, 0.2083, 0.3846]
    assert core.rect_to_zone((-7, -3, 1927, 1047), work) == "full"  # 超出工作区时裁剪
    assert core.rect_to_zone((960, 0, 3000, 1040), work) == "right"


def test_resolve_monitor():
    assert core.resolve_monitor("primary", MONS).number == 1
    assert core.resolve_monitor("secondary", MONS).number == 2
    assert core.resolve_monitor(2, MONS).number == 2
    assert core.resolve_monitor("2", MONS).number == 2
    assert core.resolve_monitor(r"\.\display2", MONS).number == 2
    assert core.resolve_monitor(9, MONS).number == 1  # 不存在时退回主显示器


def test_rule_matching():
    w = Window(1, "README.md - Visual Studio Code", 1, r"D:\vsc\Code.exe")
    assert core.rule_process({"app": r"D:\vsc\Code.exe"}) == "code.exe"
    assert core.rule_matches({"app": r'"D:\vsc\Code.exe"'}, w)
    assert core.rule_matches({"process": "code.exe", "title": "readme"}, w)
    assert not core.rule_matches({"process": "code.exe", "title": "^foo"}, w)
    assert not core.rule_matches({"process": "chrome.exe"}, w)
    assert not core.rule_matches({"app": "obsidian://open"}, w)  # 无法识别时不乱匹配


def test_config_roundtrip():
    cfg = {"layouts": {"工作": [{"app": "chrome.exe", "monitor": 2, "zone": "top"}]}}
    core.save_config(cfg)
    assert core.load_config() == cfg
