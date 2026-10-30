"""Win32 API 的最小 ctypes 封装：显示器、窗口枚举与定位。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SW_MAXIMIZE = 3
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
        ("szDevice", wt.WCHAR * 32),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.c_void_p, MONITORENUMPROC, wt.LPARAM]
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = wt.HMONITOR
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.IsZoomed.argtypes = [wt.HWND]
user32.GetWindow.argtypes = [wt.HWND, ctypes.c_uint]
user32.GetWindow.restype = wt.HWND
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
user32.GetWindowDpiAwarenessContext.argtypes = [wt.HWND]
user32.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
DPI_PER_MONITOR_V2 = -4

Rect = tuple[int, int, int, int]  # left, top, right, bottom


def set_dpi_aware() -> None:
    """使用物理像素坐标，避免多显示器不同缩放时位置错乱。"""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except AttributeError:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def _rect(r: wt.RECT) -> Rect:
    return (r.left, r.top, r.right, r.bottom)


@dataclass
class Monitor:
    number: int  # 1 = 主显示器，其余按从左到右、从上到下编号
    device: str
    primary: bool
    rect: Rect
    work: Rect
    handle: int

    @property
    def label(self) -> str:
        w, h = self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]
        return f"{self.number}{' (主)' if self.primary else ''}  {w}x{h}"


def _monitor_info(hmon) -> MONITORINFOEXW:
    mi = MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    return mi


def list_monitors() -> list[Monitor]:
    found = []

    def cb(hmon, _hdc, _rc, _lp):
        mi = _monitor_info(hmon)
        found.append((hmon, mi.szDevice, bool(mi.dwFlags & MONITORINFOF_PRIMARY), _rect(mi.rcMonitor), _rect(mi.rcWork)))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    found.sort(key=lambda m: (not m[2], m[3][0], m[3][1]))
    return [Monitor(i + 1, dev, prim, rc, work, h) for i, (h, dev, prim, rc, work) in enumerate(found)]


def monitor_of_window(hwnd, monitors: list[Monitor]) -> Monitor:
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    for m in monitors:
        if m.handle == hmon:
            return m
    return monitors[0]


@dataclass
class Window:
    hwnd: int
    title: str
    pid: int
    exe: str  # 完整路径，取不到时为空

    @property
    def exe_name(self) -> str:
        return os.path.basename(self.exe)


def _exe_path(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def _is_cloaked(hwnd) -> bool:
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
    return v.value != 0


def window_title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def list_windows() -> list[Window]:
    """可见的顶层应用窗口（与任务栏上能看到的大致一致），按 Z 序从上到下。"""
    hwnds = []
    user32.EnumWindows(WNDENUMPROC(lambda h, _: hwnds.append(h) or True), 0)
    out = []
    for h in hwnds:
        if not user32.IsWindowVisible(h) or user32.GetWindow(h, GW_OWNER):
            continue
        if user32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW or _is_cloaked(h):
            continue
        title = window_title(h)
        if not title:
            continue
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        out.append(Window(h, title, pid.value, _exe_path(pid.value)))
    return out


def window_rect(hwnd) -> Rect:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return _rect(r)


def frame_rect(hwnd) -> Rect:
    """可见边框（不含 Win10/11 的透明缩放边框）。"""
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        return window_rect(hwnd)
    return _rect(r)


def is_minimized(hwnd) -> bool:
    return bool(user32.IsIconic(hwnd))


def is_maximized(hwnd) -> bool:
    return bool(user32.IsZoomed(hwnd))


def is_window(hwnd) -> bool:
    return bool(user32.IsWindow(hwnd))


def _set_pos(hwnd, l, t, r, b) -> None:
    user32.SetWindowPos(hwnd, None, l, t, r - l, b - t, SWP_NOZORDER | SWP_NOACTIVATE)


@contextmanager
def _thread_dpi(ctx):
    """临时切换本线程的 DPI 感知方式。"""
    old = user32.SetThreadDpiAwarenessContext(ctx) if ctx else None
    try:
        yield
    finally:
        if old:
            user32.SetThreadDpiAwarenessContext(old)


def _borders(hwnd) -> Rect:
    """透明边框宽度（左上右下），换算成当前线程 DPI 下的单位。"""
    logical = window_rect(hwnd)
    with _thread_dpi(DPI_PER_MONITOR_V2):
        wr, fr = window_rect(hwnd), frame_rect(hwnd)  # DWM 边框始终是物理像素
    s = (wr[2] - wr[0]) / max(1, logical[2] - logical[0])
    return tuple(round(v / s) for v in (fr[0] - wr[0], fr[1] - wr[1], wr[2] - fr[2], wr[3] - fr[3]))


def move_window(hwnd, hmonitor, to_rect: Callable[[Rect], Rect], maximize: bool = False) -> Rect:
    """把窗口可见边框放到 to_rect(显示器工作区) 处。返回最终的可见边框（物理像素）。

    非 DPI 感知 / 系统 DPI 感知的窗口会被系统按缩放比例虚拟化坐标，
    所以要切换到与目标窗口相同的 DPI 感知方式下计算和摆放，坐标才一致。
    """
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    with _thread_dpi(user32.GetWindowDpiAwarenessContext(hwnd)):
        target = to_rect(_rect(_monitor_info(hmonitor).rcWork))
        for _ in range(3):  # 跨不同缩放的显示器时窗口会自行调整一次大小，多校正几轮
            bl, bt, br, bb = _borders(hwnd)
            want = (target[0] - bl, target[1] - bt, target[2] + br, target[3] + bb)
            _set_pos(hwnd, *want)
            if all(abs(a - b) <= 1 for a, b in zip(window_rect(hwnd), want)) and _borders(hwnd) == (bl, bt, br, bb):
                break
    if maximize:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
    return frame_rect(hwnd)
