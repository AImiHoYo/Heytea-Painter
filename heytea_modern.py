"""
Heytea Painter - Modern AI Drawing Tool
Using CustomTkinter for modern UI
"""

import sys
import os

from modules.app_logger import error_log_path, log_error, log_info, run_log_path, setup_logging

setup_logging()

import ctypes
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        log_info("DPI 感知: Per-Monitor V1")
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            log_info("DPI 感知: System DPI")
        except Exception as e:
            log_error("DPI 设置失败", e)
elif sys.platform == "darwin":
    log_info("macOS 使用系统原生缩放")

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import threading
import cv2
import numpy as np
from datetime import datetime

from modules.draw_session import DrawSessionMixin
from modules.platform_input import (
    permission_hint,
    stop_hotkey_listener,
    stop_one_click_listener,
    warmup_backends,
)
from modules.preview import PreviewMixin
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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLOR_MUTED = "#9aa0a6"
COLOR_INK = "#DCE4EE"
COLOR_STAGE = "#1a1a1a"
COLOR_ACCENT = "#3498db"
COLOR_GO = "#2ecc71"
COLOR_GO_HOVER = "#27ae60"

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_FILES = []
if os.path.exists(FONT_DIR):
    FONT_FILES = [f for f in os.listdir(FONT_DIR) if f.endswith((".ttf", ".TTF", ".otf", ".OTF"))]

CUSTOM_FONT = None
if FONT_FILES:
    try:
        CUSTOM_FONT = os.path.join(FONT_DIR, FONT_FILES[0])
    except Exception:
        pass

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


def apply_app_identity(root):
    """设置窗口标题、任务栏/程序坞图标和系统显示名。"""
    root.title(APP_NAME)
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Heytea.Painter")
        except Exception:
            pass
        if os.path.isfile(ICON_ICO):
            try:
                root.iconbitmap(ICON_ICO)
            except Exception:
                pass

    png_path = ICON_PNG if os.path.isfile(ICON_PNG) else ICON_SRC_PNG
    if os.path.isfile(png_path):
        try:
            image = Image.open(png_path).convert("RGBA")
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            root.iconphoto(True, photo)
            root._app_icon_photo = photo
        except Exception as exc:
            log_error("窗口图标加载失败", exc)

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
            icon_path = ICON_ICNS if os.path.isfile(ICON_ICNS) else png_path
            if os.path.isfile(icon_path):
                ns_image = NSImage.alloc().initWithContentsOfFile_(icon_path)
                if ns_image is not None:
                    NSApp.setApplicationIconImage_(ns_image)
        except Exception as exc:
            log_error("macOS 图标设置失败", exc)


