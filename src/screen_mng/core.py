"""配置、区域计算、应用布局、捕获当前布局、开机自启。"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from . import win32

log = logging.getLogger("screen_mng")

CONFIG_DIR = Path(os.environ.get("SCREEN_MNG_HOME") or Path(os.environ["APPDATA"]) / "ScreenMng")
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "screen_mng.log"

# 区域：工作区（不含任务栏）的比例 x, y, w, h
ZONES: dict[str, tuple[float, float, float, float]] = {
    "maximize": (0, 0, 1, 1),
    "full": (0, 0, 1, 1),
    "left": (0, 0, 1 / 2, 1),
    "right": (1 / 2, 0, 1 / 2, 1),
    "top": (0, 0, 1, 1 / 2),
    "bottom": (0, 1 / 2, 1, 1 / 2),
    "top-left": (0, 0, 1 / 2, 1 / 2),
    "top-right": (1 / 2, 0, 1 / 2, 1 / 2),
    "bottom-left": (0, 1 / 2, 1 / 2, 1 / 2),
    "bottom-right": (1 / 2, 1 / 2, 1 / 2, 1 / 2),
    "left-third": (0, 0, 1 / 3, 1),
    "center-third": (1 / 3, 0, 1 / 3, 1),
    "right-third": (2 / 3, 0, 1 / 3, 1),
    "left-two-thirds": (0, 0, 2 / 3, 1),
    "right-two-thirds": (1 / 3, 0, 2 / 3, 1),
    "top-third": (0, 0, 1, 1 / 3),
    "middle-third": (0, 1 / 3, 1, 1 / 3),
    "bottom-third": (0, 2 / 3, 1, 1 / 3),
    "top-two-thirds": (0, 0, 1, 2 / 3),
    "bottom-two-thirds": (0, 1 / 3, 1, 2 / 3),
}

ZONE_LABELS = {
    "maximize": "最大化", "full": "铺满", "left": "左半屏", "right": "右半屏",
    "top": "上半屏", "bottom": "下半屏", "top-left": "左上 1/4", "top-right": "右上 1/4",
    "bottom-left": "左下 1/4", "bottom-right": "右下 1/4", "left-third": "左 1/3",
    "center-third": "中 1/3", "right-third": "右 1/3", "left-two-thirds": "左 2/3",
    "right-two-thirds": "右 2/3", "top-third": "上 1/3", "middle-third": "中间 1/3",
    "bottom-third": "下 1/3", "top-two-thirds": "上 2/3", "bottom-two-thirds": "下 2/3",
}

# 捕获时忽略的系统进程
IGNORED_EXES = {
    "textinputhost.exe", "applicationframehost.exe", "shellexperiencehost.exe",
    "searchhost.exe", "startmenuexperiencehost.exe", "lockapp.exe", "systemsettings.exe",
}


# ---------- 配置 ----------

def load_config() -> dict:
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    else:
        cfg = {}
    cfg.setdefault("layouts", {})
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


# ---------- 规则 ----------
# 规则示例：
# {"app": "C:/.../chrome.exe", "args": "", "process": "chrome.exe", "title": "",
#  "monitor": 2, "zone": "top", "launch": true}

def rule_process(rule: dict) -> str:
    """用于匹配窗口的进程名；未写 process 时取 app 的文件名（.exe）。"""
    p = (rule.get("process") or "").strip()
    if not p:
        app = (rule.get("app") or "").strip().strip('"')
        if app.lower().endswith(".exe"):
            p = os.path.basename(app)
    return p.lower()


def rule_matches(rule: dict, w: win32.Window) -> bool:
    proc = rule_process(rule)
    title = rule.get("title") or ""
    if not proc and not title:
        return False
    if proc and w.exe_name.lower() != proc:
        return False
    if title and not re.search(title, w.title, re.IGNORECASE):
        return False
    return True


def rule_name(rule: dict) -> str:
    return rule_process(rule) or os.path.basename(rule.get("app", "")) or rule.get("title", "?")


def resolve_monitor(spec, monitors: list[win32.Monitor]) -> win32.Monitor:
    """spec: "primary" / "secondary" / 编号(1 起) / 设备名如 \\\\.\\DISPLAY2；找不到时退回主显示器。"""
    if spec in (None, "", "primary"):
        return monitors[0]
    if spec == "secondary":
        return monitors[1] if len(monitors) > 1 else monitors[0]
    if isinstance(spec, str) and spec.isdigit():
        spec = int(spec)
    if isinstance(spec, int):
        return monitors[spec - 1] if 1 <= spec <= len(monitors) else monitors[0]
    for m in monitors:
        if m.device.lower() == str(spec).lower():
            return m
    return monitors[0]


def zone_fractions(zone) -> tuple[float, float, float, float]:
    if isinstance(zone, (list, tuple)) and len(zone) == 4:
        return tuple(float(v) for v in zone)
    return ZONES.get(zone or "full", ZONES["full"])


def zone_rect(zone, work: win32.Rect) -> win32.Rect:
    l, t, r, b = work
    w, h = r - l, b - t
    fx, fy, fw, fh = zone_fractions(zone)
    return (l + round(fx * w), t + round(fy * h), l + round((fx + fw) * w), t + round((fy + fh) * h))


def rect_to_zone(rect: win32.Rect, work: win32.Rect):
    """把窗口矩形换算成区域：接近预设区域时用预设名，否则用比例列表。"""
    l, t, r, b = work
    w, h = r - l, b - t
    # 超出工作区的部分裁掉
    x0, y0 = min(max(rect[0], l), r), min(max(rect[1], t), b)
    x1, y1 = min(max(rect[2], x0), r), min(max(rect[3], y0), b)
    frac = ((x0 - l) / w, (y0 - t) / h, (x1 - x0) / w, (y1 - y0) / h)
    for name, z in ZONES.items():
        if name != "maximize" and all(abs(a - b) < 0.015 for a, b in zip(frac, z)):
            return name
    return [round(v, 4) for v in frac]


# ---------- 应用布局 ----------

def launch(rule: dict) -> None:
    app = (rule.get("app") or "").strip().strip('"')
    app = os.path.expandvars(app)
    args = rule.get("args") or ""
    cwd = os.path.dirname(app) if os.path.isfile(app) else None
    os.startfile(app, arguments=args, cwd=cwd)  # ShellExecute：支持 exe / lnk / URI / App Paths


def apply_layout(rules: list[dict], timeout: float = 20.0, report=print) -> bool:
    """按规则摆放窗口：已有窗口直接移动，没有则启动并等待窗口出现。返回是否全部成功。"""
    monitors = win32.list_monitors()
    claimed: set[int] = set()
    placed: list[tuple[int, dict, win32.Rect]] = []
    pending: list[dict] = []
    ok = True

    def place(hwnd, rule) -> win32.Rect:
        mon = resolve_monitor(rule.get("monitor"), monitors)
        zone = rule.get("zone")
        return win32.move_window(hwnd, mon.handle, lambda work: zone_rect(zone, work), zone == "maximize")

    def try_place(rule, windows) -> bool:
        for w in windows:
            if w.hwnd not in claimed and rule_matches(rule, w):
                claimed.add(w.hwnd)
                placed.append((w.hwnd, rule, place(w.hwnd, rule)))
                report(f"✓ {rule_name(rule)} → 显示器 {resolve_monitor(rule.get('monitor'), monitors).number} {rule.get('zone')}")
                return True
        return False

    windows = win32.list_windows()
    for rule in rules:
        if try_place(rule, windows):
            continue
        if not rule.get("app") or rule.get("launch", True) is False:
            report(f"✗ 未找到窗口：{rule_name(rule)}")
            ok = False
            continue
        try:
            launch(rule)
            report(f"… 启动 {rule_name(rule)}")
            pending.append(rule)
        except OSError as e:
            report(f"✗ 启动失败 {rule.get('app')}: {e}")
            ok = False

    deadline = time.monotonic() + timeout
    launched_from = len(placed)
    while pending and time.monotonic() < deadline:
        time.sleep(0.3)
        windows = win32.list_windows()
        pending = [r for r in pending if not try_place(r, windows)]
    for rule in pending:
        report(f"✗ 等待窗口超时：{rule_name(rule)}")
        ok = False

    # Electron/Chromium 程序启动后会恢复自己记住的位置，稍后再校正几次
    fresh = placed[launched_from:]
    for delay in (0.7, 1.5, 2.5) if fresh else ():
        time.sleep(delay)
        for hwnd, rule, rect in fresh:
            if not win32.is_window(hwnd):
                continue
            maxi = rule.get("zone") == "maximize"
            drifted = any(abs(a - b) > 2 for a, b in zip(win32.frame_rect(hwnd), rect))
            if maxi != win32.is_maximized(hwnd) or (not maxi and drifted):
                place(hwnd, rule)
    return ok


# ---------- 捕获当前布局 ----------

def capture_windows() -> list[tuple[win32.Window, dict]]:
    """当前可见窗口 → 规则（未最小化、非系统窗口、非本程序）。"""
    monitors = win32.list_monitors()
    out = []
    for w in win32.list_windows():
        if w.pid == os.getpid() or not w.exe or w.exe_name.lower() in IGNORED_EXES:
            continue
        if win32.is_minimized(w.hwnd):
            continue
        mon = win32.monitor_of_window(w.hwnd, monitors)
        zone = "maximize" if win32.is_maximized(w.hwnd) else rect_to_zone(win32.frame_rect(w.hwnd), mon.work)
        rule = {"app": w.exe, "args": "", "process": w.exe_name, "title": "",
                "monitor": "primary" if mon.primary else mon.number, "zone": zone, "launch": True}
        out.append((w, rule))
    return out


# ---------- 开机自启 ----------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ScreenMng"


def _self_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" -m screen_mng'


def get_autostart() -> str | None:
    """返回开机自动应用的布局名，未设置时为 None。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            cmd, _ = winreg.QueryValueEx(k, RUN_NAME)
    except OSError:
        return None
    m = re.search(r'apply\s+"([^"]*)"', cmd)
    return m.group(1) if m else None


def set_autostart(layout: str | None) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if layout is None:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'{_self_command()} apply "{layout}" --timeout 60')
