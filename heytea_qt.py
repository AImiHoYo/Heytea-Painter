"""
Heytea Painter - PySide6 主窗口（正式入口）
深色 Fusion + 蓝色强调，控件名与 heytea_modern.ModernDrawingApp 对齐。
"""

import sys
import os
import ctypes
from datetime import datetime

from modules.app_logger import error_log_path, log_error, log_info, run_log_path, setup_logging

setup_logging()

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from modules.platform_input import (
    permission_hint,
    stop_hotkey_listener,
    stop_one_click_listener,
    warmup_backends,
)
from modules.qt_draw_session import DrawSessionMixin
from modules.qt_preview import PreviewMixin
from modules.qt_widgets import (
    ButtonAdapter,
    CheckRow,
    SectionCard,
    SegmentedRow,
    make_slider,
)
from modules.settings_store import (
    ALL_EXTRACT_METHODS,
    APP_NAME,
    APP_ROOT,
    CALIB_TO_UI,
    LEGACY_PRESET_FILE,
    SETTINGS_FILE,
    SIMPLE_EXTRACT_METHODS,
    apply_beginner_preset,
    load_settings,
    save_settings,
    normalize_settings,
)

COLOR_MUTED = "#9aa0a6"
COLOR_INK = "#DCE4EE"
COLOR_STAGE = "#1a1a1a"
COLOR_ACCENT = "#1F6AA5"
COLOR_GO = "#2ecc71"
COLOR_GO_HOVER = "#27ae60"
COLOR_BG = QColor(36, 36, 36)  # gray14

if sys.platform == "darwin":
    FONT_FAMILY = "PingFang SC"
elif sys.platform == "win32":
    FONT_FAMILY = "Microsoft YaHei UI"
else:
    FONT_FAMILY = "Noto Sans CJK SC"

ICON_DIR = os.path.join(APP_ROOT, "icon")
ICON_PNG = os.path.join(ICON_DIR, "app_icon.png")
ICON_SRC_PNG = os.path.join(ICON_DIR, "icon.png")
ICON_ICO = os.path.join(ICON_DIR, "icon.ico")
ICON_ICNS = os.path.join(ICON_DIR, "icon.icns")


def _enable_windows_dpi():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            log_info("DPI 感知: Per-Monitor V1")
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                log_info("DPI 感知: System DPI")
            except Exception as exc:
                log_error("DPI 设置失败", exc)
    elif sys.platform == "darwin":
        log_info("macOS 使用系统原生缩放")


def apply_dark_fusion(app):
    """Fusion 深色调色板：gray14 底、#DCE4EE 字、#1F6AA5 高亮。"""
    app.setStyle("Fusion")
    palette = QPalette()
    text = QColor(COLOR_INK)
    highlight = QColor(COLOR_ACCENT)
    base = QColor(COLOR_STAGE)
    alt = QColor(45, 45, 45)
    button = QColor(50, 50, 50)
    muted = QColor(COLOR_MUTED)
    palette.setColor(QPalette.ColorRole.Window, COLOR_BG)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, alt)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, alt)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Light, QColor(70, 70, 70))
    palette.setColor(QPalette.ColorRole.Mid, QColor(55, 55, 55))
    palette.setColor(QPalette.ColorRole.Dark, QColor(28, 28, 28))
    app.setPalette(palette)
    app.setFont(QFont(FONT_FAMILY, 12))


def apply_app_identity(window):
    """设置窗口标题、任务栏/程序坞图标和系统显示名。"""
    window.setWindowTitle(APP_NAME)
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Heytea.Painter")
        except Exception:
            pass

    icon_path = None
    if os.path.isfile(ICON_PNG):
        icon_path = ICON_PNG
    elif os.path.isfile(ICON_ICO):
        icon_path = ICON_ICO
    elif os.path.isfile(ICON_SRC_PNG):
        icon_path = ICON_SRC_PNG
    if icon_path:
        icon = QIcon(icon_path)
        window.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    if sys.platform == "darwin":
        try:
            from AppKit import NSApp, NSApplication, NSImage
            from Foundation import NSBundle, NSProcessInfo

            info = NSBundle.mainBundle().infoDictionary()
            if info is not None:
                info["CFBundleName"] = APP_NAME
                info["CFBundleDisplayName"] = APP_NAME
            NSProcessInfo.processInfo().setProcessName_(APP_NAME)
            NSApplication.sharedApplication()
            png_path = ICON_PNG if os.path.isfile(ICON_PNG) else ICON_SRC_PNG
            icon_file = ICON_ICNS if os.path.isfile(ICON_ICNS) else png_path
            if os.path.isfile(icon_file):
                ns_image = NSImage.alloc().initWithContentsOfFile_(icon_file)
                if ns_image is not None:
                    NSApp.setApplicationIconImage_(ns_image)
        except Exception as exc:
            log_error("macOS 图标设置失败", exc)


