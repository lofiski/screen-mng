"""极简图形界面（tkinter）。"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import core, win32

COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1", "#9c755f"]
CUSTOM = "自定义比例"


def center(win: tk.Toplevel, master: tk.Misc) -> None:
    """对话框显示在主窗口中央。"""
    win.update_idletasks()
    x = master.winfo_rootx() + (master.winfo_width() - win.winfo_reqwidth()) // 2
    y = master.winfo_rooty() + (master.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"{x:+d}{y:+d}")


def zone_label(zone) -> str:
    if isinstance(zone, list):
        return "自定义 " + ",".join(f"{v:g}" for v in zone)
    return core.ZONE_LABELS.get(zone, str(zone))


class RuleDialog(tk.Toplevel):
    """新建 / 编辑一条窗口规则。"""

    def __init__(self, master, monitors: list[win32.Monitor], rule: dict | None = None):
        super().__init__(master)
        self.title("窗口规则")
        self.resizable(False, False)
        self.transient(master)
        self.monitors = monitors
        self.result: dict | None = None
        rule = dict(rule or {"zone": "maximize", "monitor": 1, "launch": True})

        self.v_app = tk.StringVar(value=rule.get("app", ""))
        self.v_args = tk.StringVar(value=rule.get("args", ""))
        self.v_proc = tk.StringVar(value=rule.get("process", ""))
        self.v_title = tk.StringVar(value=rule.get("title", ""))
        mon = core.resolve_monitor(rule.get("monitor"), monitors)
        self.v_mon = tk.StringVar(value=mon.label)
        zone = rule.get("zone", "maximize")
        self.v_zone = tk.StringVar(value=CUSTOM if isinstance(zone, list) else core.ZONE_LABELS.get(zone, "最大化"))
        self.v_custom = tk.StringVar(value=", ".join(f"{v:g}" for v in zone) if isinstance(zone, list) else "")
        self.v_launch = tk.BooleanVar(value=rule.get("launch", True))

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        rows = [
            ("程序路径", self.v_app, "exe / 快捷方式 / URI，例如 chrome.exe"),
            ("启动参数", self.v_args, "可留空"),
            ("进程名", self.v_proc, "用来识别窗口，留空则取程序文件名"),
            ("标题包含", self.v_title, "可选，正则；同一程序多个窗口时区分用"),
        ]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i * 2, column=0, sticky="w", pady=(6, 0))
            e = ttk.Entry(f, textvariable=var, width=52)
            e.grid(row=i * 2, column=1, sticky="we", pady=(6, 0))
            ttk.Label(f, text=hint, foreground="#888").grid(row=i * 2 + 1, column=1, sticky="w")
            if i == 0:
                ttk.Button(f, text="浏览…", command=self.browse).grid(row=0, column=2, padx=(6, 0), pady=(6, 0))
                e.focus_set()

        r = len(rows) * 2
        ttk.Label(f, text="显示器").grid(row=r, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(f, textvariable=self.v_mon, state="readonly", values=[m.label for m in monitors]
                     ).grid(row=r, column=1, sticky="w", pady=(10, 0))
        ttk.Label(f, text="区域").grid(row=r + 1, column=0, sticky="w", pady=(6, 0))
        zf = ttk.Frame(f)
        zf.grid(row=r + 1, column=1, sticky="w", pady=(6, 0))
        cb = ttk.Combobox(zf, textvariable=self.v_zone, state="readonly", width=12,
                          values=list(core.ZONE_LABELS.values()) + [CUSTOM])
        cb.pack(side="left")
        self.custom_entry = ttk.Entry(zf, textvariable=self.v_custom, width=26)
        self.custom_entry.pack(side="left", padx=(8, 0))
        ttk.Label(f, text="自定义：x, y, 宽, 高（占工作区比例 0~1）", foreground="#888").grid(row=r + 2, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda _: self._sync_custom())
        self._sync_custom()
        ttk.Checkbutton(f, text="窗口不存在时自动启动程序", variable=self.v_launch).grid(
            row=r + 3, column=1, sticky="w", pady=(8, 0))

        bf = ttk.Frame(f)
        bf.grid(row=r + 4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(bf, text="确定", command=self.ok).pack(side="left", padx=4)
        ttk.Button(bf, text="取消", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda _: self.ok())
        self.bind("<Escape>", lambda _: self.destroy())
        center(self, master)
        self.grab_set()
        self.wait_window()

    def _sync_custom(self):
        self.custom_entry.configure(state="normal" if self.v_zone.get() == CUSTOM else "disabled")

    def browse(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("程序", "*.exe *.lnk"), ("所有文件", "*.*")])
        if path:
            path = os.path.normpath(path)
            self.v_app.set(path)
            if path.lower().endswith(".exe"):
                self.v_proc.set(os.path.basename(path))

    def ok(self):
        zone_lbl = self.v_zone.get()
        if zone_lbl == CUSTOM:
            try:
                zone = [float(v) for v in self.v_custom.get().replace("，", ",").split(",")]
                assert len(zone) == 4 and all(0 <= v <= 1 for v in zone)
            except (ValueError, AssertionError):
                messagebox.showerror("区域", "自定义区域格式：x, y, 宽, 高，例如 0, 0, 0.5, 1", parent=self)
                return
        else:
            zone = next(k for k, v in core.ZONE_LABELS.items() if v == zone_lbl)
        rule = {
            "app": self.v_app.get().strip().strip('"'),
            "args": self.v_args.get().strip(),
            "process": self.v_proc.get().strip(),
            "title": self.v_title.get().strip(),
            "monitor": next(m.number for m in self.monitors if m.label == self.v_mon.get()),
            "zone": zone,
            "launch": self.v_launch.get(),
        }
        if not core.rule_process(rule) and not rule["title"]:
            messagebox.showerror("规则", "无法识别窗口：请填写「进程名」或「标题包含」。", parent=self)
            return
        self.result = rule
        self.destroy()


class CaptureDialog(tk.Toplevel):
    """勾选要保存到布局中的当前窗口。"""

    def __init__(self, master, items: list[tuple[win32.Window, dict]]):
        super().__init__(master)
        self.title("捕获当前窗口")
        self.transient(master)
        self.result: list[dict] | None = None
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="勾选要保存的窗口（先把窗口摆好再捕获）：").pack(anchor="w")
        self.vars = []
        for w, rule in items:
            v = tk.BooleanVar(value=True)
            self.vars.append((v, rule))
            text = f"[显示器 {core.resolve_monitor(rule['monitor'], win32.list_monitors()).number}] " \
                   f"{w.exe_name}  —  {w.title[:50]}  ({zone_label(rule['zone'])})"
            ttk.Checkbutton(f, text=text, variable=v).pack(anchor="w", pady=1)
        bf = ttk.Frame(f)
        bf.pack(anchor="e", pady=(10, 0))
        ttk.Button(bf, text="保存", command=self.ok).pack(side="left", padx=4)
        ttk.Button(bf, text="取消", command=self.destroy).pack(side="left")
        center(self, master)
        self.grab_set()
        self.wait_window()

    def ok(self):
        self.result = [r for v, r in self.vars if v.get()]
        self.destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("ScreenMng 桌面布局")
        s = root.winfo_fpixels("1i") / 96  # 界面缩放比例
        root.minsize(int(820 * s), int(440 * s))
        ttk.Style().configure("Treeview", rowheight=int(22 * s))
        try:
            self.cfg = core.load_config()
        except ValueError as e:
            backup = core.CONFIG_FILE.with_name("config.broken.json")
            core.CONFIG_FILE.replace(backup)
            messagebox.showwarning("配置文件", f"配置文件格式错误，已备份为\n{backup}\n\n{e}")
            self.cfg = core.load_config()
        self.mtime = self._cfg_mtime()
        self.monitors = win32.list_monitors()
        self.msgs: queue.Queue[str] = queue.Queue()

        top = ttk.Frame(root, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        ttk.Label(top, text="布局").pack(side="left")
        self.v_layout = tk.StringVar()
        self.cb_layout = ttk.Combobox(top, textvariable=self.v_layout, state="readonly", width=24)
        self.cb_layout.pack(side="left", padx=6)
        self.cb_layout.bind("<<ComboboxSelected>>", lambda _: self.refresh_rules())
        for text, cmd in (("新建", self.new_layout), ("重命名", self.rename_layout), ("删除", self.delete_layout)):
            ttk.Button(top, text=text, command=cmd, width=7).pack(side="left", padx=2)
        ttk.Button(top, text="▶ 应用布局", command=self.apply).pack(side="right")

        mid = ttk.Frame(root, padding=10)
        mid.pack(fill="both", expand=True)
        cols = ("app", "monitor", "zone", "title", "launch")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse", height=10)
        for c, text, w in zip(cols, ("程序", "显示器", "区域", "标题包含", "自动启动"), (150, 60, 110, 80, 70)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=int(w * s), stretch=c == "app")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _: self.edit_rule())
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.draw_preview())
        self.canvas = tk.Canvas(mid, width=int(300 * s), height=int(240 * s), bg="#f4f4f4", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", padx=(10, 0))
        self.canvas.bind("<Configure>", lambda _: self.draw_preview())

        bar = ttk.Frame(root, padding=(10, 0, 10, 6))
        bar.pack(fill="x")
        for text, cmd in (("添加窗口", self.add_rule), ("编辑", self.edit_rule), ("删除", self.delete_rule),
                          ("上移", lambda: self.move_rule(-1)), ("下移", lambda: self.move_rule(1)),
                          ("捕获当前窗口…", self.capture)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        bottom = ttk.Frame(root, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        self.v_auto = tk.BooleanVar()
        ttk.Checkbutton(bottom, text="开机时自动应用此布局", variable=self.v_auto,
                        command=self.toggle_autostart).pack(side="left")
        ttk.Button(bottom, text="打开配置文件", command=self.open_config).pack(side="right")
        ttk.Button(bottom, text="识别显示器", command=self.identify).pack(side="right", padx=4)
        self.status = ttk.Label(root, text="", padding=(10, 0, 10, 8), foreground="#555")
        self.status.pack(fill="x")

        root.bind("<FocusIn>", lambda e: self.reload_if_changed() if e.widget is root else None)
        self.refresh_layouts()
        self._poll_msgs()

    # ---------- 数据 ----------
    def _cfg_mtime(self):
        return core.CONFIG_FILE.stat().st_mtime if core.CONFIG_FILE.exists() else 0

    def save(self):
        core.save_config(self.cfg)
        self.mtime = self._cfg_mtime()

    def reload_if_changed(self):
        if self._cfg_mtime() != self.mtime:
            try:
                self.cfg = core.load_config()
            except ValueError as e:
                self.set_status(f"配置文件格式错误：{e}")
                return
            self.mtime = self._cfg_mtime()
            self.refresh_layouts(self.v_layout.get())
            self.set_status("已重新加载配置文件")

    @property
    def layouts(self) -> dict:
        return self.cfg["layouts"]

    @property
    def rules(self) -> list[dict]:
        return self.layouts.setdefault(self.v_layout.get(), []) if self.v_layout.get() else []

    def selected_index(self) -> int | None:
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else None

    # ---------- 刷新 ----------
    def refresh_layouts(self, select: str | None = None):
        names = list(self.layouts)
        self.cb_layout["values"] = names
        if select in names:
            self.v_layout.set(select)
        elif self.v_layout.get() not in names:
            self.v_layout.set(names[0] if names else "")
        self.refresh_rules()

    def refresh_rules(self, select: int | None = None):
        self.tree.delete(*self.tree.get_children())
        for r in self.rules:
            mon = core.resolve_monitor(r.get("monitor"), self.monitors)
            self.tree.insert("", "end", values=(
                core.rule_name(r), mon.number, zone_label(r.get("zone")), r.get("title", ""),
                "是" if r.get("launch", True) else "否"))
        if select is not None and self.tree.get_children():
            item = self.tree.get_children()[max(0, min(select, len(self.rules) - 1))]
            self.tree.selection_set(item)
        self.v_auto.set(bool(self.v_layout.get()) and core.get_autostart() == self.v_layout.get())
        self.draw_preview()

    def draw_preview(self):
        c = self.canvas
        c.delete("all")
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 20 or not self.monitors:
            return
        L = min(m.rect[0] for m in self.monitors)
        T = min(m.rect[1] for m in self.monitors)
        R = max(m.rect[2] for m in self.monitors)
        B = max(m.rect[3] for m in self.monitors)
        pad = 12
        s = min((cw - 2 * pad) / (R - L), (ch - 2 * pad) / (B - T))
        ox = (cw - (R - L) * s) / 2
        oy = (ch - (B - T) * s) / 2

        def tx(rect):
            return (ox + (rect[0] - L) * s, oy + (rect[1] - T) * s, ox + (rect[2] - L) * s, oy + (rect[3] - T) * s)

        for m in self.monitors:
            x0, y0, x1, y1 = tx(m.rect)
            c.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#999", width=2)
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=str(m.number), fill="#ddd", font=("Segoe UI", 28, "bold"))
        sel = self.selected_index()
        for i, r in enumerate(self.rules):
            mon = core.resolve_monitor(r.get("monitor"), self.monitors)
            x0, y0, x1, y1 = tx(core.zone_rect(r.get("zone"), mon.work))
            color = COLORS[i % len(COLORS)]
            c.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=color, width=4 if i == sel else 2,
                               fill=color, stipple="gray25")
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=core.rule_name(r).removesuffix(".exe"),
                          fill=color, font=("Segoe UI", 9, "bold"), width=max(30, x1 - x0 - 6))

    def set_status(self, text: str):
        self.status.configure(text=text)

    def _poll_msgs(self):
        while not self.msgs.empty():
            self.set_status(self.msgs.get())
        self.root.after(150, self._poll_msgs)

    # ---------- 布局 ----------
    def ask_name(self, title, initial=""):
        name = simpledialog.askstring(title, "布局名称：", initialvalue=initial, parent=self.root)
        name = (name or "").strip()
        if name and name in self.layouts and name != initial:
            if not messagebox.askyesno(title, f"布局「{name}」已存在，覆盖？", parent=self.root):
                return None
        return name or None

    def new_layout(self):
        name = self.ask_name("新建布局", f"布局{len(self.layouts) + 1}")
        if name:
            self.layouts[name] = []
            self.save()
            self.refresh_layouts(name)

    def rename_layout(self):
        old = self.v_layout.get()
        if not old:
            return
        name = self.ask_name("重命名布局", old)
        if name and name != old:
            self.cfg["layouts"] = {(name if k == old else k): v for k, v in self.layouts.items() if k != name or k == old}
            self.save()
            if core.get_autostart() == old:
                core.set_autostart(name)
            self.refresh_layouts(name)

    def delete_layout(self):
        name = self.v_layout.get()
        if name and messagebox.askyesno("删除布局", f"删除布局「{name}」？", parent=self.root):
            del self.layouts[name]
            self.save()
            if core.get_autostart() == name:
                core.set_autostart(None)
            self.refresh_layouts()

    def ensure_layout(self) -> bool:
        if not self.v_layout.get():
            self.new_layout()
        return bool(self.v_layout.get())

    # ---------- 规则 ----------
    def add_rule(self):
        if not self.ensure_layout():
            return
        d = RuleDialog(self.root, self.monitors)
        if d.result:
            self.rules.append(d.result)
            self.save()
            self.refresh_rules(len(self.rules) - 1)

    def edit_rule(self):
        i = self.selected_index()
        if i is None:
            return
        d = RuleDialog(self.root, self.monitors, self.rules[i])
        if d.result:
            self.rules[i] = d.result
            self.save()
            self.refresh_rules(i)

    def delete_rule(self):
        i = self.selected_index()
        if i is not None:
            del self.rules[i]
            self.save()
            self.refresh_rules(i)

    def move_rule(self, delta: int):
        i = self.selected_index()
        if i is None or not 0 <= i + delta < len(self.rules):
            return
        r = self.rules
        r[i], r[i + delta] = r[i + delta], r[i]
        self.save()
        self.refresh_rules(i + delta)

    def capture(self):
        items = core.capture_windows()
        if not items:
            messagebox.showinfo("捕获", "没有可捕获的窗口。", parent=self.root)
            return
        d = CaptureDialog(self.root, items)
        if not d.result:
            return
        name = self.ask_name("保存为布局", self.v_layout.get() or "布局1")
        if name:
            self.layouts[name] = d.result
            self.save()
            self.refresh_layouts(name)
            self.set_status(f"已保存 {len(d.result)} 个窗口到「{name}」")

    # ---------- 动作 ----------
    def apply(self):
        rules = list(self.rules)
        if not rules:
            self.set_status("当前布局没有窗口规则")
            return
        self.monitors = win32.list_monitors()
        self.set_status("正在应用…")

        def work():
            logs = []

            def report(msg):
                logs.append(msg)
                self.msgs.put(msg)

            ok = core.apply_layout(rules, report=report)
            fails = [m for m in logs if m.startswith("✗")]
            self.msgs.put("布局已应用" if ok else "部分失败：" + "；".join(fails))

        threading.Thread(target=work, daemon=True).start()

    def toggle_autostart(self):
        name = self.v_layout.get()
        if not name:
            self.v_auto.set(False)
            return
        core.set_autostart(name if self.v_auto.get() else None)
        self.set_status(f"开机自动应用「{name}」" if self.v_auto.get() else "已取消开机自动应用")

    def open_config(self):
        if not core.CONFIG_FILE.exists():
            self.save()
        subprocess.Popen(["notepad.exe", str(core.CONFIG_FILE)])

    def identify(self):
        self.monitors = win32.list_monitors()
        self.draw_preview()
        for m in self.monitors:
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            tk.Label(t, text=str(m.number), font=("Segoe UI", 96, "bold"), fg="white", bg="#4e79a7",
                     padx=40).pack()
            t.update_idletasks()
            w, h = t.winfo_reqwidth(), t.winfo_reqheight()
            cx, cy = (m.rect[0] + m.rect[2]) // 2, (m.rect[1] + m.rect[3]) // 2
            t.geometry(f"{w}x{h}{cx - w // 2:+d}{cy - h // 2:+d}")
            t.after(2000, t.destroy)


def run():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
