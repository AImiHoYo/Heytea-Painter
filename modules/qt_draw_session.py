"""
绘画会话：标定覆盖层 → 聚焦点击 → 延迟 → 后台线程落笔。
中止条保持顶栏居中约 280×52；不调用 activateWindow。
"""

import sys
import threading

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

try:
    from PySide6.QtGui import QShortcut
except ImportError:
    from PySide6.QtWidgets import QShortcut

from modules.app_logger import log_error, log_info
from modules.drawing_engine import (
    compute_canvas_calibration,
    start_drawing_method_1,
    start_drawing_method_2,
    start_drawing_method_3,
    start_drawing_method_4,
)
from modules.platform_input import (
    focus_terminal,
    request_abort,
    start_hotkey_listener,
    start_one_click_listener,
    stop_one_click_listener,
)
from modules.canvas_detect import detect_wechat_canvas
from modules.settings_store import APP_NAME, CALIB_ALIASES

if sys.platform == "darwin":
    FONT_FAMILY = "PingFang SC"
elif sys.platform == "win32":
    FONT_FAMILY = "Microsoft YaHei UI"
else:
    FONT_FAMILY = "Noto Sans CJK SC"


def _qt_flag(enum_ns, name):
    return getattr(enum_ns, name, None)


def _virtual_desktop_geometry():
    """Cover the virtual desktop (all screens) when Qt reports one."""
    screen = QGuiApplication.primaryScreen()
    screens = QGuiApplication.screens()
    if screen is not None:
        geo = screen.virtualGeometry()
        if geo.isValid() and geo.width() > 0 and geo.height() > 0:
            return QRect(geo)
        geo = screen.geometry()
        if geo.isValid() and geo.width() > 0 and geo.height() > 0:
            return QRect(geo)
    if screens:
        geo = screens[0].virtualGeometry()
        if geo.isValid() and geo.width() > 0 and geo.height() > 0:
            return QRect(geo)
    return QRect(0, 0, 1920, 1080)


