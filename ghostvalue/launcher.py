"""GUI entry point with file-backed errors for pythonw and installed launchers."""
import sys
import traceback
import tkinter as tk
from tkinter import messagebox
from .paths import DATA_DIR


def report_error(exc_type, exc_value, exc_traceback):
    log = DATA_DIR / 'logs' / 'startup-errors.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as stream:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=stream)
    messagebox.showerror('GhostValue', f'程序遇到错误：{exc_value}\n\n详情已保存到 {log}')


def main():
    window = tk.Tk()
    window.report_callback_exception = report_error
    try:
        from .app import App
        App(window)
        window.mainloop()
    except Exception:
        report_error(*sys.exc_info())
        window.destroy()