class ModernDrawingApp(PreviewMixin, DrawSessionMixin):
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1600x950")

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

        self.setup_gui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_quit)
        if sys.platform == "darwin":
            try:
                self.root.createcommand("::tk::mac::Quit", self._on_app_quit)
            except Exception:
                pass
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
        self._build_topbar()

        main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        left_right_container = ctk.CTkFrame(main_container, fg_color="transparent")
        left_right_container.pack(fill="both", expand=True)

        self.control_panel = ctk.CTkScrollableFrame(
            left_right_container, width=380, corner_radius=10)
        self.control_panel.pack(side="left", fill="y", padx=(0, 14))

        right_container = ctk.CTkFrame(left_right_container, fg_color="transparent")
        right_container.pack(side="right", fill="both", expand=True)

        preview_frame = ctk.CTkFrame(right_container, corner_radius=10)
        preview_frame.pack(fill="both", expand=True, pady=(0, 12))

        preview_header = ctk.CTkFrame(preview_frame, fg_color="transparent")
        preview_header.pack(fill="x", padx=16, pady=(12, 8))

        title_col = ctk.CTkFrame(preview_header, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(title_col, text="预览", font=(FONT_FAMILY, 16, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            title_col, text="红线即落笔路径",
            font=(FONT_FAMILY, 11), text_color=COLOR_MUTED).pack(anchor="w")

        zoom_frame = ctk.CTkFrame(preview_header, fg_color="transparent")
        zoom_frame.pack(side="right")
        for text, cmd in (("＋", self.zoom_in), ("－", self.zoom_out), ("复位", self.reset_zoom)):
            ctk.CTkButton(
                zoom_frame, text=text, width=50, height=30, command=cmd,
                font=(FONT_FAMILY, 11),
            ).pack(side="left", padx=3)

        self.preview_canvas = ctk.CTkCanvas(preview_frame, bg=COLOR_STAGE, highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.preview_canvas.bind("<MouseWheel>", self.on_preview_mousewheel)
        self.preview_canvas.bind("<Button-4>", self.on_preview_mousewheel)
        self.preview_canvas.bind("<Button-5>", self.on_preview_mousewheel)

        console_frame = ctk.CTkFrame(right_container, corner_radius=10, height=148)
        console_frame.pack(fill="x")
        console_frame.pack_propagate(False)
        ctk.CTkLabel(
            console_frame, text="日志",
            font=(FONT_FAMILY, 12, "bold"), text_color=COLOR_MUTED,
        ).pack(anchor="w", padx=16, pady=(10, 2))
        self.console_text = ctk.CTkTextbox(console_frame, height=100, font=(FONT_FAMILY, 12), wrap="word")
        self.console_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.console_text.configure(state="disabled")

        self.create_controls()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self.root, height=64, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        png_path = ICON_PNG if os.path.isfile(ICON_PNG) else ICON_SRC_PNG
        if os.path.isfile(png_path):
            try:
                image = Image.open(png_path).convert("RGBA")
                image.thumbnail((40, 40), Image.Resampling.LANCZOS)
                self._header_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(40, 40))
                ctk.CTkLabel(bar, image=self._header_icon, text="").pack(side="left", padx=(18, 10), pady=12)
            except Exception:
                pass

        titles = ctk.CTkFrame(bar, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text=APP_NAME, font=(FONT_FAMILY, 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            titles, text="线稿提取  ·  模拟落笔",
            font=(FONT_FAMILY, 11), text_color=COLOR_MUTED).pack(anchor="w")

        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.pack(side="right", padx=16)
        self.ui_mode = ctk.CTkSegmentedButton(
            actions,
            values=["简单", "高级"],
            font=(FONT_FAMILY, 12),
            command=self.on_ui_mode_change,
            width=120,
            height=32,
        )
        self.ui_mode.set("简单")
        self.ui_mode.pack(side="left", padx=(0, 10))
        ghost = {"width": 84, "height": 32, "font": (FONT_FAMILY, 12)}
        ctk.CTkButton(actions, text="保存设置", command=self.save_presets, **ghost).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="读取设置", command=self.load_presets, **ghost).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="一键推荐", command=self.apply_recommended, **ghost).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="重置", command=self.reset_params, **ghost).pack(side="left", padx=4)

    def section_card(self, parent, title, step=None, caption=None):
        """侧栏步骤卡片，返回可放控件的内容区。"""
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 4))
        if step:
            ctk.CTkLabel(
                head, text=step, width=26, height=22,
                fg_color=COLOR_ACCENT, text_color=COLOR_INK, corner_radius=7,
                font=(FONT_FAMILY, 11, "bold"),
            ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(head, text=title, font=(FONT_FAMILY, 14, "bold")).pack(side="left")
        if caption:
            ctk.CTkLabel(
                card, text=caption, font=(FONT_FAMILY, 11),
                text_color=COLOR_MUTED,
            ).pack(anchor="w", padx=14, pady=(0, 2))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=(2, 12))
        return body

    def log(self, message):
        """用户可见日志：右侧控制台 + 终端一行。诊断请用 log_info。"""
        text = str(message).strip()
        if not text or text == self._last_log_line:
            return
        self._last_log_line = text
        timestamp = datetime.now().strftime("%H:%M")
        line = f"[{timestamp}] {text}\n"

        def write():
            try:
                box = self.console_text
                if box is None:
                    return
                box.configure(state="normal")
                box.insert("end", line)
                end_line = int(float(box.index("end-1c")))
                if end_line > 220:
                    box.delete("1.0", f"{end_line - 180}.0")
                box.see("end")
                box.configure(state="disabled")
            except Exception:
                pass

        try:
            if threading.current_thread() is threading.main_thread():
                write()
            else:
                self.root.after(0, write)
        except Exception:
            pass
        print(text)

    def create_controls(self):
        """创建控制面板。控件名与回调保持不变。"""
        file_frame = self.section_card(self.control_panel, "打开图片")
        ctk.CTkButton(
            file_frame, text="选择图片", command=self.load_image,
            height=40, font=(FONT_FAMILY, 13, "bold"),
        ).pack(fill="x", pady=(2, 2))
        self.simple_guide = ctk.CTkLabel(
            file_frame,
            text="新手建议：先点顶栏「一键推荐」，再用 Anime2Sketch + 仿真人开画",
            font=(FONT_FAMILY, 11),
            text_color=COLOR_ACCENT,
            wraplength=300,
            justify="left",
        )
        self.simple_guide.pack(anchor="w", pady=(6, 2))

        extract_frame = self.section_card(
            self.control_panel, "提取线稿", step="1",
            caption="先出红线，再决定怎么画")

        self.extraction_method = ctk.CTkSegmentedButton(
            extract_frame,
            values=["Pencil Sketch", "Canny", "Anime2Sketch", "LineartAnime"],
            font=(FONT_FAMILY, 10))
        self.extraction_method.set("Pencil Sketch")
        self.extraction_method.pack(fill="x", pady=(0, 8))

        self.force_reinfer_btn = ctk.CTkButton(
            extract_frame, text="强制重推理（清缓存）",
            command=self.force_reinfer_preview,
            height=28, font=(FONT_FAMILY, 11),
            fg_color="transparent", border_width=1, text_color=COLOR_ACCENT,
        )

        self.params_container = ctk.CTkFrame(extract_frame, fg_color="transparent")
        self.params_container.pack(fill="x")

        self.pencil_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.sigma_s = self.create_modern_slider(self.pencil_params, "平滑度", 1, 200, 60, tooltip="控制线条平滑程度，值越大越平滑")
        self.sigma_r = self.create_modern_slider(self.pencil_params, "细节保留", 0.01, 1.0, 0.4, 0.01, tooltip="保留图像细节的强度")
        self.shade_factor = self.create_modern_slider(self.pencil_params, "阴影强度", 0.0, 1.0, 0.05, 0.01, tooltip="阴影的深度和强度")

        self.canny_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.canny_blur = self.create_modern_slider(self.canny_params, "高斯模糊", 1, 20, 3, 1, tooltip="预处理模糊程度，减少噪点")
        self.canny_low = self.create_modern_slider(self.canny_params, "低阈值", 1, 500, 50, 1, tooltip="边缘检测下限，低于此值忽略")
        self.canny_high = self.create_modern_slider(self.canny_params, "高阈值", 1, 1000, 150, 1, tooltip="边缘检测上限，高于此值保留")

        self.anime_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.anime_threshold = self.create_modern_slider(self.anime_params, "二值化阈值", 50, 200, 127, 1, tooltip="黑白分界点，控制线条粗细")
        self.anime_morph_size = self.create_modern_slider(self.anime_params, "形态学核大小", 1, 5, 2, 1, tooltip="线条处理核大小，影响线条连续性")
        self.anime_morph_iter = self.create_modern_slider(self.anime_params, "形态学迭代", 1, 3, 1, 1, tooltip="形态学处理次数")
        self.anime_min_area = self.create_modern_slider(self.anime_params, "最小轮廓面积", 5, 100, 10, 1, tooltip="过滤小轮廓，减少噪点")

        self.anime_expert = ctk.CTkFrame(self.anime_params, fg_color="transparent")
        self.anime_expert.pack(fill="x")
        adv_label = ctk.CTkLabel(self.anime_expert, text="高级参数", font=(FONT_FAMILY, 11, "bold"))
        adv_label.pack(pady=5)

        self.anime_pre_blur = self.create_modern_slider(self.anime_expert, "预处理模糊", 0, 9, 0, 1, tooltip="AI处理前的模糊强度")
        self.anime_edge_enhance = self.create_modern_slider(self.anime_expert, "边缘增强", 0, 3.0, 0, 0.1, tooltip="增强边缘锐度")
        self.anime_sigmoid = self.create_modern_slider(self.anime_expert, "模型敏感度", 0.3, 0.9, 0.5, 0.05, tooltip="AI模型的灵敏度")

        self.anime_invert = ctk.CTkCheckBox(self.anime_expert, text="反转提取", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.anime_invert.pack(pady=2)

        self.anime_adaptive = ctk.CTkCheckBox(self.anime_expert, text="自适应二值化", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.anime_adaptive.pack(pady=2)

        ctk.CTkLabel(self.anime_params, text="轮廓模式:", font=(FONT_FAMILY, 11)).pack(pady=2)
        self.anime_mode = ctk.CTkSegmentedButton(
            self.anime_params,
            values=["外部轮廓", "所有轮廓", "中心线"],
            command=lambda v: self.update_preview(),
            font=(FONT_FAMILY, 10))
        self.anime_mode.set("外部轮廓")
        self.anime_mode.pack(fill="x", pady=5)

        self.lineart_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.lineart_detect = self.create_modern_slider(
            self.lineart_params, "检测分辨率", 256, 1024, 512, 64,
            tooltip="官方 detect_resolution，默认 512")
        self.lineart_min_area = self.create_modern_slider(
            self.lineart_params, "最小路径长度", 5, 100, 10, 1,
            tooltip="中心线按路径长度过滤碎线；外框模式仍按面积过滤")
        self.lineart_invert = ctk.CTkCheckBox(
            self.lineart_params, text="官方反色 (255−x)",
            command=self.update_preview, font=(FONT_FAMILY, 11))
        self.lineart_invert.select()
        self.lineart_invert.pack(pady=2)
        ctk.CTkLabel(self.lineart_params, text="轮廓模式:", font=(FONT_FAMILY, 11)).pack(pady=2)
        self.lineart_mode = ctk.CTkSegmentedButton(
            self.lineart_params,
            values=["外部轮廓", "所有轮廓", "中心线"],
            command=lambda v: self.update_preview(),
            font=(FONT_FAMILY, 10))
        self.lineart_mode.set("中心线")
        self.lineart_mode.pack(fill="x", pady=5)

        self.extraction_method.configure(command=self.on_method_change)

        optimize_frame = self.section_card(
            self.control_panel, "路径优化", step="2",
            caption="红线阶段处理，影响预览和落笔")

        self.simplify_eps = self.create_modern_slider(optimize_frame, "线条简化度 [全局]", 0.1, 5.0, 1.0, 0.1, tooltip="简化线条路径，减少点数")
        self.preview_thick = self.create_modern_slider(optimize_frame, "预览线条粗细 [预览]", 1, 20, 1, 1, tooltip="预览图中线条的粗细")
        self.taper_paths = ctk.CTkCheckBox(
            optimize_frame, text="起收笔路径（红线重叠）[全局]",
            command=self.update_preview, font=(FONT_FAMILY, 11))
        self.taper_paths.select()
        self.taper_paths.pack(pady=5)

        self.show_chunk_grid = ctk.CTkCheckBox(
            optimize_frame, text="显示分块网格 [预览]",
            command=self.update_preview, font=(FONT_FAMILY, 11))
        self.show_chunk_grid.pack(pady=5)

        self.optimize_expert = ctk.CTkFrame(optimize_frame, fg_color="transparent")
        self.optimize_expert.pack(fill="x")
        self.spline_smooth = self.create_modern_slider(self.optimize_expert, "路径平滑度 [全局]", 0, 5000, 0, 1, tooltip="使用B样条平滑路径")
        self.jitter_correct = self.create_modern_slider(self.optimize_expert, "抖动修正强度 [全局]", 0, 10, 0, 1, tooltip="修正线条抖动，使线条更平滑")

        self.thin_contours = ctk.CTkCheckBox(self.optimize_expert, text="边缘细化（双线变单线）[全局]", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.thin_contours.pack(pady=5)

        self.taper_layers = self.create_modern_slider(
            self.optimize_expert, "重叠层数 [全局]", 1, 4, 3, 1,
            tooltip="粗处最多叠几条红线；1=不重叠")
        self.taper_ratio = self.create_modern_slider(
            self.optimize_expert, "起收笔比例 [全局]", 0.10, 0.40, 0.18, 0.02,
            tooltip="两端加粗（顿笔）占整段长度的比例，效果为粗-细-粗")
        self.taper_spacing = self.create_modern_slider(
            self.optimize_expert, "层间距 [全局]", 0.6, 2.0, 1.0, 0.1,
            tooltip="重叠红线之间的像素间距")

        self.skip_points = self.create_modern_slider(self.optimize_expert, "跳点加速 [全局]", 1, 5, 1, 1, tooltip="跳过部分点来加快绘画速度")
        self.bbox_cell_size = self.create_modern_slider(
            self.optimize_expert, "分块边长 [全局]", 0, 400, 0, 10,
            tooltip="路径包围盒分块边长（像素）。0=自动，越大块越大、跨区跳跃越少")

        draw_frame = self.section_card(
            self.control_panel, "绘画方式", step="3",
            caption="只决定运笔节奏，粗细看红线")

        self.draw_method = ctk.CTkSegmentedButton(
            draw_frame,
            values=["短行程", "智能拖动", "仿真人", "压感"],
            font=(FONT_FAMILY, 11))
        self.draw_method.set("短行程")
        self.draw_method.pack(fill="x", pady=(0, 6))

        self.draw_params_container = ctk.CTkFrame(draw_frame, fg_color="transparent")
        self.draw_params_container.pack(fill="x")

        self.m1_params = ctk.CTkFrame(self.draw_params_container, fg_color="transparent")
        self.stroke_len = self.create_modern_slider(self.m1_params, "笔画长度", 5, 100, 15, 5, tooltip="每次绘制的点数（短行程模式）")

        self.m2_params = ctk.CTkFrame(self.draw_params_container, fg_color="transparent")
        self.min_drag = self.create_modern_slider(self.m2_params, "最小拖动距离", 1, 20, 5, 1, tooltip="触发移动的最小距离（智能拖动）")

        self.m3_params = ctk.CTkFrame(self.draw_params_container, fg_color="transparent")
        self.hand_shake = self.create_modern_slider(self.m3_params, "手部抖动", 0, 5, 1, 1, tooltip="模拟手部抖动（仿真人）")
        self.think_pause = self.create_modern_slider(self.m3_params, "思考停顿倍率", 1, 10, 3, 1, tooltip="转角处的思考停顿（仿真人）")
        self.corner_sharp = self.create_modern_slider(self.m3_params, "转角锐利度", 0, 10, 5, 1, tooltip="转角锐利度：0=圆润平滑，10=极度锐利")

        self.m4_params = ctk.CTkFrame(self.draw_params_container, fg_color="transparent")
        ctk.CTkLabel(
            self.m4_params,
            text="粗细已画在红线里。请先开「起收笔路径」，绘画只跟随红线。",
            font=(FONT_FAMILY, 11),
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=4)

        self.draw_method.configure(command=self.on_draw_method_change)

        self.draw_delay = self.create_modern_slider(draw_frame, "绘画延迟(ms) [全局]", 1, 100, 5, 1, tooltip="每个运笔点之间的延迟")
        self.lift_pause = self.create_modern_slider(
            draw_frame, "换线停顿(秒) [全局]", 0.05, 10.0, 5.0, 0.05,
            tooltip="换线后的额外等待。仿真人建议 ≥5 秒，防止喜茶小程序误清屏；抬笔至少约 0.12 秒以防连笔")
        self.lift_pause_tip = ctk.CTkLabel(
            draw_frame,
            text="提示：仿真人模式建议换线停顿 ≥ 5 秒，避免小程序清屏",
            font=(FONT_FAMILY, 11),
            text_color=COLOR_MUTED,
            wraplength=300,
            justify="left",
        )
        self.lift_pause_tip.pack(anchor="w", pady=(0, 6))

        speed_frame = self.section_card(self.control_panel, "运笔速度")
        self.speed_expert = ctk.CTkFrame(speed_frame, fg_color="transparent")
        self.speed_expert.pack(fill="x")
        self.speed_mult = self.create_modern_slider(
            self.speed_expert, "运笔速度 [全局]", 0.1, 5.0, 1.0, 0.1,
            tooltip="只加快运笔点间距，不影响换线停顿")

        button_frame = self.section_card(
            self.control_panel, "落笔", step="4",
            caption="先定画布，再开始")

        self.canvas_calib = ctk.CTkSegmentedButton(
            button_frame,
            values=["手动定画布", "自动识别画布"],
            font=(FONT_FAMILY, 11),
        )
        self.canvas_calib.set("手动定画布")
        self.canvas_calib.pack(fill="x", pady=(0, 8))

        self.start_btn = ctk.CTkButton(
            button_frame, text="开始绘画",
            command=self.start_drawing,
            height=46, font=(FONT_FAMILY, 15, "bold"),
            fg_color=COLOR_GO, hover_color=COLOR_GO_HOVER,
            text_color="#ffffff", state="disabled")
        self.start_btn.pack(fill="x")

    def create_modern_slider(self, parent, label, from_, to, default, resolution=None, tooltip=None):
        """创建现代化滑块"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=3)

        if resolution is None:
            if (to - from_) < 10 and isinstance(default, float):
                resolution = 0.01
            else:
                resolution = 1

        if resolution >= 1:
            fmt = "{:.0f}"
        elif resolution >= 0.1:
            fmt = "{:.1f}"
        else:
            fmt = "{:.2f}"

        label_frame = ctk.CTkFrame(frame, fg_color="transparent")
        label_frame.pack(fill="x")

        label_widget = ctk.CTkLabel(
            label_frame, text=label, font=(FONT_FAMILY, 11), text_color=COLOR_MUTED)
        label_widget.pack(side="left")

        if tooltip:
            self.create_tooltip(label_widget, tooltip)

        var = ctk.DoubleVar(value=default)
        value_label = ctk.CTkLabel(
            label_frame, text=fmt.format(default),
            width=48, height=20, corner_radius=8,
            fg_color="transparent", text_color=COLOR_ACCENT,
            font=(FONT_FAMILY, 11, "bold"))
        value_label.pack(side="right")

        def update_label(*args):
            if not self.is_updating:
                value_label.configure(text=fmt.format(var.get()))

        var.trace_add("write", update_label)

        slider = ctk.CTkSlider(frame, from_=from_, to=to, variable=var,
                              command=lambda v: self.update_preview_throttled())
        slider.pack(fill="x", pady=2)

        return var

    def create_tooltip(self, widget, text):
        """创建鼠标悬停提示"""
        pass

    def on_method_change(self, value=None):
        """切换提取方法：只显示当前方法的参数。"""
        for widget in self.params_container.winfo_children():
            widget.pack_forget()

        method = self.extraction_method.get()
        if method == "Pencil Sketch":
            self.pencil_params.pack(fill="x")
        elif method == "Canny":
            self.canny_params.pack(fill="x")
        elif method == "Anime2Sketch":
            self.anime_params.pack(fill="x")
        elif method == "LineartAnime":
            self.lineart_params.pack(fill="x")

        # AI 方法才有边图缓存，强制重推理按钮只在这两个方法显示
        if hasattr(self, "force_reinfer_btn"):
            if method in ("Anime2Sketch", "LineartAnime"):
                self.force_reinfer_btn.pack(fill="x", pady=(0, 6), before=self.params_container)
            else:
                self.force_reinfer_btn.pack_forget()

        # 方法切换后按当前简单/高级折叠专家区
        if hasattr(self, "apply_ui_mode") and value is None:
            pass
        if hasattr(self, "anime_expert") and method == "Anime2Sketch":
            if self._ui_mode_key() == "simple":
                self.anime_expert.pack_forget()
            else:
                self.anime_expert.pack(fill="x")

        if value is not None:
            self._announce_extract = True
            self.update_preview()

    def on_draw_method_change(self, value=None):
        """切换绘画方法：只显示当前方法的参数。全局延迟/换线/运笔速度始终可见。"""
        for widget in self.draw_params_container.winfo_children():
            widget.pack_forget()

        if hasattr(self, "_ui_mode_key") and self._ui_mode_key() == "simple":
            return

        method = self.draw_method.get()
        if method == "短行程":
            self.m1_params.pack(fill="x")
        elif method == "智能拖动":
            self.m2_params.pack(fill="x")
        elif method == "仿真人":
            self.m3_params.pack(fill="x")
        elif method == "压感":
            self.m4_params.pack(fill="x")

    def load_image(self):
        """加载图片"""
        default_dir = os.path.join(os.path.dirname(__file__), "images")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")

        file_path = filedialog.askopenfilename(
            initialdir=default_dir,
            title="选择图片（支持任意位置）",
            filetypes=(
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("所有文件", "*.*")
            )
        )
        if file_path:
            self.file_path = file_path
            name = os.path.basename(file_path)
            size_text = ""
            try:
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
        self.root.destroy()

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
            if simple:
                self.simple_guide.pack(anchor="w", pady=(6, 2))
            else:
                self.simple_guide.pack_forget()
        if hasattr(self, "anime_expert"):
            if simple:
                self.anime_expert.pack_forget()
            else:
                if self.extraction_method.get() == "Anime2Sketch":
                    self.anime_expert.pack(fill="x")
        if hasattr(self, "optimize_expert"):
            if simple:
                self.optimize_expert.pack_forget()
            else:
                self.optimize_expert.pack(fill="x")
        if hasattr(self, "speed_expert"):
            if simple:
                self.speed_expert.pack_forget()
            else:
                self.speed_expert.pack(fill="x")
        if hasattr(self, "draw_params_container"):
            if simple:
                for widget in self.draw_params_container.winfo_children():
                    widget.pack_forget()
            else:
                self.on_draw_method_change()
        if hasattr(self, "extraction_method"):
            self._apply_extract_values(simple)

    def _apply_extract_values(self, simple):
        """简单模式只保留 AI 提取方法；Pencil/Canny 收进高级模式。"""
        target = SIMPLE_EXTRACT_METHODS if simple else ALL_EXTRACT_METHODS
        try:
            current_values = list(self.extraction_method.cget("values") or [])
        except Exception:
            current_values = None
        if current_values == target:
            return
        current = self.extraction_method.get()
        self.extraction_method.configure(values=target)
        if current not in target:
            self.extraction_method.set(SIMPLE_EXTRACT_METHODS[0])
            self.on_method_change()
            self.log(
                f"简单模式隐藏 Pencil/Canny：提取方法已切为 {SIMPLE_EXTRACT_METHODS[0]}"
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


if __name__ == "__main__":
    root = ctk.CTk()
    apply_app_identity(root)
    app = ModernDrawingApp(root)
    root.mainloop()
