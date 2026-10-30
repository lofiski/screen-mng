"""真实窗口集成测试：启动测试窗口并检查摆放位置。"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from screen_mng import core, win32

SCRIPT = str(Path(__file__).with_name("dummy_window.py"))
MONS = win32.list_monitors()


def find(title):
    return next((w for w in win32.list_windows() if w.title == title), None)


def wait_window(title, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if w := find(title):
            return w
        time.sleep(0.2)
    raise TimeoutError(title)


@pytest.fixture
def spawn():
    procs = []

    def _spawn(title, dpi_aware=False):
        procs.append(subprocess.Popen([sys.executable, SCRIPT, title] + (["aware"] if dpi_aware else [])))
        return wait_window(title)

    yield _spawn
    for p in procs:
        p.kill()


def assert_at(hwnd, rule):
    mon = core.resolve_monitor(rule["monitor"], MONS)
    target = core.zone_rect(rule["zone"], mon.work)
    got = win32.frame_rect(hwnd)
    assert all(abs(a - b) <= 2 for a, b in zip(got, target)), (got, target)


@pytest.mark.parametrize("aware", [False, True])
def test_move_existing_windows_every_monitor(spawn, aware):
    rules = []
    for m in MONS:
        for zone in ("top", "bottom"):
            title = f"SMTEST-{m.number}-{zone}-{aware}"
            spawn(title, aware)
            rules.append({"title": f"^{title}$", "monitor": m.number, "zone": zone, "launch": False})
    assert core.apply_layout(rules, timeout=5, report=print)
    for r in rules:
        assert_at(find(r["title"][1:-1]).hwnd, r)


def test_maximize_on_secondary(spawn):
    m = MONS[-1]
    w = spawn("SMTEST-max", True)
    assert core.apply_layout([{"title": "^SMTEST-max$", "monitor": m.number, "zone": "maximize"}], report=print)
    assert win32.is_maximized(w.hwnd)
    assert win32.monitor_of_window(w.hwnd, MONS).number == m.number


def test_launch_when_missing():
    title = "SMTEST-launched"
    rule = {"app": sys.executable, "args": f'"{SCRIPT}" {title} aware', "title": f"^{title}$",
            "monitor": MONS[-1].number, "zone": "right-two-thirds"}
    try:
        assert core.apply_layout([rule], timeout=15, report=print)
        assert_at(find(title).hwnd, rule)
    finally:
        if w := find(title):
            subprocess.run(["taskkill", "/F", "/PID", str(w.pid)], capture_output=True)


def test_missing_window_without_launch_fails():
    assert not core.apply_layout([{"title": "^SMTEST-none$", "launch": False}], report=print)


def test_capture_then_apply_roundtrip(spawn):
    w = spawn("SMTEST-capture", True)
    m = MONS[-1]
    core.apply_layout([{"title": "^SMTEST-capture$", "monitor": m.number, "zone": [0.1, 0.2, 0.5, 0.3]}], report=print)
    before = win32.frame_rect(w.hwnd)
    rule = next(r for cw, r in core.capture_windows() if cw.hwnd == w.hwnd)
    assert rule["zone"] == pytest.approx([0.1, 0.2, 0.5, 0.3], abs=0.002)
    rule["title"] = "^SMTEST-capture$"
    core.apply_layout([{"title": "^SMTEST-capture$", "monitor": 1, "zone": "left"}], report=print)
    assert core.apply_layout([rule], report=print)
    assert all(abs(a - b) <= 2 for a, b in zip(win32.frame_rect(w.hwnd), before))


def test_autostart_registry():
    prev = core.get_autostart()
    try:
        core.set_autostart("测试 布局")
        assert core.get_autostart() == "测试 布局"
        core.set_autostart(None)
        assert core.get_autostart() is None
    finally:
        core.set_autostart(prev)
