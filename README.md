# PDFReciter

中文 PDF 朗读器 —— 鼠标拖拽框选文本，自动语音朗读。

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey)

## 功能

- **拖拽框选朗读** — 鼠标拖拽自由框选 PDF 中的文本，松开后自动用中文语音朗读
- **连续自由滚动** — 所有页面纵向堆叠，滚轮或滚动条连续翻阅，无需逐页切换
- **窗口自适应** — 窗口大小变化时自动适配 PDF 宽度，也支持手动缩放（`Ctrl+=` / `Ctrl+-`）
- **阅读位置记忆** — 关闭时自动保存当前页码和滚动位置，再次打开同一 PDF 恢复到上次位置
- **语速档位** — 工具栏提供慢速(100) / 正常(160) / 快速(240) 三个档位，菜单中还可微调
- **中英混排纠正** — 选框内中英文数字混合内容按正确阅读顺序排列
- **免费开源字体** — 自动检测并使用 Noto Sans SC（思源黑体），未安装则自动下载

## 运行

### 方式一：Python 源码

```bash
pip install -r requirements.txt
python main.py                     # 启动后打开 PDF
python main.py "文档.pdf"           # 直接打开指定 PDF
```

### 方式二：打包好的 EXE

从 [Releases](https://github.com/lixiaowang/PDFReciter/releases) 下载 `PDFReciter.exe`，双击运行。无需安装 Python。

> EXE 约 62MB，首次启动可能需要几秒解压。

## 快捷键

| 按键 | 功能 |
|------|------|
| `Ctrl+O` | 打开 PDF |
| 鼠标拖拽 | 框选文本，松开自动朗读 |
| `Space` | 朗读上次框选内容 / 停止 |
| `Esc` | 取消框选 / 停止朗读 |
| `Ctrl+=` / `Ctrl+-` | 放大 / 缩小 |
| `Ctrl+W` | 适应窗口宽度 |
| `PageUp` / `PageDown` | 翻页 |
| `Home` / `End` | 跳到首页 / 末页 |
| `Ctrl+Q` | 退出 |

## 项目结构

```
PDFReader/
├── main.py          # 入口
├── app.py           # 主界面 / PDF 渲染 / 框选逻辑
├── tts.py           # TTS 引擎封装
├── utils.py         # 字体下载 / 位置持久化
└── requirements.txt
```

## 依赖

| 库 | 用途 |
|---|------|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF 渲染与文本提取 |
| [Pillow](https://python-pillow.org/) | 图像处理 |
| [pyttsx3](https://github.com/nateshmbhat/pyttsx3) | Windows SAPI5 中文语音合成 |

## 系统要求

- Windows 10 / 11
- 系统需安装中文语音包（通常预装 Microsoft Huihui）
- Python 3.8+（源码运行方式）

## 构建 EXE

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name PDFReciter main.py
# 输出在 dist/PDFReciter.exe
```


## License

[CC BY-NC 4.0](LICENSE) —— 个人、学习、研究可自由使用；商用需联系作者获取授权。
