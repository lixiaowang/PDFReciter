"""
PDF 朗读器主界面 — 连续滚动、拖拽框选、TTS 朗读。
"""

import fitz
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk
import bisect
import os
import re
import threading

from tts import TTSEngine
from utils import (
    FONT_SIZE, load_positions, save_positions, file_key
)


class PDFReaderApp:

    PAGE_GAP = 6

    def __init__(self, root, font_name):
        self.root = root
        self._font = font_name
        self.root.title("PDF 朗读器 — 中文语音朗读")
        self.root.geometry("1300x850")
        self.root.minsize(500, 400)

        # ---- 文档 ----
        self.doc = None
        self.filepath = None
        self.total_pages = 0

        # ---- 缩放 ----
        self.zoom = 1.5
        self._auto_fit = True

        # ---- 连续滚动布局 ----
        self._page_heights = []
        self._page_offsets = []
        self._total_height = 0
        self._loaded = set()
        self._page_images = {}
        self._max_cached = 12

        # ---- 文本跨度 {page_num: [line_of_spans, ...]} ----
        # 每个 line_of_spans = [span_dict, ...]  行内已按 x 排序
        self._page_lines = {}

        # ---- 拖拽框选 ----
        self._sel_start = None
        self._sel_rect = None
        self._sel_text = ""
        self._drag_active = False

        # ---- 位置记忆 ----
        self._positions = {}

        # ---- TTS ----
        self.tts = TTSEngine()
        self._reading = False
        self._tts_thread = None

        # ---- 界面 ----
        self._build_menu()
        self._build_toolbar()
        self._build_canvas()
        self._build_statusbar()
        self._bind_keys()
        self._draw_placeholder()

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.bind('<Configure>', self._on_window_configure)
        self._resize_after = None
        self._zoom_after_id = None

    # ===================================================================
    # UI 构建
    # ===================================================================

    def _build_menu(self):
        mb = tk.Menu(self.root, font=(self._font, 18))
        self.root.config(menu=mb)

        fm = tk.Menu(mb, tearoff=0, font=(self._font, 18))
        mb.add_cascade(label="文件", menu=fm)
        fm.add_command(label="打开 PDF...  Ctrl+O", command=self.open_pdf)
        fm.add_separator()
        fm.add_command(label="退出  Ctrl+Q", command=self._on_close)

        vm = tk.Menu(mb, tearoff=0, font=(self._font, 18))
        mb.add_cascade(label="视图", menu=vm)
        vm.add_command(label="放大  Ctrl+=", command=self.zoom_in)
        vm.add_command(label="缩小  Ctrl+-", command=self.zoom_out)
        vm.add_command(label="适应宽度  Ctrl+W", command=self.fit_width)

        sm = tk.Menu(mb, tearoff=0, font=(self._font, 18))
        mb.add_cascade(label="语音", menu=sm)
        sm.add_command(label="朗读选中文本  Space", command=self.read_selected)
        sm.add_command(label="停止朗读  Esc", command=self.stop_reading)
        sm.add_separator()
        sm.add_command(label="语速加快", command=lambda: self._adj_speed(20))
        sm.add_command(label="语速减慢", command=lambda: self._adj_speed(-20))
        sm.add_separator()
        sm.add_command(label="慢速 (100)", command=lambda: self._set_speed(100))
        sm.add_command(label="正常 (160)", command=lambda: self._set_speed(160))
        sm.add_command(label="快速 (240)", command=lambda: self._set_speed(240))

        hm = tk.Menu(mb, tearoff=0, font=(self._font, 18))
        mb.add_cascade(label="帮助", menu=hm)
        hm.add_command(label="关于 PDFReciter", command=self._show_about)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        style = ttk.Style()
        style.configure('Tool.TButton', font=(self._font, 18), padding=(14, 6))
        style.configure('Tool.TLabel', font=(self._font, 18), padding=(6, 3))

        B = lambda t, c: ttk.Button(bar, text=t, command=c, style='Tool.TButton')
        L = lambda t, w: ttk.Label(bar, text=t, width=w, anchor=tk.CENTER,
                                   style='Tool.TLabel')
        S = lambda: ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        B("打开", self.open_pdf).pack(side=tk.LEFT, padx=3); S()
        self._page_label = L("0 / 0", 10)
        self._page_label.pack(side=tk.LEFT, padx=4); S()
        B("放大", self.zoom_in).pack(side=tk.LEFT, padx=3)
        B("缩小", self.zoom_out).pack(side=tk.LEFT, padx=3)
        self._zoom_label = L("150%", 6)
        self._zoom_label.pack(side=tk.LEFT, padx=4)
        B("适应宽度", self.fit_width).pack(side=tk.LEFT, padx=3); S()
        B("朗读", self.read_selected).pack(side=tk.LEFT, padx=3)
        B("停止", self.stop_reading).pack(side=tk.LEFT, padx=3); S()
        B("慢速", lambda: self._set_speed(100)).pack(side=tk.LEFT, padx=1)
        B("正常", lambda: self._set_speed(160)).pack(side=tk.LEFT, padx=1)
        B("快速", lambda: self._set_speed(240)).pack(side=tk.LEFT, padx=1)
        self._speed_label = L("语速:160", 8)
        self._speed_label.pack(side=tk.LEFT, padx=4)

    def _build_canvas(self):
        cf = ttk.Frame(self.root)
        cf.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(cf, bg='#555555', cursor='cross',
                                highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._v_scroll = ttk.Scrollbar(cf, orient=tk.VERTICAL,
                                       command=self._on_scroll_y)
        self._v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._h_scroll = ttk.Scrollbar(self.root, orient=tk.HORIZONTAL,
                                       command=self._on_scroll_x)
        self._h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(xscrollcommand=self._h_scroll.set,
                              yscrollcommand=self._v_scroll.set)

        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<MouseWheel>', self._on_wheel)
        self.canvas.bind('<Button-4>', self._on_wheel)
        self.canvas.bind('<Button-5>', self._on_wheel)

    def _build_statusbar(self):
        sf = ttk.Frame(self.root, relief=tk.SUNKEN)
        sf.pack(side=tk.BOTTOM, fill=tk.X)

        style = ttk.Style()
        style.configure('Status.TLabel', font=(self._font, 18), padding=(6, 4))

        self._status_var = tk.StringVar(
            value="就绪 — Ctrl+O 或点击「打开」按钮打开 PDF，拖拽鼠标框选文本后自动朗读")
        ttk.Label(sf, textvariable=self._status_var, anchor=tk.W,
                  style='Status.TLabel').pack(side=tk.LEFT, fill=tk.X, expand=True)

        tts_info = (f"语音: {self.tts.voice_name}"
                    if self.tts.available else "语音: 不可用")
        self._tts_var = tk.StringVar(value=tts_info)
        ttk.Label(sf, textvariable=self._tts_var, anchor=tk.E,
                  style='Status.TLabel').pack(side=tk.RIGHT)

    def _bind_keys(self):
        r = self.root
        r.bind('<Control-o>', lambda e: self.open_pdf())
        r.bind('<Control-O>', lambda e: self.open_pdf())
        r.bind('<Control-q>', lambda e: self._on_close())
        r.bind('<Control-Q>', lambda e: self._on_close())
        r.bind('<Control-equal>', lambda e: self.zoom_in())
        r.bind('<Control-plus>', lambda e: self.zoom_in())
        r.bind('<Control-minus>', lambda e: self.zoom_out())
        r.bind('<Control-w>', lambda e: self.fit_width())
        r.bind('<Control-W>', lambda e: self.fit_width())
        r.bind('<Prior>', lambda e: self._jump_page(-1))
        r.bind('<Next>', lambda e: self._jump_page(1))
        r.bind('<Home>', lambda e: self._scroll_to_page(0))
        r.bind('<End>', lambda e: self._scroll_to_page(self.total_pages - 1))
        r.bind('<space>', lambda e: self._on_space())
        r.bind('<Escape>', lambda e: self._cancel_selection())

    def _on_canvas_configure(self, event):
        """画布大小变化时，如果没有文档则重绘居中占位文字。"""
        if not self.doc:
            self._draw_placeholder()

    def _draw_placeholder(self):
        self.canvas.delete('all')
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        cx = cw // 2 if cw > 10 else 400
        cy = ch // 2 if ch > 10 else 300
        self.canvas.create_text(
            cx, cy,
            text="按 Ctrl+O 或点击「打开」按钮选择 PDF 文件\n\n鼠标拖拽即可框选文本朗读\n\n—— PDFReciter ——",
            font=(self._font, 24), fill='#AAAAAA', justify=tk.CENTER,
            anchor=tk.CENTER, tags='placeholder')

    # ===================================================================
    # 布局
    # ===================================================================

    def _calc_layout(self):
        self._page_heights = []
        self._page_offsets = []
        y = 0.0
        z = self.zoom
        for i in range(self.total_pages):
            h = self.doc[i].rect.height * z + self.PAGE_GAP
            self._page_heights.append(h)
            self._page_offsets.append(y)
            y += h
        self._total_height = y

    def _page_at_y(self, canvas_y):
        if not self._page_offsets:
            return -1
        i = bisect.bisect_right(self._page_offsets, canvas_y) - 1
        if i < 0:
            i = 0
        if i >= self.total_pages:
            i = self.total_pages - 1
        if canvas_y <= self._page_offsets[i] + self._page_heights[i]:
            return i
        return -1

    # ===================================================================
    # 渲染
    # ===================================================================

    def _rebuild_layout(self, *, keep_position=True):
        """重建布局并渲染。先离屏渲染再原子替换，避免闪烁空白。"""
        if not self.doc:
            return
        old_page = 0
        old_frac = 0.0
        if keep_position and self._page_offsets:
            top_y = self.canvas.canvasy(0)
            old_page = self._page_at_y(top_y)
            if old_page >= 0:
                page_top = self._page_offsets[old_page]
                page_h = self._page_heights[old_page]
                old_frac = ((top_y - page_top) / page_h) if page_h > 0 else 0.0

        self._calc_layout()
        self.canvas.configure(scrollregion=(0, 0, 1, self._total_height))

        # 离屏渲染所有可见页，全部就绪后再一次性放到画布上
        first, last = self._visible_page_range()
        new_images = {}
        for p in range(first, last + 1):
            photo = self._render_page_to_image(p)
            if photo:
                new_images[p] = photo

        # 原子替换
        self._clear_selection()
        self.canvas.delete('all')
        self._loaded.clear()
        self._page_images.clear()

        for p, photo in new_images.items():
            y0 = self._page_offsets[p]
            self.canvas.create_image(0, y0, anchor=tk.NW, image=photo,
                                     tags=(f'page_{p}',))
            self._page_images[p] = photo
            self._loaded.add(p)

        if keep_position and 0 <= old_page < self.total_pages:
            target_y = (self._page_offsets[old_page]
                        + old_frac * self._page_heights[old_page])
            denom = self._total_height
            self.root.after(10, lambda: self.canvas.yview_moveto(
                target_y / denom if denom > 0 else 0.0))

    def _render_page_to_image(self, page_num):
        """离屏渲染一页，返回 PhotoImage。同时预提取文本行。"""
        z = self.zoom
        page = self.doc[page_num]
        mat = fitz.Matrix(z, z)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        photo = ImageTk.PhotoImage(img)
        if page_num not in self._page_lines:
            self._page_lines[page_num] = self._extract_lines(page)
        return photo

    def _visible_page_range(self):
        top = max(0, int(self.canvas.canvasy(0)))
        bot = top + self.canvas.winfo_height()
        if bot <= 0:
            return 0, 0
        first = self._page_at_y(top)
        last = self._page_at_y(bot)
        if first < 0:
            first = 0
        if last < 0:
            last = max(0, self.total_pages - 1)
        return max(0, first - 1), min(self.total_pages - 1, last + 1)

    def _render_visible(self):
        if not self.doc:
            return
        first, last = self._visible_page_range()
        want = set(range(first, last + 1))

        for p in list(self._loaded):
            if p not in want:
                self.canvas.delete(f'page_{p}')
                self._page_images.pop(p, None)
                self._loaded.discard(p)

        for p in want:
            if p not in self._loaded:
                self._render_page(p)

        if len(self._loaded) > self._max_cached:
            surplus = sorted(self._loaded - want,
                             key=lambda x: abs(x - (first + last) // 2))
            for p in surplus:
                if len(self._loaded) <= self._max_cached:
                    break
                self.canvas.delete(f'page_{p}')
                self._page_images.pop(p, None)
                self._loaded.discard(p)

    def _render_page(self, page_num):
        z = self.zoom
        page = self.doc[page_num]
        mat = fitz.Matrix(z, z)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        photo = ImageTk.PhotoImage(img)
        self._page_images[page_num] = photo
        y0 = self._page_offsets[page_num]

        self.canvas.create_image(0, y0, anchor=tk.NW, image=photo,
                                 tags=(f'page_{page_num}',))
        self._loaded.add(page_num)

        if page_num not in self._page_lines:
            self._page_lines[page_num] = self._extract_lines(page)

    # ------------------------------------------------------------------
    # 文本提取 — 保留行结构，行内按 x 排序
    # ------------------------------------------------------------------

    def _extract_lines(self, page):
        """提取一页的文本：每行是一个 span 列表，行内已按 x 坐标排序。
        返回  [[span_dict, ...],  [span_dict, ...],  ...]
        """
        lines = []
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                spans = []
                for sp in line["spans"]:
                    t = sp["text"]
                    if not t.strip():
                        continue
                    spans.append({"text": t, "bbox": tuple(sp["bbox"])})
                if spans:
                    # 行内按 x 排序 — 修复中英文/数字混排时 PDF 内部顺序
                    # 与视觉顺序不一致的问题
                    spans.sort(key=lambda s: s["bbox"][0])
                    lines.append(spans)
        return lines

    # ===================================================================
    # 拖拽框选
    # ===================================================================

    def _on_press(self, event):
        if not self._page_offsets:
            return
        self._clear_selection()
        self._drag_active = True
        self._sel_start = (self.canvas.canvasx(event.x),
                           self.canvas.canvasy(event.y))

    def _on_drag(self, event):
        if not self._drag_active or self._sel_start is None:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        x0, y0 = self._sel_start

        if self._sel_rect is not None:
            self.canvas.delete(self._sel_rect)

        self._sel_rect = self.canvas.create_rectangle(
            x0, y0, cx, cy,
            outline='#2196F3', width=2,
            fill='#64B5F6', stipple='gray25',
            dash=(6, 3), tags='sel_rect')

    def _on_release(self, event):
        self._drag_active = False
        if self._sel_start is None:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        rx0, rx1 = sorted([self._sel_start[0], cx])
        ry0, ry1 = sorted([self._sel_start[1], cy])
        self._sel_start = None

        if (rx1 - rx0) < 3 and (ry1 - ry0) < 3:
            self._clear_selection()
            return

        collected = self._collect_in_rect(rx0, ry0, rx1, ry1)
        if not collected:
            self._clear_selection()
            self._status_var.set("框选范围内无可读取的文本")
            return

        self._sel_text = collected
        preview = collected[:100] + ("…" if len(collected) > 100 else "")
        self._status_var.set(f"已选中: {preview}")

        if not self._reading:
            self._do_read(collected)

    # ------------------------------------------------------------------
    # 框选文本收集 — 按行结构排序，解决中英混排顺序问题
    # ------------------------------------------------------------------

    def _collect_in_rect(self, rx0, ry0, rx1, ry1):
        """收集选框（画布坐标）覆盖的文本。先按行排，行内按 x 排。"""
        z = self.zoom
        line_hits = []  # [(page, line_canvas_y, [(span_x, text), ...])]

        for pg in list(self._loaded):
            if pg not in self._page_lines:
                continue
            page_y0 = self._page_offsets[pg]
            page_y1 = page_y0 + self._page_heights[pg]
            if ry1 < page_y0 or ry0 > page_y1:
                continue

            for line_spans in self._page_lines[pg]:
                # 行的画布 y 范围（取整行 span 的 min/max）
                ly0 = min(s["bbox"][1] for s in line_spans) * z + page_y0
                ly1 = max(s["bbox"][3] for s in line_spans) * z + page_y0
                if ly1 < ry0 or ly0 > ry1:
                    continue

                selected = []
                for sp in line_spans:
                    sx0, sy0_pdf, sx1, sy1_pdf = sp["bbox"]
                    scy0 = sy0_pdf * z + page_y0
                    scy1 = sy1_pdf * z + page_y0
                    scx0 = sx0 * z
                    scx1 = sx1 * z
                    if (scx0 <= rx1 and scx1 >= rx0
                            and scy0 <= ry1 and scy1 >= ry0):
                        selected.append((scx0, sp["text"]))
                if selected:
                    # 行内按 x 排序（即使 _extract_lines 已排序，这里再确保一次）
                    selected.sort(key=lambda t: t[0])
                    line_hits.append((pg, ly0, selected))

        if not line_hits:
            return ""

        # 按页面 → 行 y → 行内 x 排序
        line_hits.sort(key=lambda h: (h[0], h[1]))
        return "".join(t for _, _, spans in line_hits for _, t in spans)

    # ------------------------------------------------------------------

    def _clear_selection(self):
        if self._sel_rect is not None:
            self.canvas.delete(self._sel_rect)
            self._sel_rect = None
        self._sel_text = ""
        self._sel_start = None
        self._drag_active = False

    def _cancel_selection(self, event=None):
        if self._reading:
            self.stop_reading()
        else:
            self._clear_selection()
            self._status_var.set("已取消选择")

    # ===================================================================
    # 滚轮 / 滚动条
    # ===================================================================

    def _on_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-2, 'units')
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(2, 'units')
        self.root.after(60, self._render_visible)

    def _on_scroll_y(self, *args):
        self.canvas.yview(*args)
        self.root.after(60, self._render_visible)

    def _on_scroll_x(self, *args):
        self.canvas.xview(*args)

    # ===================================================================
    # 缩放
    # ===================================================================

    def _set_zoom(self, new_zoom):
        """设置缩放，100ms 防抖避免快速连续缩放时反复重建。"""
        self.zoom = max(0.2, min(8.0, new_zoom))
        self._zoom_label.config(text=f"{int(self.zoom * 100)}%")
        if self._zoom_after_id is not None:
            self.root.after_cancel(self._zoom_after_id)
        self._zoom_after_id = self.root.after(100, self._do_zoom_render)

    def _do_zoom_render(self):
        self._zoom_after_id = None
        self._rebuild_layout(keep_position=True)

    def zoom_in(self):
        self._auto_fit = False
        self._set_zoom(self.zoom * 1.2)

    def zoom_out(self):
        self._auto_fit = False
        self._set_zoom(self.zoom / 1.2)

    def fit_width(self):
        if not self.doc:
            return
        cw = self.canvas.winfo_width()
        if cw < 20:
            return
        pw = self.doc[0].rect.width
        self._auto_fit = True
        self._set_zoom((cw - 20) / pw if pw > 0 else 1.0)

    def _auto_fit_width(self):
        if not self.doc or not self._auto_fit:
            return
        cw = self.canvas.winfo_width()
        if cw < 20:
            return
        pw = self.doc[0].rect.width
        new_zoom = (cw - 20) / pw if pw > 0 else 1.0
        if abs(self.zoom - new_zoom) < 0.005:
            return
        self._set_zoom(new_zoom)

    def _on_window_configure(self, event):
        if event.widget is not self.root or not self.doc:
            return
        if self._resize_after is not None:
            self.root.after_cancel(self._resize_after)
        self._resize_after = self.root.after(200, self._auto_fit_width)

    # ===================================================================
    # 导航
    # ===================================================================

    def _scroll_to_page(self, page_num):
        if not self.doc or page_num < 0 or page_num >= self.total_pages:
            return
        target = self._page_offsets[page_num]
        denom = self._total_height
        self.canvas.yview_moveto(target / denom if denom > 0 else 0.0)
        self.root.after(60, self._render_visible)

    def _jump_page(self, delta):
        if not self.doc:
            return
        top_y = self.canvas.canvasy(0)
        cur = self._page_at_y(top_y)
        if cur < 0:
            cur = 0
        self._scroll_to_page(max(0, min(self.total_pages - 1, cur + delta)))

    # ===================================================================
    # TTS
    # ===================================================================

    def read_selected(self, event=None):
        if self._reading:
            return
        text = self._sel_text
        if not text:
            self._status_var.set("请先拖拽鼠标框选要朗读的文本")
            return
        self._do_read(text)

    def _do_read(self, text):
        if not self.tts.available:
            self._status_var.set("TTS 不可用")
            return

        self._reading = True
        clean = re.sub(r'\s+', '', text)
        preview = clean[:80] + ("…" if len(clean) > 80 else "")
        self._status_var.set(f"朗读中: {preview}")

        def _run():
            try:
                self.tts.reset()
                if not self.tts.available:
                    self.root.after(0, lambda: self._status_var.set("TTS 引擎初始化失败"))
                    return
                self.tts.say(clean)
                self.tts.run_and_wait()
            except Exception as e:
                self.root.after(0, lambda e=e: self._status_var.set(f"朗读出错: {e}"))
            finally:
                self._reading = False
                self.root.after(0, lambda: self._status_var.set("朗读完成"))

        self._tts_thread = threading.Thread(target=_run, daemon=True)
        self._tts_thread.start()

    def stop_reading(self, event=None):
        self.tts.stop()
        self._reading = False
        self._status_var.set("已停止朗读")

    def _set_speed(self, rate):
        self.tts.set_rate(rate)
        self._speed_label.config(text=f"语速:{self.tts.rate}")
        self._status_var.set(f"语速 → {self.tts.rate}")

    def _adj_speed(self, delta):
        self.tts.adjust(delta)
        self._speed_label.config(text=f"语速:{self.tts.rate}")
        self._status_var.set(f"语速 → {self.tts.rate}")

    def _on_space(self):
        if self._reading:
            self.stop_reading()
        elif self._sel_text:
            self.read_selected()

    # ===================================================================
    # 文件打开 / 位置记忆
    # ===================================================================

    def open_pdf(self, filepath=None):
        if not filepath:
            filepath = filedialog.askopenfilename(
                title="选择 PDF 文件",
                filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        if not filepath or not os.path.isfile(filepath):
            return

        self._save_current_position()

        try:
            doc = fitz.open(filepath)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法读取 PDF:\n{e}")
            return

        self.doc = doc
        self.filepath = os.path.abspath(filepath)
        self.total_pages = len(doc)

        self._positions = load_positions()
        key = file_key(self.filepath)
        saved = self._positions.get(key, {})

        if saved.get('auto_fit', True):
            self._auto_fit = True
            cw = self.canvas.winfo_width()
            pw = doc[0].rect.width
            self.zoom = max(0.2, min(8.0,
                                     (cw - 20) / pw if pw > 0 and cw > 20 else 1.5))
        else:
            self._auto_fit = False
            self.zoom = saved.get('zoom', 1.5)

        self._page_lines.clear()
        self._clear_selection()
        self._calc_layout()
        self.canvas.configure(scrollregion=(0, 0, 1, self._total_height))

        # 离屏渲染目标页优先，再渲染其余可见页
        target_page = saved.get('page', 0)
        target_frac = saved.get('frac', 0.0)
        first, last = self._visible_page_range()

        # 目标页排在最前，确保它最先出现在画布上
        render_order = list(range(first, last + 1))
        if target_page in render_order:
            render_order.remove(target_page)
            render_order.insert(0, target_page)

        new_images = {}
        for p in render_order:
            photo = self._render_page_to_image(p)
            if photo:
                new_images[p] = photo

        self.canvas.delete('all')
        self._loaded.clear()
        self._page_images.clear()
        for p, photo in new_images.items():
            y0 = self._page_offsets[p]
            self.canvas.create_image(0, y0, anchor=tk.NW, image=photo,
                                     tags=(f'page_{p}',))
            self._page_images[p] = photo
            self._loaded.add(p)

        if target_page < self.total_pages and self._total_height > 0:
            y = (self._page_offsets[target_page]
                 + target_frac * self._page_heights[target_page])
            self.canvas.yview_moveto(y / self._total_height)

        self._zoom_label.config(text=f"{int(self.zoom * 100)}%")
        name = os.path.basename(self.filepath)
        self._status_var.set(
            f"已打开: {name}  ({self.total_pages} 页)"
            + (f" — 恢复到第 {target_page + 1} 页" if saved else ""))
        self.root.title(f"PDF 朗读器 — {name}")

    def _save_current_position(self):
        if not self.filepath or not self.doc:
            return
        top_y = self.canvas.canvasy(0)
        pg = self._page_at_y(top_y)
        if pg < 0:
            pg = 0
        off = self._page_offsets[pg] if pg < len(self._page_offsets) else 0
        h = self._page_heights[pg] if pg < len(self._page_heights) else 1
        frac = ((top_y - off) / h) if h > 0 else 0.0
        frac = max(0.0, min(1.0, frac))

        key = file_key(self.filepath)
        self._positions[key] = {
            'path': self.filepath,
            'page': pg,
            'frac': frac,
            'zoom': self.zoom,
            'auto_fit': self._auto_fit,
        }
        save_positions(self._positions)

    def _show_about(self):
        messagebox.showinfo(
            "关于 PDFReciter",
            "PDFReciter — 中文 PDF 朗读器\n\n"
            "鼠标拖拽框选 PDF 文本，自动语音朗读。\n\n"
            "License: CC BY-NC 4.0\n"
            "个人/学习/研究免费使用，商用需授权。\n\n"
            f"字体: {self._font}")

    def _on_close(self):
        self._save_current_position()
        self.stop_reading()
        self.root.quit()
