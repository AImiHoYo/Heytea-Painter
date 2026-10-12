"""
Heytea Painter - Modern AI Drawing Tool
Using CustomTkinter for modern UI
"""

import sys
import os

# 🔧 关键: 在导入任何GUI库之前设置DPI感知 (使用Per-Monitor V1)
import ctypes
try:
    # Windows 8.1+ Per-Monitor DPI Aware (稳定可靠)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    print("✓ DPI感知已启用 (Per-Monitor V1)")
except:
    # Fallback: Windows Vista+ System DPI Aware
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        print("✓ DPI感知已启用 (System DPI)")
    except Exception as e:
        print(f"⚠ DPI设置失败: {e}")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import threading
import json
import cv2
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from modules.image_processor import process_image_pencil, process_image_canny, process_image_anime2sketch
from modules.contour_optimizer import thin_contours_to_skeleton, remove_backtracking, apply_point_skipping, apply_jitter_correction
from modules.drawing_engine import start_drawing_method_1, start_drawing_method_2, start_drawing_method_3
from modules.ui_layout import build_main_layout
from modules.ui_components import create_slider, create_section
from modules.ui_state import normalize_preset

# Set appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Load custom font
FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
FONT_FILES = []
if os.path.exists(FONT_DIR):
    FONT_FILES = [f for f in os.listdir(FONT_DIR) if f.endswith(('.ttf', '.TTF', '.otf', '.OTF'))]
    
CUSTOM_FONT = None
if FONT_FILES:
    try:
        CUSTOM_FONT = os.path.join(FONT_DIR, FONT_FILES[0])
    except:
        pass

FONT_FAMILY = "Microsoft YaHei UI"


def get_app_version():
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            version = f.read().strip()
            return version or "0.0.0"
    except Exception:
        return "0.0.0"