class QtRootMixin:
    """Tk 风格窗口操作，供绘画会话 / 预览 mixin 调用。"""

    def after(self, ms, fn):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(fn)
        timer.start(int(ms))
        return timer

    def after_cancel(self, timer):
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass

    def iconify(self):
        self.showMinimized()

    def deiconify(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def destroy(self):
        self.close()


class HeyteaWindow(QMainWindow, QtRootMixin, PreviewMixin, DrawSessionMixin):
    _log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.root = self

        self.file_path = None
        self.contours = None
        self.img_w = 0
        self.img_h = 0
        self.preset_file = SETTINGS_FILE
        self.legacy_preset_file = LEGACY_PRESET_FILE

        self.preview_zoom = 1.0
        self.preview_original_img = None
        self.photo_image = None
        self.is_updating = False

        self._hint_win = None
        self._calib_overlay = None
        self._calib_canvas = None
        self._calib_label_id = None
        self._abort_win = None
        self._calib_points = []
        self._pending_draw = None
        self._pending_calib = None
        self._abort_btn = None
        self._hint_label = None
        self._announce_extract = False
        self._last_log_line = ""
        self._preview_timer = None
        self._quit_done = False
        self._in_close_event = False
        self.console_text = None

        self._log_signal.connect(self._write_log)
        self.setup_gui()
        warmup_backends()
        self.load_presets(silent=True)
        self.on_method_change()
        self.on_draw_method_change()
        self.apply_ui_mode()
        hint = permission_hint()
        if hint:
            self.log(hint)
        log_info(f"设置文件: {self.preset_file}")
        log_info(f"运行日志: {run_log_path()}")
        log_info(f"错误日志: {error_log_path()}")

    def setup_gui(self):
        """顶栏 + 左侧步骤卡片 + 右侧预览台。"""
        self.setWindowTitle(APP_NAME)
        self.resize(1600, 950)

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_topbar())

        main = QWidget()
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(14)
        root_layout.addWidget(main, 1)

        self.control_panel = QScrollArea()
        self.control_panel.setWidgetResizable(True)
        self.control_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.control_panel.setMinimumWidth(360)
        self.control_panel.setFixedWidth(380)
        self.control_panel.setFrameShape(QScrollArea.Shape.NoFrame)
        self._controls_host = QWidget()
        self._controls_layout = QVBoxLayout(self._controls_host)
        self._controls_layout.setContentsMargins(0, 0, 8, 0)
        self._controls_layout.setSpacing(0)
        self.control_panel.setWidget(self._controls_host)
        main_layout.addWidget(self.control_panel, 0)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        main_layout.addWidget(right, 1)

        preview_wrap = QWidget()
        preview_wrap.setObjectName("preview_wrap")
        preview_layout = QVBoxLayout(preview_wrap)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        title_col = QWidget()
        title_col_layout = QVBoxLayout(title_col)
        title_col_layout.setContentsMargins(0, 0, 0, 0)
        title_col_layout.setSpacing(0)
        preview_title = QLabel("预览")
        preview_title.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        preview_cap = QLabel("红线即落笔路径")
        preview_cap.setFont(QFont(FONT_FAMILY, 11))
        preview_cap.setStyleSheet(f"color: {COLOR_MUTED};")
        title_col_layout.addWidget(preview_title)
        title_col_layout.addWidget(preview_cap)
        header_layout.addWidget(title_col, 1)

        zoom_row = QWidget()
        zoom_layout = QHBoxLayout(zoom_row)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(6)
        for text, cmd in (("放大", self.zoom_in), ("缩小", self.zoom_out), ("复位", self.reset_zoom)):
            btn = QPushButton(text)
            btn.setFixedSize(56, 30)
            btn.setFont(QFont(FONT_FAMILY, 11))
            btn.clicked.connect(lambda _checked=False, c=cmd: c())
            zoom_layout.addWidget(btn)
        header_layout.addWidget(zoom_row)
        preview_layout.addWidget(header)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("preview_label")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setStyleSheet(f"background-color: {COLOR_STAGE};")
        preview_layout.addWidget(self.preview_label, 1)
        self.install_preview_wheel()
        right_layout.addWidget(preview_wrap, 1)

        console_wrap = QWidget()
        console_wrap.setFixedHeight(148)
        console_layout = QVBoxLayout(console_wrap)
        console_layout.setContentsMargins(16, 10, 12, 10)
        console_layout.setSpacing(4)
        log_title = QLabel("日志")
        log_title.setFont(QFont(FONT_FAMILY, 12, QFont.Weight.Bold))
        log_title.setStyleSheet(f"color: {COLOR_MUTED};")
        console_layout.addWidget(log_title)
        self.console_text = QPlainTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setMaximumBlockCount(220)
        self.console_text.setFont(QFont(FONT_FAMILY, 12))
        self.console_text.setStyleSheet(f"background-color: {COLOR_STAGE}; color: {COLOR_INK};")
        console_layout.addWidget(self.console_text, 1)
        right_layout.addWidget(console_wrap)

        self.create_controls()
        self._controls_layout.addStretch(1)

    def _build_topbar(self):
        bar = QWidget()
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 16, 8)
        layout.setSpacing(10)

        png_path = ICON_PNG if os.path.isfile(ICON_PNG) else ICON_SRC_PNG
        if os.path.isfile(png_path):
            try:
                pix = QPixmap(png_path)
                if not pix.isNull():
                    icon_lab = QLabel()
                    icon_lab.setPixmap(
                        pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                    )
                    icon_lab.setFixedSize(40, 40)
                    layout.addWidget(icon_lab)
            except Exception:
                pass

        titles = QWidget()
        titles_layout = QVBoxLayout(titles)
        titles_layout.setContentsMargins(0, 0, 0, 0)
        titles_layout.setSpacing(0)
        name_lab = QLabel(APP_NAME)
        name_lab.setFont(QFont(FONT_FAMILY, 18, QFont.Weight.Bold))
        sub_lab = QLabel("线稿提取  ·  模拟落笔")
        sub_lab.setFont(QFont(FONT_FAMILY, 11))
        sub_lab.setStyleSheet(f"color: {COLOR_MUTED};")
        titles_layout.addWidget(name_lab)
        titles_layout.addWidget(sub_lab)
        layout.addWidget(titles)
        layout.addStretch(1)

        self.ui_mode = SegmentedRow(bar, values=["简单", "高级"], default="简单")
        self.ui_mode.setFixedHeight(32)
        self.ui_mode.setFixedWidth(140)
        self.ui_mode.configure(command=self.on_ui_mode_change)
        layout.addWidget(self.ui_mode)
        for text, cmd in (("保存设置", self.save_presets), ("读取设置", self.load_presets), ("一键推荐", self.apply_recommended), ("重置", self.reset_params)):
            btn = QPushButton(text)
            btn.setFixedSize(84, 32)
            btn.setFont(QFont(FONT_FAMILY, 12))
            btn.clicked.connect(lambda _checked=False, c=cmd: c())
            layout.addWidget(btn)
        return bar

    def _section(self, title, step=None, caption=None):
        card = SectionCard(self._controls_host, title, step=step, caption=caption)
        self._place(self._controls_host, card)
        body = card.body()
        if isinstance(body, QWidget) and body.layout() is None:
            lay = QVBoxLayout(body)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
        return body

    def _place(self, parent, widget):
        if not isinstance(widget, QWidget):
            return widget
        layout = parent.layout() if isinstance(parent, QWidget) else parent
        if layout is None:
            return widget
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is not None and item.widget() is widget:
                return widget
        layout.addWidget(widget)
        return widget

    def _slider(self, parent, label, from_, to, default, resolution=None, tooltip=None, preview=True):
        slider = make_slider(
            parent, label, from_, to, default, resolution, tooltip,
            on_change=self.update_preview_throttled if preview else None,
        )
        self._place(parent, slider)
        return slider

    def _check(self, parent, text, command=None):
        row = CheckRow(parent, text, command=command) if command is not None else CheckRow(parent, text)
        self._place(parent, row if isinstance(row, QWidget) else None)
        return row

    def _segmented(self, parent, values, default=None):
        row = SegmentedRow(parent, values=values)
        if default is not None:
            row.set(default)
        self._place(parent, row if isinstance(row, QWidget) else None)
        return row

    def _label(self, parent, text, bold=False, muted=False, wrap=False):
        lab = QLabel(text)
        lab.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        if muted:
            lab.setStyleSheet(f"color: {COLOR_MUTED};")
        if wrap:
            lab.setWordWrap(True)
        self._place(parent, lab)
        return lab

    def log(self, message):
        """用户可见日志：右侧控制台 + 终端一行。诊断请用 log_info。"""
        text = str(message).strip()
        if not text or text == self._last_log_line:
            return
        self._last_log_line = text
        timestamp = datetime.now().strftime("%H:%M")
        line = f"[{timestamp}] {text}"
        try:
            self._log_signal.emit(line)
        except Exception:
            QTimer.singleShot(0, lambda: self._write_log(line))
        print(text)

    def _write_log(self, line):
        try:
            box = self.console_text
            if box is None:
                return
            box.appendPlainText(line)
            box.ensureCursorVisible()
        except Exception:
            pass

    def create_controls(self):
        """创建控制面板。控件名与回调保持不变。"""
        file_frame = self._section("打开图片")
        pick = QPushButton("选择图片")
        pick.setMinimumHeight(40)
        pick.setFont(QFont(FONT_FAMILY, 13, QFont.Weight.Bold))
        pick.clicked.connect(lambda: self.load_image())
        self._place(file_frame, pick)
        self.simple_guide = self._label(
            file_frame,
            "新手建议：先点顶栏「一键推荐」，再用 Anime2Sketch + 仿真人开画",
            muted=False, wrap=True,
        )
        self.simple_guide.setStyleSheet(f"color: {COLOR_ACCENT};")

        extract_frame = self._section("提取线稿", step="1", caption="先出红线，再决定怎么画")
        self.extraction_method = self._segmented(
            extract_frame,
            ["Pencil Sketch", "Canny", "Anime2Sketch", "LineartAnime"],
            "Pencil Sketch",
        )
        self.force_reinfer_btn = ButtonAdapter(
            "强制重推理（清缓存）", command=lambda *a: self.force_reinfer_preview())
        self.force_reinfer_btn.setFont(QFont(FONT_FAMILY, 11))
        self.force_reinfer_btn.setToolTip("忽略边图缓存，重新跑一次网络")
        self._place(extract_frame, self.force_reinfer_btn)

        self.params_container = QWidget()
        params_layout = QVBoxLayout(self.params_container)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(0)
        self._place(extract_frame, self.params_container)

        self.pencil_params = QWidget()
        QVBoxLayout(self.pencil_params).setContentsMargins(0, 0, 0, 0)
        self.sigma_s = self._slider(self.pencil_params, "平滑度", 1, 200, 60, tooltip="控制线条平滑程度，值越大越平滑")
        self.sigma_r = self._slider(self.pencil_params, "细节保留", 0.01, 1.0, 0.4, 0.01, tooltip="保留图像细节的强度")
        self.shade_factor = self._slider(self.pencil_params, "阴影强度", 0.0, 1.0, 0.05, 0.01, tooltip="阴影的深度和强度")
        params_layout.addWidget(self.pencil_params)

        self.canny_params = QWidget()
        QVBoxLayout(self.canny_params).setContentsMargins(0, 0, 0, 0)
        self.canny_blur = self._slider(self.canny_params, "高斯模糊", 1, 20, 3, 1, tooltip="预处理模糊程度，减少噪点")
        self.canny_low = self._slider(self.canny_params, "低阈值", 1, 500, 50, 1, tooltip="边缘检测下限，低于此值忽略")
        self.canny_high = self._slider(self.canny_params, "高阈值", 1, 1000, 150, 1, tooltip="边缘检测上限，高于此值保留")
        params_layout.addWidget(self.canny_params)

        self.anime_params = QWidget()
        QVBoxLayout(self.anime_params).setContentsMargins(0, 0, 0, 0)
        self.anime_threshold = self._slider(self.anime_params, "二值化阈值", 50, 200, 127, 1, tooltip="黑白分界点，控制线条粗细")
        self.anime_morph_size = self._slider(self.anime_params, "形态学核大小", 1, 5, 2, 1, tooltip="线条处理核大小，影响线条连续性")
        self.anime_morph_iter = self._slider(self.anime_params, "形态学迭代", 1, 3, 1, 1, tooltip="形态学处理次数")
        self.anime_min_area = self._slider(self.anime_params, "最小轮廓面积", 5, 100, 10, 1, tooltip="过滤小轮廓，减少噪点")
        self.anime_expert = QWidget()
        QVBoxLayout(self.anime_expert).setContentsMargins(0, 0, 0, 0)
        self.anime_params.layout().addWidget(self.anime_expert)
        self._label(self.anime_expert, "高级参数", bold=True)
        self.anime_pre_blur = self._slider(self.anime_expert, "预处理模糊", 0, 9, 0, 1, tooltip="AI处理前的模糊强度")
        self.anime_edge_enhance = self._slider(self.anime_expert, "边缘增强", 0, 3.0, 0, 0.1, tooltip="增强边缘锐度")
        self.anime_sigmoid = self._slider(self.anime_expert, "模型敏感度", 0.3, 0.9, 0.5, 0.05, tooltip="AI模型的灵敏度")
        self.anime_invert = self._check(self.anime_expert, "反转提取", command=self.update_preview)
        self.anime_adaptive = self._check(self.anime_expert, "自适应二值化", command=self.update_preview)
        self._label(self.anime_params, "轮廓模式:")
        self.anime_mode = self._segmented(self.anime_params, ["外部轮廓", "所有轮廓", "中心线"], "外部轮廓")
        self.anime_mode.configure(command=lambda v: self.update_preview())
        params_layout.addWidget(self.anime_params)

        self.lineart_params = QWidget()
        QVBoxLayout(self.lineart_params).setContentsMargins(0, 0, 0, 0)
        self.lineart_detect = self._slider(
            self.lineart_params, "检测分辨率", 256, 1024, 512, 64,
            tooltip="官方 detect_resolution，默认 512")
        self.lineart_min_area = self._slider(
            self.lineart_params, "最小路径长度", 5, 100, 10, 1,
            tooltip="中心线按路径长度过滤碎线；外框模式仍按面积过滤")
        self.lineart_invert = self._check(self.lineart_params, "官方反色 (255−x)", command=self.update_preview)
        self.lineart_invert.select()
        self._label(self.lineart_params, "轮廓模式:")
        self.lineart_mode = self._segmented(self.lineart_params, ["外部轮廓", "所有轮廓", "中心线"], "中心线")
        self.lineart_mode.configure(command=lambda v: self.update_preview())
        params_layout.addWidget(self.lineart_params)

        self.extraction_method.configure(command=self.on_method_change)

        optimize_frame = self._section("路径优化", step="2", caption="红线阶段处理，影响预览和落笔")
        self.simplify_eps = self._slider(optimize_frame, "线条简化度 [全局]", 0.1, 5.0, 1.0, 0.1, tooltip="简化线条路径，减少点数")
        self.preview_thick = self._slider(optimize_frame, "预览线条粗细 [预览]", 1, 20, 1, 1, tooltip="预览图中线条的粗细")
        self.taper_paths = self._check(optimize_frame, "起收笔路径（红线重叠）[全局]", command=self.update_preview)
        self.taper_paths.select()
        self.show_chunk_grid = self._check(optimize_frame, "显示分块网格 [预览]", command=self.update_preview)
        self.optimize_expert = QWidget()
        QVBoxLayout(self.optimize_expert).setContentsMargins(0, 0, 0, 0)
        self._place(optimize_frame, self.optimize_expert)
        self.spline_smooth = self._slider(self.optimize_expert, "路径平滑度 [全局]", 0, 5000, 0, 1, tooltip="使用B样条平滑路径")
        self.jitter_correct = self._slider(self.optimize_expert, "抖动修正强度 [全局]", 0, 10, 0, 1, tooltip="修正线条抖动，使线条更平滑")
        self.thin_contours = self._check(self.optimize_expert, "边缘细化（双线变单线）[全局]", command=self.update_preview)
        self.taper_layers = self._slider(
            self.optimize_expert, "重叠层数 [全局]", 1, 4, 3, 1,
            tooltip="粗处最多叠几条红线；1=不重叠")
        self.taper_ratio = self._slider(
            self.optimize_expert, "起收笔比例 [全局]", 0.10, 0.40, 0.18, 0.02,
            tooltip="两端加粗（顿笔）占整段长度的比例，效果为粗-细-粗")
        self.taper_spacing = self._slider(
            self.optimize_expert, "层间距 [全局]", 0.6, 2.0, 1.0, 0.1,
            tooltip="重叠红线之间的像素间距")
        self.skip_points = self._slider(self.optimize_expert, "跳点加速 [全局]", 1, 5, 1, 1, tooltip="跳过部分点来加快绘画速度")
        self.bbox_cell_size = self._slider(
            self.optimize_expert, "分块边长 [全局]", 0, 400, 0, 10,
            tooltip="路径包围盒分块边长（像素）。0=自动，越大块越大、跨区跳跃越少",
            preview=False,
        )

        draw_frame = self._section("绘画方式", step="3", caption="只决定运笔节奏，粗细看红线")
        self.draw_method = self._segmented(draw_frame, ["短行程", "智能拖动", "仿真人", "压感"], "短行程")

        self.draw_params_container = QWidget()
        draw_params_layout = QVBoxLayout(self.draw_params_container)
        draw_params_layout.setContentsMargins(0, 0, 0, 0)
        draw_params_layout.setSpacing(0)
        self._place(draw_frame, self.draw_params_container)

        self.m1_params = QWidget()
        QVBoxLayout(self.m1_params).setContentsMargins(0, 0, 0, 0)
        self.stroke_len = self._slider(self.m1_params, "笔画长度", 5, 100, 15, 5, tooltip="每次绘制的点数（短行程模式）", preview=False)
        draw_params_layout.addWidget(self.m1_params)

        self.m2_params = QWidget()
        QVBoxLayout(self.m2_params).setContentsMargins(0, 0, 0, 0)
        self.min_drag = self._slider(self.m2_params, "最小拖动距离", 1, 20, 5, 1, tooltip="触发移动的最小距离（智能拖动）", preview=False)
        draw_params_layout.addWidget(self.m2_params)

        self.m3_params = QWidget()
        QVBoxLayout(self.m3_params).setContentsMargins(0, 0, 0, 0)
        self.hand_shake = self._slider(self.m3_params, "手部抖动", 0, 5, 1, 1, tooltip="模拟手部抖动（仿真人）", preview=False)
        self.think_pause = self._slider(self.m3_params, "思考停顿倍率", 1, 10, 3, 1, tooltip="转角处的思考停顿（仿真人）", preview=False)
        self.corner_sharp = self._slider(self.m3_params, "转角锐利度", 0, 10, 5, 1, tooltip="转角锐利度：0=圆润平滑，10=极度锐利", preview=False)
        draw_params_layout.addWidget(self.m3_params)

        self.m4_params = QWidget()
        m4_layout = QVBoxLayout(self.m4_params)
        m4_layout.setContentsMargins(0, 0, 0, 0)
        m4_help = QLabel("粗细已画在红线里。请先开「起收笔路径」，绘画只跟随红线。")
        m4_help.setFont(QFont(FONT_FAMILY, 11))
        m4_help.setWordWrap(True)
        m4_layout.addWidget(m4_help)
        draw_params_layout.addWidget(self.m4_params)

        self.draw_method.configure(command=self.on_draw_method_change)

        self.draw_delay = self._slider(draw_frame, "绘画延迟(ms) [全局]", 1, 100, 5, 1, tooltip="每个运笔点之间的延迟", preview=False)
        self.lift_pause = self._slider(
            draw_frame, "换线停顿(秒) [全局]", 0.05, 10.0, 5.0, 0.05,
            tooltip="换线后的额外等待。仿真人建议 ≥5 秒，防止喜茶小程序误清屏；抬笔至少约 0.12 秒以防连笔",
            preview=False)
        self.lift_pause_tip = self._label(
            draw_frame,
            "提示：仿真人模式建议换线停顿 ≥ 5 秒，避免小程序清屏",
            muted=True, wrap=True,
        )

        speed_frame = self._section("运笔速度")
        self.speed_expert = QWidget()
        QVBoxLayout(self.speed_expert).setContentsMargins(0, 0, 0, 0)
        self._place(speed_frame, self.speed_expert)
        self.speed_mult = self._slider(
            self.speed_expert, "运笔速度 [全局]", 0.1, 5.0, 1.0, 0.1,
            tooltip="只加快运笔点间距，不影响换线停顿",
            preview=False)

        button_frame = self._section("落笔", step="4", caption="先定画布，再开始")
        self.canvas_calib = self._segmented(button_frame, ["手动定画布", "自动识别画布"], "手动定画布")

        self.start_btn = ButtonAdapter("开始绘画")
        self.start_btn.setMinimumHeight(46)
        self.start_btn.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        self.start_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLOR_GO}; color: #ffffff; border: none; "
            f"border-radius: 8px; min-height: 46px; }}"
            f"QPushButton:hover {{ background-color: {COLOR_GO_HOVER}; }}"
            f"QPushButton:disabled {{ background-color: #3d6b4f; color: #b0b0b0; }}"
        )
        self.start_btn.configure(state="disabled", command=lambda *a: self.start_drawing())
        self._place(button_frame, self.start_btn)

    def on_method_change(self, value=None):
        """切换提取方法：只显示当前方法的参数。"""
        method = self.extraction_method.get()
        self.pencil_params.setVisible(method == "Pencil Sketch")
        self.canny_params.setVisible(method == "Canny")
        self.anime_params.setVisible(method == "Anime2Sketch")
        self.lineart_params.setVisible(method == "LineartAnime")
        if hasattr(self, "force_reinfer_btn"):
            # AI 方法才有边图缓存，强制重推理按钮只在这两个方法显示
            self.force_reinfer_btn.setVisible(method in ("Anime2Sketch", "LineartAnime"))
        if value is not None:
            self._announce_extract = True
            self.update_preview()

    def on_draw_method_change(self, value=None):
        """切换绘画方法：只显示当前方法的参数。全局延迟/换线/运笔速度始终可见。"""
        method = self.draw_method.get()
        show = True
        if hasattr(self, "_ui_mode_key") and self._ui_mode_key() == "simple":
            show = False
        self.m1_params.setVisible(show and method == "短行程")
        self.m2_params.setVisible(show and method == "智能拖动")
        self.m3_params.setVisible(show and method == "仿真人")
        self.m4_params.setVisible(show and method == "压感")

    def load_image(self):
        """加载图片"""
        default_dir = os.path.join(os.path.dirname(__file__), "images")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片（支持任意位置）",
            default_dir,
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp);;"
            "JPEG (*.jpg *.jpeg);;PNG (*.png);;所有文件 (*.*)",
        )
        if file_path:
            self.file_path = file_path
            name = os.path.basename(file_path)
            size_text = ""
            try:
                import cv2
                import numpy as np

                with open(file_path, "rb") as f:
                    img_array = np.frombuffer(f.read(), np.uint8)
                test_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if test_img is not None:
                    h, w = test_img.shape[:2]
                    size_text = f"（{w}×{h}）"
                    if max(h, w) > 4096:
                        self.log(f"已加载 {name}{size_text}，已缩小超大图")
                    elif max(h, w) < 256:
                        self.log(f"已加载 {name}{size_text}，已放大过小图")
                    else:
                        self.log(f"已加载 {name}{size_text}")
                else:
                    self.log(f"已加载 {name}")
            except Exception as exc:
                self.log(f"已加载 {name}")
                log_error("读取图片信息失败", exc)

            self._announce_extract = True
            self.update_preview()
            self.start_btn.configure(state="normal")

    def get_all_values(self):
        """获取所有参数值（短键）。"""
        return {
            "extraction_method": self.extraction_method.get(),
            "sigma_s": self.sigma_s.get(),
            "sigma_r": self.sigma_r.get(),
            "shade_factor": self.shade_factor.get(),
            "canny_blur": self.canny_blur.get(),
            "canny_low": self.canny_low.get(),
            "canny_high": self.canny_high.get(),
            "simplify_epsilon": self.simplify_eps.get(),
            "preview_thickness": self.preview_thick.get(),
            "spline_smoothness": self.spline_smooth.get(),
            "jitter_correction": self.jitter_correct.get(),
            "stroke_len": self.stroke_len.get(),
            "min_drag_dist": self.min_drag.get(),
            "draw_delay": self.draw_delay.get(),
            "drawing_method": self.draw_method.get(),
            "anime_threshold": self.anime_threshold.get(),
            "anime_morph_size": self.anime_morph_size.get(),
            "anime_morph_iter": self.anime_morph_iter.get(),
            "anime_min_area": self.anime_min_area.get(),
            "anime_contour_mode": self.anime_mode.get(),
            "anime_pre_blur": self.anime_pre_blur.get(),
            "anime_edge_enhance": self.anime_edge_enhance.get(),
            "anime_sigmoid_threshold": self.anime_sigmoid.get(),
            "anime_invert": self.anime_invert.get() == 1,
            "anime_adaptive": self.anime_adaptive.get() == 1,
            "thin_contours": self.thin_contours.get() == 1,
            "taper_paths": self.taper_paths.get() == 1,
            "taper_layers": self.taper_layers.get(),
            "taper_ratio": self.taper_ratio.get(),
            "taper_spacing": self.taper_spacing.get(),
            "skip_points": self.skip_points.get(),
            "hand_shake": self.hand_shake.get(),
            "think_pause": self.think_pause.get(),
            "corner_sharpness": self.corner_sharp.get(),
            "lift_pause": self.lift_pause.get(),
            "speed_multiplier": self.speed_mult.get(),
            "canvas_calib": self.canvas_calib.get(),
            "lineart_detect_resolution": self.lineart_detect.get(),
            "lineart_min_area": self.lineart_min_area.get(),
            "lineart_contour_mode": self.lineart_mode.get(),
            "lineart_invert": self.lineart_invert.get() == 1,
            "ui_mode": self._ui_mode_key(),
            "bbox_cell_size": self.bbox_cell_size.get() if hasattr(self, "bbox_cell_size") else 0.0,
            "show_chunk_grid": self.show_chunk_grid.get() == 1 if hasattr(self, "show_chunk_grid") else False,
        }

    def set_all_values(self, values):
        """设置所有参数值（接受旧键）。"""
        values = normalize_settings(values)

        self.extraction_method.set(values["extraction_method"])
        self.sigma_s.set(values["sigma_s"])
        self.sigma_r.set(values["sigma_r"])
        self.shade_factor.set(values["shade_factor"])
        self.canny_blur.set(values["canny_blur"])
        self.canny_low.set(values["canny_low"])
        self.canny_high.set(values["canny_high"])
        self.simplify_eps.set(values["simplify_epsilon"])
        self.preview_thick.set(values["preview_thickness"])
        self.spline_smooth.set(values["spline_smoothness"])
        self.jitter_correct.set(values["jitter_correction"])
        self.stroke_len.set(values["stroke_len"])
        self.min_drag.set(values["min_drag_dist"])
        self.draw_delay.set(values["draw_delay"])
        self.draw_method.set(values["drawing_method"])
        self.anime_threshold.set(values["anime_threshold"])
        self.anime_morph_size.set(values["anime_morph_size"])
        self.anime_morph_iter.set(values["anime_morph_iter"])
        self.anime_min_area.set(values["anime_min_area"])
        self.anime_mode.set(values["anime_contour_mode"])
        self.anime_pre_blur.set(values["anime_pre_blur"])
        self.anime_edge_enhance.set(values["anime_edge_enhance"])
        self.anime_sigmoid.set(values["anime_sigmoid_threshold"])

        if values.get("anime_invert", False):
            self.anime_invert.select()
        else:
            self.anime_invert.deselect()

        if values.get("anime_adaptive", False):
            self.anime_adaptive.select()
        else:
            self.anime_adaptive.deselect()

        if values.get("thin_contours", False):
            self.thin_contours.select()
        else:
            self.thin_contours.deselect()

        if values.get("taper_paths", True):
            self.taper_paths.select()
        else:
            self.taper_paths.deselect()
        self.taper_layers.set(values.get("taper_layers", 3))
        self.taper_ratio.set(values.get("taper_ratio", values.get("pressure_taper", 0.18)))
        self.taper_spacing.set(values.get("taper_spacing", 1.0))

        self.skip_points.set(values["skip_points"])
        self.hand_shake.set(values["hand_shake"])
        self.think_pause.set(values["think_pause"])
        self.corner_sharp.set(values["corner_sharpness"])
        self.lift_pause.set(values["lift_pause"])
        self.speed_mult.set(values["speed_multiplier"])
        self.canvas_calib.set(CALIB_TO_UI.get(values.get("canvas_calib", "manual"), "手动定画布"))
        self.lineart_detect.set(values.get("lineart_detect_resolution", 512))
        self.lineart_min_area.set(values.get("lineart_min_area", 10))
        self.lineart_mode.set(values.get("lineart_contour_mode", values.get("anime_contour_mode", "中心线")))
        if values.get("lineart_invert", True):
            self.lineart_invert.select()
        else:
            self.lineart_invert.deselect()

        mode = values.get("ui_mode", "simple")
        if hasattr(self, "ui_mode"):
            self.ui_mode.set("高级" if mode == "advanced" else "简单")
        if hasattr(self, "bbox_cell_size"):
            self.bbox_cell_size.set(values.get("bbox_cell_size", 0.0))
        if hasattr(self, "show_chunk_grid"):
            if values.get("show_chunk_grid", False):
                self.show_chunk_grid.select()
            else:
                self.show_chunk_grid.deselect()

    def save_presets(self, silent=False):
        """保存当前设置到 config/settings.json（不写 heytea_presets.json）"""
        try:
            save_settings(self.get_all_values())
            if not silent:
                self.log("设置已保存")
        except Exception as e:
            if not silent:
                self.log("设置保存失败")
            log_error("保存设置失败", e)

    def load_presets(self, silent=False):
        """启动时读取 config/settings.json；没有则回退旧的 heytea_presets.json"""
        values, path = load_settings()
        if values is None:
            if path is None and not silent:
                self.log("还没有保存过设置")
            return

        try:
            self.set_all_values(values)
            self.on_method_change()
            self.on_draw_method_change()
            self.apply_ui_mode()
            if not silent:
                self.log("设置已加载")
            elif path == LEGACY_PRESET_FILE:
                self.log("已导入旧版设置")
        except Exception as e:
            if not silent:
                self.log("设置加载失败")
            log_error("加载设置失败", e)

    def _on_app_quit(self):
        """关闭窗口或 Cmd+Q 时写一次设置。"""
        if self._quit_done:
            return
        self._quit_done = True
        try:
            self.save_presets(silent=True)
        except Exception as exc:
            log_error("关闭时保存设置失败", exc)
        try:
            stop_hotkey_listener()
            stop_one_click_listener()
        except Exception:
            pass
        self._close_calibrate_windows()
        if not self._in_close_event:
            self.root.destroy()

    def closeEvent(self, event):
        self._in_close_event = True
        self._on_app_quit()
        event.accept()

    def _ui_mode_key(self):
        label = self.ui_mode.get() if hasattr(self, "ui_mode") else "简单"
        return "advanced" if label in ("高级", "advanced", "expert") else "simple"

    def on_ui_mode_change(self, value=None):
        self.apply_ui_mode()
        if self._ui_mode_key() == "simple":
            try:
                if float(self.lift_pause.get()) < 5.0:
                    self.lift_pause.set(5.0)
            except Exception:
                pass
            self.log("已切换到简单模式：专家参数已折叠")
        else:
            self.log("已切换到高级模式：显示全部参数")

    def apply_ui_mode(self):
        """简单模式折叠专家参数；高级模式全部显示。"""
        simple = self._ui_mode_key() == "simple"
        if hasattr(self, "simple_guide"):
            self.simple_guide.setVisible(simple)
        if hasattr(self, "anime_expert"):
            self.anime_expert.setVisible(not simple)
        if hasattr(self, "optimize_expert"):
            self.optimize_expert.setVisible(not simple)
        if hasattr(self, "speed_expert"):
            self.speed_expert.setVisible(not simple)
        if hasattr(self, "extraction_method"):
            self._apply_extract_values(simple)
        self.on_draw_method_change()

    def _apply_extract_values(self, simple):
        """简单模式只保留 AI 提取方法；Pencil/Canny 收进高级模式。"""
        target = SIMPLE_EXTRACT_METHODS if simple else ALL_EXTRACT_METHODS
        if self.extraction_method.values() != target:
            changed = self.extraction_method.set_values(target, default=SIMPLE_EXTRACT_METHODS[0])
            if changed:
                self.on_method_change()
                self.log(
                    f"简单模式隐藏 Pencil/Canny：提取方法已切为 {self.extraction_method.get()}"
                    "（也可点顶栏「一键推荐」）"
                )

    def force_reinfer_preview(self):
        """强制重推理：清空边图缓存并立即重新提取。"""
        self.clear_edge_cache()
        method = self.extraction_method.get()
        self.log(f"已清空推理缓存：{method} 将重新跑模型")
        if self.file_path:
            self._announce_extract = True
            self.update_preview()

    def apply_recommended(self):
        """小白一键推荐：Anime2Sketch + 仿真人 + 安全换线。"""
        self.set_all_values(apply_beginner_preset({}))
        self.on_method_change()
        self.on_draw_method_change()
        self.apply_ui_mode()
        self.log("已套用小白推荐：Anime2Sketch + 仿真人，换线停顿 5 秒")
        if self.file_path:
            self.update_preview()

    def reset_params(self):
        """重置参数"""
        self.log("参数已重置")
        self.set_all_values({})
        self.on_method_change()
        self.on_draw_method_change()
        self.apply_ui_mode()
        if self.file_path:
            self.update_preview()


def main():
    _enable_windows_dpi()
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Heytea.Painter")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_fusion(app)

    window = HeyteaWindow()
    apply_app_identity(window)
    window.resize(1600, 950)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
