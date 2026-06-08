"""
工具模块 — 免费字体下载 / 注册、阅读位置持久化。
"""

import os
import json
import hashlib
import urllib.request
from tkinter import font as tkfont

# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

_FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notosanssc/static/"
    "NotoSansSC-Regular.ttf"
)
_FONT_NAME = "Noto Sans SC"
FONT_SIZE = 20

_OPEN_SOURCE_FONTS = [
    'Noto Sans SC', 'Source Han Sans SC', '思源黑体',  # 思源黑体
    'Noto Sans CJK SC', 'WenQuanYi Micro Hei',
    'WenQuanYi Zen Hei', '文泉驿微米黑',     # 文泉驿微米黑
]
_FALLBACK_FONTS = ['Microsoft YaHei', 'SimHei', 'SimSun', 'Tahoma']


def _font_dir():
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.expanduser('~')
    d = os.path.join(base, '.pdf-reader-tts', 'fonts')
    os.makedirs(d, exist_ok=True)
    return d


def ensure_font(root):
    """确保有可用的免费中文字体，没有则自动下载 Noto Sans SC 并注册。"""
    available = set(tkfont.families(root=root))

    for name in _OPEN_SOURCE_FONTS:
        if name in available:
            return name

    # 加载已下载的字体文件
    fd = _font_dir()
    if os.path.isdir(fd):
        for fn in os.listdir(fd):
            if fn.lower().endswith(('.ttf', '.otf')):
                _register_font(os.path.join(fd, fn))

    available = set(tkfont.families(root=root))
    if _FONT_NAME in available:
        return _FONT_NAME

    # 下载
    font_path = os.path.join(fd, 'NotoSansSC-Regular.ttf')
    if not os.path.isfile(font_path):
        try:
            urllib.request.urlretrieve(_FONT_URL, font_path)
        except Exception:
            pass
    if os.path.isfile(font_path):
        _register_font(font_path)
        return _FONT_NAME

    # 回退
    for name in _FALLBACK_FONTS:
        if name in available:
            return name
    return 'TkDefaultFont'


def _register_font(path):
    try:
        import ctypes
        ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0)
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 阅读位置
# ---------------------------------------------------------------------------

def _pos_file():
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.expanduser('~')
    d = os.path.join(base, '.pdf-reader-tts')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'positions.json')


def load_positions():
    path = _pos_file()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_positions(data):
    try:
        with open(_pos_file(), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def file_key(filepath):
    return hashlib.md5(os.path.abspath(filepath).encode()).hexdigest()
