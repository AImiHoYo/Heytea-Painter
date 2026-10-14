"""
绘画会话：标定覆盖层 → 聚焦点击 → 延迟 → 后台线程落笔。
中止条保持顶栏居中约 280×52；不调用 focus_force()。
"""

import sys
import threading
import tkinter as tk

import customtkinter as ctk

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
    stop_hotkey_listener,
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
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-alpha", 0.28)
        except Exception:
            pass
        vx = self.root.winfo_vrootx()
        vy = self.root.winfo_vrooty()
        vw = self.root.winfo_vrootwidth() or self.root.winfo_screenwidth()
        vh = self.root.winfo_vrootheight() or self.root.winfo_screenheight()
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
        canvas = tk.Canvas(overlay, highlightthickness=0, cursor="arrow", bg="#111111")
        canvas.pack(fill="both", expand=True)
        ox = vx
        oy = vy
        x0, y0 = self._auto_tl
        x1, y1 = self._auto_br
        canvas.create_rectangle(x0 - ox, y0 - oy, x1 - ox, y1 - oy, outline="#3ddc84", width=4)
        overlay.bind("<Return>", lambda e: self._accept_auto_canvas())
        overlay.bind("<Escape>", lambda e: self._reject_auto_canvas())
        overlay.bind("q", lambda e: self._reject_auto_canvas())
        overlay.bind("Q", lambda e: self._reject_auto_canvas())
        self.root.bind_all("<Return>", lambda e: self._accept_auto_canvas())
        self.root.bind_all("<Escape>", lambda e: self._reject_auto_canvas())
        overlay.deiconify()
        overlay.lift()
        self._calib_overlay = overlay
        self._calib_canvas = canvas
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
        """用 Tk 覆盖层采集角点，彻底避开 macOS 上 pynput Listener 的 GIL 崩溃。"""
        self._calib_points = []
        self._close_calibrate_windows()
        self.log("标定：请点击画布左上角")
        log_info("启动 Tk 标定覆盖层")

        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-alpha", 0.28)
        except Exception:
            pass

        vx = self.root.winfo_vrootx()
        vy = self.root.winfo_vrooty()
        vw = self.root.winfo_vrootwidth() or self.root.winfo_screenwidth()
        vh = self.root.winfo_vrootheight() or self.root.winfo_screenheight()
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")

        canvas = tk.Canvas(overlay, highlightthickness=0, cursor="crosshair", bg="#111111")
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Button-1>", lambda e: self._on_calib_point(e.x_root, e.y_root))
        overlay.bind("<Escape>", lambda e: self._cancel_calibration())
        overlay.bind("q", lambda e: self._cancel_calibration())
        overlay.bind("Q", lambda e: self._cancel_calibration())
        overlay.deiconify()
        overlay.lift()

        self.root.bind_all("<Escape>", lambda e: self._cancel_calibration())
        self.root.bind_all("<q>", lambda e: self._cancel_calibration())
        self.root.bind_all("<Q>", lambda e: self._cancel_calibration())

        self._calib_overlay = overlay
        self._calib_canvas = canvas
        self._calib_label_id = None
        self._show_calib_hint("点击画布左上角 · Esc 取消")

    def _on_calib_point(self, x, y):
        self._calib_points.append((int(x), int(y)))
        if len(self._calib_points) == 1:
            pt = self._calib_points[0]
            self.log(f"左上角 ({pt[0]}, {pt[1]})")
            self._show_calib_hint("点击画布右下角 · Esc 取消")
            if self._calib_canvas is not None:
                ox = self._calib_overlay.winfo_rootx() if self._calib_overlay else 0
                oy = self._calib_overlay.winfo_rooty() if self._calib_overlay else 0
                x0, y0 = pt
                self._calib_canvas.create_oval(
                    x0 - ox - 7, y0 - oy - 7, x0 - ox + 7, y0 - oy + 7, outline="#ff5555", width=3
                )
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
        overlay = self._calib_overlay
        self._calib_overlay = None
        self._calib_canvas = None
        self._calib_label_id = None
        if overlay is not None:
            try:
                overlay.destroy()
            except Exception:
                pass
        self._close_hint_window()

    def _close_hint_window(self):
        win = self._hint_win
        self._hint_win = None
        self._hint_label = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _show_calib_hint(self, text):
        """不透明顶栏提示，避免半透明覆盖层上的字看不清。"""
        if self._hint_win is None:
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            try:
                win.attributes("-alpha", 0.94)
            except Exception:
                pass
            label = tk.Label(
                win,
                text=text,
                bg="#1c1c1c",
                fg="white",
                font=(FONT_FAMILY, 15, "bold"),
                padx=18,
                pady=12,
            )
            label.pack(fill="both", expand=True)
            self._hint_win = win
            self._hint_label = label
            self._place_top_center(win, width=360, height=52, margin_top=18)
        elif self._hint_label is not None:
            self._hint_label.configure(text=text)

    def _place_top_center(self, win, width=280, height=52, margin_top=18):
        win.update_idletasks()
        screen_w = win.winfo_screenwidth()
        x = max(0, (screen_w - width) // 2)
        win.geometry(f"{width}x{height}+{x}+{margin_top}")

    def _show_abort_window(self):
        self._close_abort_window()
        win = ctk.CTkToplevel(self.root)
        win.title(APP_NAME)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        if sys.platform == "darwin":
            try:
                win.tk.call("::tk::unsupported::MacWindowStyle", "style", win._w, "floating", "noActivates")
            except Exception:
                pass
        self._abort_btn = ctk.CTkButton(
            win,
            text="中止绘画 (Esc / Q)",
            command=self._request_abort,
            height=36,
            font=(FONT_FAMILY, 13),
        )
        self._abort_btn.pack(fill="both", expand=True, padx=8, pady=8)
        self._place_top_center(win)
        win.bind("<Escape>", lambda e: self._request_abort())
        win.bind("q", lambda e: self._request_abort())
        win.bind("Q", lambda e: self._request_abort())
        self.root.bind_all("<Escape>", self._on_global_abort)
        self.root.bind_all("<q>", self._on_global_abort)
        self.root.bind_all("<Q>", self._on_global_abort)
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
        win = self._abort_win
        self._abort_win = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _launch_drawing_thread(self, calib):
        pending = self._pending_draw
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

    def _close_calibrate_windows(self):
        stop_one_click_listener()
        for seq in ("<Escape>", "<q>", "<Q>", "<Return>"):
            try:
                self.root.unbind_all(seq)
            except Exception:
                pass
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
