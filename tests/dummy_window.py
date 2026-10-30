"""测试用窗口：python dummy_window.py <标题> [dpi-aware]"""
import ctypes
import sys
import tkinter as tk

if len(sys.argv) > 2:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
root = tk.Tk()
root.title(sys.argv[1])
root.geometry("400x300+100+100")
root.after(60000, root.destroy)
root.mainloop()