def _tool_window_flags(no_focus=False):
    flags = (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    if no_focus:
        extra = _qt_flag(Qt.WindowType, "WindowDoesNotAcceptFocus")
        if extra is not None:
            flags |= extra
    return flags


def _mark_tool_window(widget, opacity=None, no_activate=False):
    widget.setWindowFlags(_tool_window_flags(no_focus=no_activate))
    if opacity is not None:
        widget.setWindowOpacity(opacity)
    show_without = _qt_flag(Qt.WidgetAttribute, "WA_ShowWithoutActivating")
    if no_activate and show_without is not None:
        widget.setAttribute(show_without, True)
    mac_tool = _qt_flag(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow")
    if mac_tool is not None:
        widget.setAttribute(mac_tool, True)


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        try:
            return event.globalPosition().toPoint()
        except Exception:
            pass
    if hasattr(event, "globalPos"):
        try:
            return event.globalPos()
        except Exception:
            pass
    return QCursor.pos()


def _safe_close(win):
    if win is None:
        return
    try:
        win.hide()
        win.close()
        win.deleteLater()
    except Exception:
        pass


class _CalibOverlay(QWidget):
    """Fullscreen semi-transparent overlay for auto-confirm or manual corner clicks."""

    def __init__(self, session, mode="manual"):
        super().__init__(None)
        self._session = session
        self._mode = mode
        self._first_point = None
        self._confirm_rect = None
        self._shortcuts = []
        _mark_tool_window(self, opacity=0.28, no_activate=False)
        self.setStyleSheet("background-color: #111111;")
        self.setAutoFillBackground(True)
        if mode == "manual":
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(_virtual_desktop_geometry())
        if mode == "confirm":
            self._add_shortcut(Qt.Key.Key_Return, session._accept_auto_canvas)
            self._add_shortcut(Qt.Key.Key_Enter, session._accept_auto_canvas)
            self._add_shortcut(Qt.Key.Key_Escape, session._reject_auto_canvas)
            self._add_shortcut(Qt.Key.Key_Q, session._reject_auto_canvas)
        else:
            self._add_shortcut(Qt.Key.Key_Escape, session._cancel_calibration)
            self._add_shortcut(Qt.Key.Key_Q, session._cancel_calibration)

    def _add_shortcut(self, key, slot):
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(slot)
        self._shortcuts.append(shortcut)

    def set_first_point(self, point):
        self._first_point = (int(point[0]), int(point[1]))
        self.update()

    def set_confirm_rect(self, top_left, bottom_right):
        self._confirm_rect = (
            (int(top_left[0]), int(top_left[1])),
            (int(bottom_right[0]), int(bottom_right[1])),
        )
        self.update()

    def mousePressEvent(self, event):
        if self._mode != "manual":
            super().mousePressEvent(event)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = _event_global_pos(event)
        if pos is None:
            pos = QCursor.pos()
        self._session._on_calib_point(int(pos.x()), int(pos.y()))
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        text = (event.text() or "").lower()
        is_escape = key in (Qt.Key.Key_Escape, Qt.Key.Key_Q) or text == "q"
        if self._mode == "confirm":
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._session._accept_auto_canvas()
                event.accept()
                return
            if is_escape:
                self._session._reject_auto_canvas()
                event.accept()
                return
        elif is_escape:
            self._session._cancel_calibration()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#111111"))
        if self._confirm_rect is not None:
            (x0, y0), (x1, y1) = self._confirm_rect
            p0 = self.mapFromGlobal(QPoint(x0, y0))
            p1 = self.mapFromGlobal(QPoint(x1, y1))
            painter.setPen(QPen(QColor("#3ddc84"), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(p0, p1).normalized())
        if self._first_point is not None:
            x0, y0 = self._first_point
            center = self.mapFromGlobal(QPoint(x0, y0))
            painter.setPen(QPen(QColor("#ff5555"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, 7, 7)
        painter.end()


class _HintBanner(QWidget):
    """Opaque top-center hint; stays readable over the dim overlay."""

    def __init__(self, text):
        super().__init__(None)
        _mark_tool_window(self, opacity=0.94, no_activate=True)
        self.setFixedSize(360, 52)
        self._label = QLabel(text, self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont(FONT_FAMILY, 15)
        font.setBold(True)
        self._label.setFont(font)
        self._label.setStyleSheet(
            "QLabel { background-color: #1c1c1c; color: white; padding: 12px 18px; }"
        )
        self.setStyleSheet("background-color: #1c1c1c;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def set_text(self, text):
        self._label.setText(text)


class _AbortButton(QPushButton):
    def configure(self, text=None, command=None, **_kwargs):
        if text is not None:
            self.setText(text)
        if command is not None:
            try:
                self.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.clicked.connect(command)


class _AbortBar(QWidget):
    """Top-center abort strip. Must not steal focus or call activateWindow."""

    def __init__(self, session):
        super().__init__(None)
        _mark_tool_window(self, opacity=None, no_activate=True)
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(280, 52)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background-color: #2b2b2b;")
        self.button = _AbortButton("中止绘画 (Esc / Q)", self)
        self.button.setFixedHeight(36)
        self.button.setFont(QFont(FONT_FAMILY, 13))
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.clicked.connect(session._request_abort)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.button)


class DrawSessionMixin:
    def start_drawing(self):
        """开始绘画"""
        if not self.contours or len(self.contours) == 0:
            self.log("没有可画的线条")
            return

        total_points = 0
        for contour in self.contours:
            points = contour.squeeze()
            if len(points.shape) > 1:
                total_points += len(points)

        method = self.draw_method.get()
        speed = self.speed_mult.get()
        self.log(f"准备绘画：{len(self.contours)} 条，{method}")
        if total_points > 50000:
            self.log("点数较多，可调高「线条简化度」或「跳点加速」")

        draw_delay = self.draw_delay.get() / 1000.0 / speed
        lift_pause = self.lift_pause.get()

        if method == "短行程":
            target = start_drawing_method_1
            args = (self, self.contours, self.img_w, self.img_h,
                    int(self.stroke_len.get()), draw_delay, lift_pause, speed)
        elif method == "智能拖动":
            target = start_drawing_method_2
            args = (self, self.contours, self.img_w, self.img_h,
                    int(self.min_drag.get()), draw_delay, speed, lift_pause)
        elif method == "仿真人":
            target = start_drawing_method_3
            args = (self, self.contours, self.img_w, self.img_h,
                    draw_delay, lift_pause,
                    int(self.hand_shake.get()),
                    self.think_pause.get(),
                    int(self.corner_sharp.get()),
                    speed)
        elif method == "压感":
            target = start_drawing_method_4
            args = (self, self.contours, self.img_w, self.img_h,
                    draw_delay, lift_pause,
                    0.0,
                    self.taper_ratio.get(),
                    speed)
        else:
            self.log(f"未知绘画方法：{method}")
            log_error(f"未知绘画方法: {method}")
            return

        self._pending_draw = (target, args)
        self.start_btn.configure(state="disabled")
        if focus_terminal():
            log_info("已激活终端窗口")
        mode = CALIB_ALIASES.get(self.canvas_calib.get(), "manual")
        self.root.iconify()
        if mode == "auto":
            self.log("窗口将最小化，正在识别微信画布")
            self.root.after(2000, self._try_auto_canvas)
        else:
            self.log("窗口将最小化，请点出画布的左上角和右下角")
            self.root.after(2000, self._start_calibration_on_main_thread)

    def _try_auto_canvas(self):
        result = detect_wechat_canvas()
        if not result.get("ok"):
            reason = result.get("reason") or "自动识别失败"
            self.log(reason)
            self.log("改为手动点角")
            self._start_calibration_on_main_thread()
            return
        self._auto_tl = result["top_left"]
        self._auto_br = result["bottom_right"]
        self.log(f"已识别画布 {self._auto_tl} → {self._auto_br}")
        self._show_auto_confirm_overlay()

    def _show_auto_confirm_overlay(self):
        self._close_calibrate_windows()
        overlay = _CalibOverlay(self, mode="confirm")
        overlay.set_confirm_rect(self._auto_tl, self._auto_br)
        overlay.show()
        overlay.raise_()
        self._bind_root_keys(
            (Qt.Key.Key_Return, self._accept_auto_canvas),
            (Qt.Key.Key_Enter, self._accept_auto_canvas),
            (Qt.Key.Key_Escape, self._reject_auto_canvas),
            (Qt.Key.Key_Q, self._reject_auto_canvas),
        )
        self._calib_overlay = overlay
        self._calib_canvas = overlay
        self._show_calib_hint("回车确认此框 · Esc 改为手动")

    def _accept_auto_canvas(self):
        tl = getattr(self, "_auto_tl", None)
        br = getattr(self, "_auto_br", None)
        self._destroy_calib_overlay()
        if tl is None or br is None:
            self._start_calibration_on_main_thread()
            return
        self._apply_calib_corners(tl, br)

    def _reject_auto_canvas(self):
        self._destroy_calib_overlay()
        self.log("已取消识别框，改为手动点角")
        self._start_calibration_on_main_thread()

    def _start_calibration_on_main_thread(self):
        """用 Qt 覆盖层采集角点，彻底避开 macOS 上 pynput Listener 的 GIL 崩溃。"""
        self._calib_points = []
        self._close_calibrate_windows()
        self.log("标定：请点击画布左上角")
        log_info("启动 Qt 标定覆盖层")

        overlay = _CalibOverlay(self, mode="manual")
        overlay.show()
        overlay.raise_()
        self._bind_root_keys(
            (Qt.Key.Key_Escape, self._cancel_calibration),
            (Qt.Key.Key_Q, self._cancel_calibration),
        )
        self._calib_overlay = overlay
        self._calib_canvas = overlay
        self._calib_label_id = None
        self._show_calib_hint("点击画布左上角 · Esc 取消")

    def _on_calib_point(self, x, y):
        self._calib_points.append((int(x), int(y)))
        if len(self._calib_points) == 1:
            pt = self._calib_points[0]
            self.log(f"左上角 ({pt[0]}, {pt[1]})")
            self._show_calib_hint("点击画布右下角 · Esc 取消")
            if self._calib_canvas is not None:
                self._calib_canvas.set_first_point(pt)
            return

        pt = self._calib_points[1]
        self.log(f"右下角 ({pt[0]}, {pt[1]})")
        self._destroy_calib_overlay()
        self._apply_calib_corners(self._calib_points[0], pt)

    def _apply_calib_corners(self, top_left, bottom_right):
        calib = compute_canvas_calibration(top_left, bottom_right, self.img_w, self.img_h)
        if calib is None or calib[0] is None:
            self.log("角点无效，已取消")
            self.on_drawing_complete()
            return
        canvas_w = int(bottom_right[0] - top_left[0])
        canvas_h = int(bottom_right[1] - top_left[1])
        self.log(f"画布 {canvas_w}×{canvas_h}")
        self._pending_calib = calib
        self._show_abort_window()
        self.log("请点击画布内部以聚焦")
        self._update_abort_banner("请点击画布内部", click_aborts=False)
        try:
            start_one_click_listener(lambda x, y: self.root.after(0, lambda: self._on_focus_click(x, y)))
        except Exception as exc:
            log_error("启动聚焦点击监听失败", exc)
            self.log("聚焦失败，已取消")
            self.on_drawing_complete()

    def _on_focus_click(self, x, y):
        stop_one_click_listener()
        log_info(f"已聚焦 ({x}, {y})")
        self._update_abort_banner("中止绘画 (Esc / Q)", click_aborts=True)
        self.log("已聚焦，请松开鼠标")
        self.root.after(500, self._after_focus_ready)

    def _after_focus_ready(self):
        start_hotkey_listener()
        calib = getattr(self, "_pending_calib", None)
        self._pending_calib = None
        self.log("1.5 秒后开始")
        self.root.after(1500, lambda: self._launch_drawing_thread(calib))

    def _cancel_calibration(self):
        self.log("已取消标定")
        self._pending_draw = None
        self.on_drawing_complete()

    def _destroy_calib_overlay(self):
        overlay = getattr(self, "_calib_overlay", None)
        self._calib_overlay = None
        self._calib_canvas = None
        self._calib_label_id = None
        _safe_close(overlay)
        self._close_hint_window()

    def _close_hint_window(self):
        win = getattr(self, "_hint_win", None)
        self._hint_win = None
        self._hint_label = None
        _safe_close(win)

    def _show_calib_hint(self, text):
        """不透明顶栏提示，避免半透明覆盖层上的字看不清。"""
        if getattr(self, "_hint_win", None) is None:
            win = _HintBanner(text)
            self._hint_win = win
            self._hint_label = win._label
            self._place_top_center(win, width=360, height=52, margin_top=18)
            win.show()
        elif self._hint_label is not None:
            if hasattr(self._hint_win, "set_text"):
                self._hint_win.set_text(text)
            else:
                self._hint_label.setText(text)

    def _place_top_center(self, win, width=280, height=52, margin_top=18):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            screen_w = geo.width()
            x = geo.x() + max(0, (screen_w - width) // 2)
            y = geo.y() + margin_top
        else:
            x = max(0, (1920 - width) // 2)
            y = margin_top
        win.setGeometry(x, y, width, height)

    def _show_abort_window(self):
        self._close_abort_window()
        win = _AbortBar(self)
        self._abort_btn = win.button
        self._place_top_center(win)
        win.show()
        self._bind_root_keys(
            (Qt.Key.Key_Escape, self._on_global_abort),
            (Qt.Key.Key_Q, self._on_global_abort),
        )
        self._abort_win = win

    def _update_abort_banner(self, text, click_aborts=True):
        btn = getattr(self, "_abort_btn", None)
        if btn is None:
            return
        btn.configure(text=text, command=self._request_abort if click_aborts else lambda: None)

    def _on_global_abort(self, event=None):
        self._request_abort()
        return "break"

    def _request_abort(self):
        request_abort()
        self.log("正在停笔…")

    def _close_abort_window(self):
        win = getattr(self, "_abort_win", None)
        self._abort_win = None
        _safe_close(win)

    def _launch_drawing_thread(self, calib):
        pending = getattr(self, "_pending_draw", None)
        if pending is None:
            self.on_drawing_complete()
            return
        target, args = pending
        self._pending_draw = None

        def launch():
            try:
                log_info("绘画线程启动")
                target(*args, calib_data=calib)
            except Exception as exc:
                log_error("绘画线程异常", exc)
                self.on_drawing_complete()

        threading.Thread(target=launch, daemon=True).start()

    def _bind_root_keys(self, *bindings):
        self._unbind_root_keys()
        parent = getattr(self, "root", None)
        if parent is None:
            return
        shortcuts = []
        for key, slot in bindings:
            shortcut = QShortcut(QKeySequence(key), parent)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(slot)
            shortcuts.append(shortcut)
        self._root_shortcuts = shortcuts

    def _unbind_root_keys(self):
        for shortcut in getattr(self, "_root_shortcuts", None) or []:
            try:
                shortcut.setEnabled(False)
                shortcut.deleteLater()
            except Exception:
                pass
        self._root_shortcuts = []

    def _close_calibrate_windows(self):
        stop_one_click_listener()
        self._unbind_root_keys()
        self._destroy_calib_overlay()
        self._close_abort_window()
        self._abort_btn = None
        self._pending_calib = None
        self._close_hint_window()

    def on_drawing_complete(self):
        """绘画完成"""
        def restore():
            self._close_calibrate_windows()
            self.start_btn.configure(state="normal")
            self.root.deiconify()
        self.root.after(0, restore)
