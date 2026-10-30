"""命令行入口。无参数时打开图形界面。"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import sys

from . import core, win32


def _attach_console() -> None:
    # 打包成无控制台的 exe 时，在终端里运行也能看到输出
    if sys.stdout is None and ctypes.windll.kernel32.AttachConsole(-1):
        # CONOUT$ 走 WriteConsoleW，按 UTF-8 写入即可正确显示中文
        sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8")
    for s in (sys.stdout, sys.stderr):
        if s and hasattr(s, "reconfigure"):
            s.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    win32.set_dpi_aware()
    _attach_console()
    p = argparse.ArgumentParser(prog="screen-mng", description="Windows 桌面布局管理")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("apply", help="应用布局")
    a.add_argument("layout")
    a.add_argument("--timeout", type=float, default=20, help="等待新启动程序窗口的秒数")
    sub.add_parser("list", help="列出布局")
    sub.add_parser("monitors", help="列出显示器")
    sub.add_parser("windows", help="列出当前窗口")
    c = sub.add_parser("capture", help="把当前窗口位置保存为布局")
    c.add_argument("layout")
    args = p.parse_args(argv)

    if args.cmd is None:
        from .gui import run
        run()
        return 0

    if args.cmd == "apply":
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=core.LOG_FILE, level=logging.INFO, encoding="utf-8",
                            format="%(asctime)s %(message)s")

        def report(msg):
            logging.info(msg)
            if sys.stdout:
                print(msg)

        layouts = core.load_config()["layouts"]
        if args.layout not in layouts:
            report(f"布局不存在：{args.layout}")
            return 2
        return 0 if core.apply_layout(layouts[args.layout], args.timeout, report) else 1

    if args.cmd == "list":
        for name, rules in core.load_config()["layouts"].items():
            print(f"{name}  ({len(rules)} 个窗口)")
    elif args.cmd == "monitors":
        for m in win32.list_monitors():
            print(f"{m.label}  {m.device}  区域={m.rect}  工作区={m.work}")
    elif args.cmd == "windows":
        monitors = win32.list_monitors()
        for w in win32.list_windows():
            m = win32.monitor_of_window(w.hwnd, monitors)
            print(f"[{m.number}] {w.exe_name:<24} {win32.frame_rect(w.hwnd)}  {w.title[:60]}")
    elif args.cmd == "capture":
        cfg = core.load_config()
        rules = [r for _, r in core.capture_windows()]
        cfg["layouts"][args.layout] = rules
        core.save_config(cfg)
        print(json.dumps(rules, ensure_ascii=False, indent=2))
        print(f"已保存 {len(rules)} 个窗口到布局「{args.layout}」：{core.CONFIG_FILE}")
    return 0
