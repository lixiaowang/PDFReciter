"""
PDF 朗读器入口 — 中文语音朗读
鼠标拖拽框选文本，松开自动朗读。
"""

import tkinter as tk
from tkinter import ttk
import os
import sys

from utils import ensure_font, FONT_SIZE
from app import PDFReaderApp


def main():
    root = tk.Tk()
    root.withdraw()

    # 高分屏模糊修正
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    font_name = ensure_font(root)

    style = ttk.Style()
    style.configure('.', font=(font_name, FONT_SIZE))
    style.configure('TButton', font=(font_name, FONT_SIZE), padding=(10, 5))
    style.configure('TLabel', font=(font_name, FONT_SIZE), padding=(3, 2))
    root.option_add('*Font', (font_name, FONT_SIZE))

    root.deiconify()
    app = PDFReaderApp(root, font_name)

    if len(sys.argv) > 1:
        fp = sys.argv[1]
        if os.path.isfile(fp):
            root.after(300, lambda: app.open_pdf(fp))

    root.mainloop()


if __name__ == '__main__':
    main()