class ModernDrawingApp:
    def __init__(self, root):
        self.root = root
        self.app_version = get_app_version()
        self.root.title(f"Heytea Painter v{self.app_version}")
        self.root.geometry("1600x950")
        
        self.file_path = None
        self.contours = None
        self.img_w = 0
        self.img_h = 0
        self.preset_file = "heytea_presets.json"
        
        self.preview_zoom = 1.0
        self.preview_original_img = None
        self.photo_image = None
        self.is_updating = False
        self.preview_worker = ThreadPoolExecutor(max_workers=1)
        self.preview_request_id = 0
        self.last_completed_signature = None
        self.preview_status_var = ctk.StringVar(value="状态：待机")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.setup_gui()
        self.load_presets(silent=True)
        self.on_method_change()
    
    def setup_gui(self):
        """创建现代化GUI界面"""
        layout = build_main_layout(
            self.root,
            FONT_FAMILY,
            self.zoom_in,
            self.zoom_out,
            self.reset_zoom,
            self.on_preview_mousewheel,
        )
        self.control_panel = layout["control_panel"]
        self.preview_canvas = layout["preview_canvas"]
        self.console_text = layout["console_text"]
        ctk.CTkLabel(self.control_panel, textvariable=self.preview_status_var, font=(FONT_FAMILY, 11)).pack(pady=(5, 0))
        
        self.create_controls()
    
    def log(self, message):
        """输出到控制台"""
        self.console_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.insert("end", f"[{timestamp}] {message}\n")
        self.console_text.see("end")
        self.console_text.configure(state="disabled")
        print(message)
    
    def create_controls(self):
        """创建控制面板"""
        # 标题
        title_label = ctk.CTkLabel(self.control_panel, text="Heytea Painter", 
                                   font=(FONT_FAMILY, 24, "bold"))
        title_label.pack(pady=20)
        
        # 1. 文件操作
        file_frame = create_section(self.control_panel, "文件操作", FONT_FAMILY)
        ctk.CTkButton(file_frame, text="加载图片", command=self.load_image, 
                     height=40, font=(FONT_FAMILY, 12)).pack(fill="x", padx=20, pady=5)
        
        # 2. 线条提取
        extract_frame = create_section(self.control_panel, "线条提取方法", FONT_FAMILY)
        
        self.extraction_method = ctk.CTkSegmentedButton(extract_frame, 
            values=["Pencil Sketch", "Canny", "Anime2Sketch"],
            command=self.on_method_change,
            font=(FONT_FAMILY, 11))
        self.extraction_method.set("Pencil Sketch")
        self.extraction_method.pack(fill="x", padx=20, pady=5)
        
        # 动态参数区
        self.params_container = ctk.CTkFrame(extract_frame, fg_color="transparent")
        self.params_container.pack(fill="x", padx=20, pady=10)
        
        # Pencil 参数
        self.pencil_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.sigma_s = self.create_modern_slider(self.pencil_params, "平滑度", 1, 200, 60, tooltip="控制线条平滑程度，值越大越平滑")
        self.sigma_r = self.create_modern_slider(self.pencil_params, "细节保留", 0.01, 1.0, 0.4, 0.01, tooltip="保留图像细节的强度")
        self.shade_factor = self.create_modern_slider(self.pencil_params, "阴影强度", 0.0, 1.0, 0.05, 0.01, tooltip="阴影的深度和强度")
        
        # Canny 参数
        self.canny_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.canny_blur = self.create_modern_slider(self.canny_params, "高斯模糊", 1, 20, 3, 1, tooltip="预处理模糊程度，减少噪点")
        self.canny_low = self.create_modern_slider(self.canny_params, "低阈值", 1, 500, 50, 1, tooltip="边缘检测下限，低于此值忽略")
        self.canny_high = self.create_modern_slider(self.canny_params, "高阈值", 1, 1000, 150, 1, tooltip="边缘检测上限，高于此值保留")
        
        # Anime2Sketch 参数
        self.anime_params = ctk.CTkFrame(self.params_container, fg_color="transparent")
        self.anime_threshold = self.create_modern_slider(self.anime_params, "二值化阈值", 50, 200, 127, 1, tooltip="黑白分界点，控制线条粗细")
        self.anime_morph_size = self.create_modern_slider(self.anime_params, "形态学核大小", 1, 5, 2, 1, tooltip="线条处理核大小，影响线条连续性")
        self.anime_morph_iter = self.create_modern_slider(self.anime_params, "形态学迭代", 1, 3, 1, 1, tooltip="形态学处理次数")
        self.anime_min_area = self.create_modern_slider(self.anime_params, "最小轮廓面积", 5, 100, 10, 1, tooltip="过滤小轮廓，减少噪点")
        
        adv_label = ctk.CTkLabel(self.anime_params, text="高级参数", font=(FONT_FAMILY, 11, "bold"))
        adv_label.pack(pady=5)
        
        self.anime_pre_blur = self.create_modern_slider(self.anime_params, "预处理模糊", 0, 9, 0, 1, tooltip="AI处理前的模糊强度")
        self.anime_edge_enhance = self.create_modern_slider(self.anime_params, "边缘增强", 0, 3.0, 0, 0.1, tooltip="增强边缘锐度")
        self.anime_sigmoid = self.create_modern_slider(self.anime_params, "模型敏感度", 0.3, 0.9, 0.5, 0.05, tooltip="AI模型的灵敏度")
        
        self.anime_invert = ctk.CTkCheckBox(self.anime_params, text="反转提取", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.anime_invert.pack(pady=2)
        
        self.anime_adaptive = ctk.CTkCheckBox(self.anime_params, text="自适应二值化", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.anime_adaptive.pack(pady=2)
        
        ctk.CTkLabel(self.anime_params, text="轮廓模式:", font=(FONT_FAMILY, 11)).pack(pady=2)
        self.anime_mode = ctk.CTkSegmentedButton(self.anime_params, 
            values=["外部轮廓", "所有轮廓", "骨架提取"],
            font=(FONT_FAMILY, 10))
        self.anime_mode.set("外部轮廓")
        self.anime_mode.pack(fill="x", pady=5)
        
        # 3. 通用优化
        optimize_frame = create_section(self.control_panel, "通用优化", FONT_FAMILY)
        
        self.simplify_eps = self.create_modern_slider(optimize_frame, "线条简化度 [全局]", 0.1, 5.0, 1.0, 0.1, tooltip="简化线条路径，减少点数")
        self.preview_thick = self.create_modern_slider(optimize_frame, "预览线条粗细 [预览]", 1, 20, 1, 1, tooltip="预览图中线条的粗细")
        self.spline_smooth = self.create_modern_slider(optimize_frame, "路径平滑度 [全局]", 0, 5000, 0, 1, tooltip="使用B样条平滑路径")
        self.jitter_correct = self.create_modern_slider(optimize_frame, "抖动修正强度 [全局]", 0, 10, 0, 1, tooltip="修正线条抖动，使线条更平滑")
        
        self.thin_contours = ctk.CTkCheckBox(optimize_frame, text="边缘细化（双线变单线）[全局]", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.thin_contours.pack(pady=5)
        
        self.skip_points = self.create_modern_slider(optimize_frame, "跳点加速 [全局]", 1, 5, 1, 1, tooltip="跳过部分点来加快绘画速度")
        
        # 4. 绘画模拟
        draw_frame = create_section(self.control_panel, "绘画模拟", FONT_FAMILY)
        
        self.draw_method = ctk.CTkSegmentedButton(draw_frame, 
            values=["短行程", "智能拖动", "仿真人"],
            font=(FONT_FAMILY, 11))
        self.draw_method.set("短行程")
        self.draw_method.pack(fill="x", padx=20, pady=5)
        
        self.stroke_len = self.create_modern_slider(draw_frame, "笔画长度 [方法1]", 5, 100, 15, 5, tooltip="每次绘制的点数（短行程模式）")
        self.min_drag = self.create_modern_slider(draw_frame, "最小拖动距离 [方法2]", 1, 20, 5, 1, tooltip="触发移动的最小距离（智能拖动）")
        self.draw_delay = self.create_modern_slider(draw_frame, "绘画延迟(ms) [全局]", 1, 100, 5, 1, tooltip="每个点之间的延迟时间")
        self.lift_pause = self.create_modern_slider(draw_frame, "换线停顿 [方法1/2]", 3, 15, 5, 1, tooltip="换线时的停顿时间")
        self.hand_shake = self.create_modern_slider(draw_frame, "手部抖动 [方法3]", 0, 5, 1, 1, tooltip="模拟手部抖动（仿真人）")
        self.think_pause = self.create_modern_slider(draw_frame, "思考停顿倍率 [方法3]", 1, 10, 3, 1, tooltip="转角处的思考停顿（仿真人）")
        self.corner_sharp = self.create_modern_slider(draw_frame, "转角锐利度 [方法3]", 0, 10, 5, 1, tooltip="转角锐利度：0=圆润平滑，10=极度锐利")
        
        # 5. 速度控制
        speed_frame = create_section(self.control_panel, "速度控制", FONT_FAMILY)
        self.speed_mult = self.create_modern_slider(speed_frame, "速度倍率 [全局]", 0.1, 5.0, 1.0, 0.1, tooltip="影响所有延迟参数的倍率")
        
        # 6. 功能按钮
        button_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        button_frame.pack(fill="x", pady=20)
        
        btn_row1 = ctk.CTkFrame(button_frame, fg_color="transparent")
        btn_row1.pack(fill="x", pady=5)
        
        ctk.CTkButton(btn_row1, text="保存预设", command=self.save_presets, 
                     height=35, font=(FONT_FAMILY, 11)).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(btn_row1, text="加载预设", command=self.load_presets, 
                     height=35, font=(FONT_FAMILY, 11)).pack(side="left", expand=True, fill="x", padx=2)
        
        ctk.CTkButton(button_frame, text="重置参数", command=self.reset_params, 
                     height=35, font=(FONT_FAMILY, 11)).pack(fill="x", pady=5)
        
        self.start_btn = ctk.CTkButton(button_frame, text="开始绘画", 
                                       command=self.start_drawing, 
                                       height=50, font=(FONT_FAMILY, 14, "bold"),
                                       fg_color="#2ecc71", hover_color="#27ae60",
                                       state="disabled")
        self.start_btn.pack(fill="x", pady=10)
    
    def create_modern_slider(self, parent, label, from_, to, default, resolution=None, tooltip=None):
        """创建现代化滑块"""
        return create_slider(
            parent=parent,
            label=label,
            from_=from_,
            to=to,
            default=default,
            font_family=FONT_FAMILY,
            on_change=self.update_preview_throttled,
            is_updating_getter=lambda: self.is_updating,
            resolution=resolution,
        )
    
    def create_tooltip(self, widget, text):
        """创建鼠标悬停提示"""
        # 禁用 tooltip 功能以避免卡住的 BUG
        pass
    
    def on_method_change(self, value=None):
        """切换提取方法"""
        for widget in self.params_container.winfo_children():
            widget.pack_forget()
        
        method = self.extraction_method.get()
        if method == "Pencil Sketch":
            self.pencil_params.pack(fill="x")
        elif method == "Canny":
            self.canny_params.pack(fill="x")
        elif method == "Anime2Sketch":
            self.anime_params.pack(fill="x")
        
        if value is not None:
            self.update_preview()
    
    def load_image(self):
        """加载图片"""
        # 设置默认目录为项目的 images 文件夹（如果存在），否则使用用户的文档目录
        default_dir = os.path.join(os.path.dirname(__file__), "images")
        if not os.path.exists(default_dir):
            # 如果项目 images 文件夹不存在，使用用户主目录
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
            # 显示完整路径，方便用户确认
            if len(file_path) > 60:
                display_path = "..." + file_path[-57:]
            else:
                display_path = file_path
            self.log(f"已加载图片: {display_path}")
            
            # 检查原始尺寸并给出提示
            try:
                with open(file_path, 'rb') as f:
                    img_array = np.frombuffer(f.read(), np.uint8)
                test_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if test_img is not None:
                    h, w = test_img.shape[:2]
                    self.log(f"原始尺寸: {w}x{h} 像素")
                    
                    # 警告信息
                    if max(h, w) > 4096:
                        self.log("⚠️ 图片超大，已预缩放到 4096px")
                        self.log("   绘画时将根据画布大小进一步调整")
                    elif max(h, w) < 256:
                        self.log("⚠️ 图片极小，已预放大")
                    else:
                        self.log("   提示: 绘画时将根据画布大小自动调整")
                    
                    # 计算总像素
                    total_pixels = w * h
                    if total_pixels > 10000000:  # 超过 10MP
                        self.log(f"   总像素: {total_pixels/1000000:.1f}MP")
            except Exception as e:
                self.log(f"   无法读取图片信息: {e}")
            
            self.update_preview()
            self.start_btn.configure(state="normal")
    
    def update_preview_throttled(self):
        """延迟更新，防止画面撕裂"""
        if hasattr(self, '_preview_timer'):
            self.root.after_cancel(self._preview_timer)
        self._preview_timer = self.root.after(250, self.update_preview)

    def _collect_preview_params(self):
        method = self.extraction_method.get()
        simplify = self.simplify_eps.get()
        spline = self.spline_smooth.get()
        thick = self.preview_thick.get()
        blur = int(self.canny_blur.get())
        if blur % 2 == 0:
            blur += 1
        mode_map = {"外部轮廓": "外部轮廓 (快速)", "所有轮廓": "所有轮廓 (详细)", "骨架提取": "骨架提取 (推荐)"}
        return {
            "method": method,
            "simplify": simplify,
            "spline": spline,
            "thick": thick,
            "sigma_s": self.sigma_s.get(),
            "sigma_r": self.sigma_r.get(),
            "shade_factor": self.shade_factor.get(),
            "canny_blur": blur,
            "canny_low": self.canny_low.get(),
            "canny_high": self.canny_high.get(),
            "anime_threshold": int(self.anime_threshold.get()),
            "anime_morph_size": int(self.anime_morph_size.get()),
            "anime_morph_iter": int(self.anime_morph_iter.get()),
            "anime_min_area": int(self.anime_min_area.get()),
            "anime_mode": mode_map[self.anime_mode.get()],
            "anime_pre_blur": int(self.anime_pre_blur.get()),
            "anime_edge_enhance": self.anime_edge_enhance.get(),
            "anime_sigmoid": self.anime_sigmoid.get(),
            "anime_invert": self.anime_invert.get() == 1,
            "anime_adaptive": self.anime_adaptive.get() == 1,
            "jitter": int(self.jitter_correct.get()),
            "thin_contours": self.thin_contours.get() == 1,
            "skip": int(self.skip_points.get()),
        }

    def _build_preview_signature(self, params):
        mtime = 0
        try:
            mtime = os.path.getmtime(self.file_path) if self.file_path else 0
        except OSError:
            pass
        tracked = (
            self.file_path,
            mtime,
            params["method"],
            round(params["simplify"], 3),
            round(params["spline"], 3),
            round(params["thick"], 3),
            round(params["sigma_s"], 3),
            round(params["sigma_r"], 3),
            round(params["shade_factor"], 3),
            params["canny_blur"],
            round(params["canny_low"], 3),
            round(params["canny_high"], 3),
            params["anime_threshold"],
            params["anime_morph_size"],
            params["anime_morph_iter"],
            params["anime_min_area"],
            params["anime_mode"],
            params["anime_pre_blur"],
            round(params["anime_edge_enhance"], 3),
            round(params["anime_sigmoid"], 3),
            params["anime_invert"],
            params["anime_adaptive"],
            params["jitter"],
            params["thin_contours"],
            params["skip"],
        )
        return tracked

    def _process_preview_request(self, file_path, params):
        method = params["method"]
        simplify = params["simplify"]
        spline = params["spline"]
        thick = params["thick"]

        if method == "Pencil Sketch":
            preview_img, contours, img_w, img_h = process_image_pencil(
                file_path,
                params["sigma_s"],
                params["sigma_r"],
                params["shade_factor"],
                simplify,
                spline,
                thick,
            )
        elif method == "Canny":
            preview_img, contours, img_w, img_h = process_image_canny(
                file_path,
                params["canny_blur"],
                params["canny_low"],
                params["canny_high"],
                simplify,
                spline,
                thick,
            )
        else:
            preview_img, contours, img_w, img_h = process_image_anime2sketch(
                file_path,
                simplify,
                spline,
                thick,
                params["anime_threshold"],
                params["anime_morph_size"],
                params["anime_morph_iter"],
                params["anime_min_area"],
                params["anime_mode"],
                params["anime_pre_blur"],
                params["anime_edge_enhance"],
                params["anime_sigmoid"],
                params["anime_invert"],
                params["anime_adaptive"],
            )

        if preview_img is None:
            return {"preview_img": None, "contours": [], "img_w": 0, "img_h": 0, "points": 0}

        if contours and len(contours) > 0:
            contours = remove_backtracking(contours)

            if params["jitter"] > 0:
                contours = apply_jitter_correction(contours, params["jitter"])

            redraw_required = False
            if params["thin_contours"]:
                contours = thin_contours_to_skeleton(contours, preview_img.shape)
                redraw_required = True

            if params["skip"] > 1:
                contours = apply_point_skipping(contours, params["skip"])
                redraw_required = True

            if redraw_required:
                preview_img = cv2.cvtColor(cv2.cvtColor(preview_img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                for contour in contours:
                    cv2.polylines(preview_img, [contour], False, (0, 0, 255), int(thick), lineType=cv2.LINE_AA)

        points = 0
        if contours:
            for contour in contours:
                try:
                    points += len(contour)
                except Exception:
                    pass
        return {"preview_img": preview_img, "contours": contours or [], "img_w": img_w, "img_h": img_h, "points": points}
    
    def update_preview(self):
        """更新预览"""
        if not self.file_path:
            return

        params = self._collect_preview_params()
        signature = self._build_preview_signature(params)
        if signature == self.last_completed_signature and self.preview_original_img is not None:
            self.preview_status_var.set("状态：参数未变化")
            return

        self.is_updating = True
        self.preview_status_var.set("状态：正在处理预览...")
        self.preview_request_id += 1
        request_id = self.preview_request_id
        file_path = self.file_path

        def process():
            return self._process_preview_request(file_path, params)

        future = self.preview_worker.submit(process)

        def on_done():
            if request_id != self.preview_request_id:
                return
            self.is_updating = False
            try:
                result = future.result()
            except Exception as e:
                self.preview_status_var.set("状态：预览失败")
                self.log(f"预览失败: {e}")
                return

            preview_img = result["preview_img"]
            contours = result["contours"]
            if preview_img is None:
                self.preview_status_var.set("状态：未生成预览")
                return

            self.contours = contours
            self.img_w = result["img_w"]
            self.img_h = result["img_h"]

            if self.preview_original_img is not None:
                try:
                    self.preview_original_img.close()
                except Exception:
                    pass

            img_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
            self.preview_original_img = Image.fromarray(img_rgb)
            self.preview_zoom = 1.0
            self.display_preview()
            self.last_completed_signature = signature
            self.preview_status_var.set(f"状态：完成（路径 {len(contours)}，点数 {result['points']}）")
            self.log(f"预览更新完成，检测到 {len(contours)} 条路径")

        self.root.after(10, self._poll_preview_future, future, on_done)

    def _poll_preview_future(self, future, callback):
        if future.done():
            callback()
            return
        self.root.after(25, self._poll_preview_future, future, callback)
    
    def display_preview(self):
        """显示预览"""
        if self.preview_original_img is None:
            return
        
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        
        if canvas_w < 50 or canvas_h < 50:
            canvas_w, canvas_h = 800, 600
        
        img = self.preview_original_img.copy()
        img_w, img_h = img.size
        
        scale = min(canvas_w / img_w, canvas_h / img_h) * self.preview_zoom
        
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        if new_w > 0 and new_h > 0:
            img = img.resize((new_w, new_h), Image.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(img)
            
            self.preview_canvas.delete("all")
            x = (canvas_w - new_w) // 2
            y = (canvas_h - new_h) // 2
            self.preview_canvas.create_image(x, y, anchor="nw", image=self.photo_image)
    
    def on_preview_mousewheel(self, event):
        """滚轮缩放"""
        if self.preview_original_img is None:
            return
        
        if event.delta > 0:
            self.preview_zoom *= 1.1
        else:
            self.preview_zoom /= 1.1
        
        self.preview_zoom = max(0.1, min(self.preview_zoom, 5.0))
        self.display_preview()
    
    def zoom_in(self):
        """放大"""
        if self.preview_original_img:
            self.preview_zoom *= 1.2
            self.preview_zoom = min(self.preview_zoom, 5.0)
            self.log(f"预览已放大，当前缩放: {self.preview_zoom:.1f}x")
            self.display_preview()
    
    def zoom_out(self):
        """缩小"""
        if self.preview_original_img:
            self.preview_zoom /= 1.2
            self.preview_zoom = max(self.preview_zoom, 0.1)
            self.log(f"预览已缩小，当前缩放: {self.preview_zoom:.1f}x")
            self.display_preview()
    
    def reset_zoom(self):
        """重置缩放"""
        if self.preview_original_img:
            self.preview_zoom = 1.0
            self.log("预览缩放已重置")
            self.display_preview()
    
    def start_drawing(self):
        """开始绘画"""
        if not self.contours or len(self.contours) == 0:
            self.log("错误: 没有可绘制的轮廓")
            return
        
        # 检查轮廓点数
        total_points = 0
        for contour in self.contours:
            points = contour.squeeze()
            if len(points.shape) > 1:
                total_points += len(points)
        
        self.log(f"绘画数据: {len(self.contours)} 条路径, {total_points} 个点")
        
        # 警告
        if total_points > 50000:
            self.log("⚠️ 点数过多！建议调整参数：")
            self.log("   1. 增加【线条简化度】到 2-3")
            self.log("   2. 启用【跳点加速】到 2-3")
            self.log("   3. 减小【预览线条粗细】")
        
        # 禁用按钮
        self.start_btn.configure(state="disabled")
        
        # 最小化 GUI
        self.root.iconify()
        self.log("GUI已最小化...")
        
        # 确保终端窗口获得焦点
        import ctypes
        import time
        try:
            # 获取控制台窗口句柄
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            
            # 获取当前进程的控制台窗口
            console_hwnd = kernel32.GetConsoleWindow()
            
            if console_hwnd:
                # 显示并激活控制台窗口
                user32.ShowWindow(console_hwnd, 9)  # SW_RESTORE = 9
                user32.SetForegroundWindow(console_hwnd)
                self.log("已激活终端窗口")
            else:
                self.log("提示: 请手动切换到终端窗口查看绘画进度")
        except Exception as e:
            self.log(f"无法激活终端窗口: {e}")
            self.log("提示: 请手动切换到终端窗口查看绘画进度")
        
        time.sleep(2)
        
        method = self.draw_method.get()
        speed = self.speed_mult.get()
        
        if method == "短行程":
            args = (self, self.contours, self.img_w, self.img_h,
                   int(self.stroke_len.get()),
                   self.draw_delay.get() / 1000.0 / speed,
                   self.lift_pause.get() / 100.0 / speed,
                   speed)
            threading.Thread(target=start_drawing_method_1, args=args, daemon=True).start()
        
        elif method == "智能拖动":
            args = (self, self.contours, self.img_w, self.img_h,
                   int(self.min_drag.get()),
                   self.draw_delay.get() / 1000.0 / speed,
                   speed)
            threading.Thread(target=start_drawing_method_2, args=args, daemon=True).start()
        
        elif method == "仿真人":
            args = (self, self.contours, self.img_w, self.img_h,
                   self.draw_delay.get() / 1000.0 / speed,
                   self.lift_pause.get() / 100.0 / speed,
                   int(self.hand_shake.get()),
                   self.think_pause.get(),
                   int(self.corner_sharp.get()),
                   speed)
            threading.Thread(target=start_drawing_method_3, args=args, daemon=True).start()
    
    def on_drawing_complete(self):
        """绘画完成"""
        def restore():
            self.log("绘画完成，恢复GUI")
            self.start_btn.configure(state="normal")
            self.root.deiconify()
        self.root.after(0, restore)
    
    def get_all_values(self):
        """获取所有参数值"""
        mode_map = {"外部轮廓": "外部轮廓 (快速)", "所有轮廓": "所有轮廓 (详细)", "骨架提取": "骨架提取 (推荐)"}
        method_map = {"短行程": "方法 1: 短行程 (推荐)", "智能拖动": "方法 2: 智能拖动 (蜘蛛网?)", "仿真人": "方法 3: 仿真人绘画 🎨"}
        extract_map = {"Pencil Sketch": "Pencil Sketch (V19)", "Canny": "Canny 边缘检测", "Anime2Sketch": "Anime2Sketch"}
        
        return {
            "extraction_method": extract_map[self.extraction_method.get()],
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
            "drawing_method": method_map[self.draw_method.get()],
            "anime_threshold": self.anime_threshold.get(),
            "anime_morph_size": self.anime_morph_size.get(),
            "anime_morph_iter": self.anime_morph_iter.get(),
            "anime_min_area": self.anime_min_area.get(),
            "anime_contour_mode": mode_map[self.anime_mode.get()],
            "anime_pre_blur": self.anime_pre_blur.get(),
            "anime_edge_enhance": self.anime_edge_enhance.get(),
            "anime_sigmoid_threshold": self.anime_sigmoid.get(),
            "anime_invert": self.anime_invert.get() == 1,
            "anime_adaptive": self.anime_adaptive.get() == 1,
            "thin_contours": self.thin_contours.get() == 1,
            "skip_points": self.skip_points.get(),
            "hand_shake": self.hand_shake.get(),
            "think_pause": self.think_pause.get(),
            "corner_sharpness": self.corner_sharp.get(),
            "lift_pause": self.lift_pause.get(),
            "speed_multiplier": self.speed_mult.get()
        }
    
    def set_all_values(self, values):
        """设置所有参数值"""
        values = normalize_preset(values)
        extract_map = {"Pencil Sketch (V19)": "Pencil Sketch", "Canny 边缘检测": "Canny", "Anime2Sketch": "Anime2Sketch"}
        method_map = {"方法 1: 短行程 (推荐)": "短行程", "方法 2: 智能拖动 (蜘蛛网?)": "智能拖动", "方法 3: 仿真人绘画 🎨": "仿真人"}
        mode_map = {"外部轮廓 (快速)": "外部轮廓", "所有轮廓 (详细)": "所有轮廓", "骨架提取 (推荐)": "骨架提取"}
        
        self.extraction_method.set(extract_map.get(values.get("extraction_method", "Pencil Sketch (V19)"), "Pencil Sketch"))
        self.sigma_s.set(values.get("sigma_s", 60))
        self.sigma_r.set(values.get("sigma_r", 0.4))
        self.shade_factor.set(values.get("shade_factor", 0.05))
        self.canny_blur.set(values.get("canny_blur", 3))
        self.canny_low.set(values.get("canny_low", 50))
        self.canny_high.set(values.get("canny_high", 150))
        self.simplify_eps.set(values.get("simplify_epsilon", 1.0))
        self.preview_thick.set(values.get("preview_thickness", 1))
        self.spline_smooth.set(values.get("spline_smoothness", 0))
        self.jitter_correct.set(values.get("jitter_correction", 0))
        self.stroke_len.set(values.get("stroke_len", 15))
        self.min_drag.set(values.get("min_drag_dist", 5))
        self.draw_delay.set(values.get("draw_delay", 5))
        self.draw_method.set(method_map.get(values.get("drawing_method", "方法 1: 短行程 (推荐)"), "短行程"))
        self.anime_threshold.set(values.get("anime_threshold", 127))
        self.anime_morph_size.set(values.get("anime_morph_size", 2))
        self.anime_morph_iter.set(values.get("anime_morph_iter", 1))
        self.anime_min_area.set(values.get("anime_min_area", 10))
        self.anime_mode.set(mode_map.get(values.get("anime_contour_mode", "外部轮廓 (快速)"), "外部轮廓"))
        self.anime_pre_blur.set(values.get("anime_pre_blur", 0))
        self.anime_edge_enhance.set(values.get("anime_edge_enhance", 0))
        self.anime_sigmoid.set(values.get("anime_sigmoid_threshold", 0.5))
        
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
        
        self.skip_points.set(values.get("skip_points", 1))
        self.hand_shake.set(values.get("hand_shake", 1))
        self.think_pause.set(values.get("think_pause", 3))
        self.corner_sharp.set(values.get("corner_sharpness", 5))
        self.lift_pause.set(values.get("lift_pause", 5))
        self.speed_mult.set(values.get("speed_multiplier", 1.0))
    
    def save_presets(self):
        """保存预设"""
        values = normalize_preset(self.get_all_values())
        try:
            with open(self.preset_file, 'w', encoding='utf-8') as f:
                json.dump(values, f, indent=4, ensure_ascii=False)
            self.log(f"预设已保存: {self.preset_file}")
        except Exception as e:
            self.log(f"保存失败: {e}")
    
    def load_presets(self, silent=False):
        """加载预设"""
        if not os.path.exists(self.preset_file):
            if not silent:
                self.log(f"预设文件不存在: {self.preset_file}")
            return
        
        try:
            with open(self.preset_file, 'r', encoding='utf-8') as f:
                values = json.load(f)
            values = normalize_preset(values)
            self.set_all_values(values)
            if not silent:
                self.log(f"预设已加载: {self.preset_file}")
        except Exception as e:
            if not silent:
                self.log(f"加载失败，已回退默认值: {e}")
            self.set_all_values({})
    
    def reset_params(self):
        """重置参数"""
        self.log("参数已重置为默认值")
        self.set_all_values({})
        self.on_method_change()
        if self.file_path:
            self.update_preview()

    def on_close(self):
        try:
            self.preview_worker.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = ctk.CTk()
    app = ModernDrawingApp(root)
    root.mainloop()
