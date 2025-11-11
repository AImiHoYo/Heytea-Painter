"""
Heytea Painter - Modern AI Drawing Tool
Using CustomTkinter for modern UI
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageFont
import threading
import json
import cv2
import numpy as np
from datetime import datetime

from modules.image_processor import process_image_pencil, process_image_canny, process_image_anime2sketch
from modules.contour_optimizer import thin_contours_to_skeleton, remove_backtracking, apply_point_skipping, apply_jitter_correction
from modules.drawing_engine import start_drawing_method_1, start_drawing_method_2, start_drawing_method_3

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


class ModernDrawingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Heytea Painter")
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
        
        self.setup_gui()
        self.load_presets(silent=True)
        self.on_method_change()
    
    def setup_gui(self):
        """创建现代化GUI界面"""
        # 主容器
        main_container = ctk.CTkFrame(self.root)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 左右分割
        left_right_container = ctk.CTkFrame(main_container, fg_color="transparent")
        left_right_container.pack(fill="both", expand=True)
        
        # 左侧控制面板
        self.control_panel = ctk.CTkScrollableFrame(left_right_container, width=400, corner_radius=10)
        self.control_panel.pack(side="left", fill="y", padx=(0, 10))
        
        # 右侧容器
        right_container = ctk.CTkFrame(left_right_container, fg_color="transparent")
        right_container.pack(side="right", fill="both", expand=True)
        
        # 右上：预览区域
        preview_frame = ctk.CTkFrame(right_container, corner_radius=10)
        preview_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # 预览标题栏
        preview_header = ctk.CTkFrame(preview_frame, height=50, corner_radius=0)
        preview_header.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(preview_header, text="预览区域", font=(FONT_FAMILY, 16, "bold")).pack(side="left", padx=20, pady=10)
        
        zoom_frame = ctk.CTkFrame(preview_header, fg_color="transparent")
        zoom_frame.pack(side="right", padx=20)
        
        ctk.CTkButton(zoom_frame, text="放大", width=50, command=self.zoom_in, font=(FONT_FAMILY, 11)).pack(side="left", padx=2)
        ctk.CTkButton(zoom_frame, text="缩小", width=50, command=self.zoom_out, font=(FONT_FAMILY, 11)).pack(side="left", padx=2)
        ctk.CTkButton(zoom_frame, text="重置", width=50, command=self.reset_zoom, font=(FONT_FAMILY, 11)).pack(side="left", padx=2)
        
        # 预览画布
        self.preview_canvas = ctk.CTkCanvas(preview_frame, bg="#1a1a1a", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.preview_canvas.bind("<MouseWheel>", self.on_preview_mousewheel)
        
        # 右下：控制台
        console_frame = ctk.CTkFrame(right_container, corner_radius=10)
        console_frame.pack(fill="x", pady=0)
        
        ctk.CTkLabel(console_frame, text="控制台输出", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", padx=15, pady=(10, 5))
        
        self.console_text = ctk.CTkTextbox(console_frame, height=150, font=(FONT_FAMILY, 10))
        self.console_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.console_text.configure(state="disabled")
        
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
        file_frame = ctk.CTkFrame(self.control_panel, corner_radius=10)
        file_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(file_frame, text="文件操作", font=(FONT_FAMILY, 14, "bold")).pack(pady=10)
        ctk.CTkButton(file_frame, text="加载图片", command=self.load_image, 
                     height=40, font=(FONT_FAMILY, 12)).pack(fill="x", padx=20, pady=5)
        
        # 2. 线条提取
        extract_frame = ctk.CTkFrame(self.control_panel, corner_radius=10)
        extract_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(extract_frame, text="线条提取方法", font=(FONT_FAMILY, 14, "bold")).pack(pady=10)
        
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
        optimize_frame = ctk.CTkFrame(self.control_panel, corner_radius=10)
        optimize_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(optimize_frame, text="通用优化", font=(FONT_FAMILY, 14, "bold")).pack(pady=10)
        
        self.simplify_eps = self.create_modern_slider(optimize_frame, "线条简化度", 0.1, 5.0, 1.0, 0.1, tooltip="简化线条路径，减少点数")
        self.preview_thick = self.create_modern_slider(optimize_frame, "预览线条粗细", 1, 20, 1, 1, tooltip="预览图中线条的粗细")
        self.spline_smooth = self.create_modern_slider(optimize_frame, "路径平滑度", 0, 5000, 0, 1, tooltip="使用B样条平滑路径")
        self.jitter_correct = self.create_modern_slider(optimize_frame, "抖动修正强度", 0, 10, 0, 1, tooltip="修正线条抖动，使线条更平滑")
        
        self.thin_contours = ctk.CTkCheckBox(optimize_frame, text="边缘细化（双线变单线）", command=self.update_preview, font=(FONT_FAMILY, 11))
        self.thin_contours.pack(pady=5)
        
        self.skip_points = self.create_modern_slider(optimize_frame, "跳点加速", 1, 5, 1, 1, tooltip="跳过部分点来加快绘画速度")
        
        # 4. 绘画模拟
        draw_frame = ctk.CTkFrame(self.control_panel, corner_radius=10)
        draw_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(draw_frame, text="绘画模拟", font=(FONT_FAMILY, 14, "bold")).pack(pady=10)
        
        self.draw_method = ctk.CTkSegmentedButton(draw_frame, 
            values=["短行程", "智能拖动", "仿真人"],
            font=(FONT_FAMILY, 11))
        self.draw_method.set("短行程")
        self.draw_method.pack(fill="x", padx=20, pady=5)
        
        self.stroke_len = self.create_modern_slider(draw_frame, "笔画长度", 5, 100, 15, 5, tooltip="每次绘制的点数（短行程模式）")
        self.min_drag = self.create_modern_slider(draw_frame, "最小拖动距离", 1, 20, 5, 1, tooltip="触发移动的最小距离（智能拖动）")
        self.draw_delay = self.create_modern_slider(draw_frame, "绘画延迟(ms)", 1, 100, 5, 1, tooltip="每个点之间的延迟时间")
        self.lift_pause = self.create_modern_slider(draw_frame, "换线停顿", 3, 15, 5, 1, tooltip="换线时的停顿时间")
        self.hand_shake = self.create_modern_slider(draw_frame, "手部抖动", 0, 5, 1, 1, tooltip="模拟手部抖动（仿真人）")
        self.think_pause = self.create_modern_slider(draw_frame, "思考停顿倍率", 1, 10, 3, 1, tooltip="转角处的思考停顿（仿真人）")
        
        # 5. 速度控制
        speed_frame = ctk.CTkFrame(self.control_panel, corner_radius=10)
        speed_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(speed_frame, text="速度控制", font=(FONT_FAMILY, 14, "bold")).pack(pady=10)
        self.speed_mult = self.create_modern_slider(speed_frame, "速度倍率", 0.1, 5.0, 1.0, 0.1, tooltip="全局速度调节，影响所有延迟")
        
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
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)
        
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
        
        label_widget = ctk.CTkLabel(label_frame, text=label, font=(FONT_FAMILY, 11))
        label_widget.pack(side="left")
        
        # 添加提示信息
        if tooltip:
            self.create_tooltip(label_widget, tooltip)
        
        var = ctk.DoubleVar(value=default)
        value_label = ctk.CTkLabel(label_frame, text=fmt.format(default), 
                                   font=(FONT_FAMILY, 11, "bold"),
                                   text_color="#3498db")
        value_label.pack(side="right")
        
        def update_label(*args):
            if not self.is_updating:
                value_label.configure(text=fmt.format(var.get()))
        
        var.trace_add('write', update_label)
        
        slider = ctk.CTkSlider(frame, from_=from_, to=to, variable=var, 
                              command=lambda v: self.update_preview_throttled())
        slider.pack(fill="x", pady=2)
        
        return var
    
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
            self.update_preview()
            self.start_btn.configure(state="normal")
    
    def update_preview_throttled(self):
        """延迟更新，防止画面撕裂"""
        if self.is_updating:
            return
        if hasattr(self, '_preview_timer'):
            self.root.after_cancel(self._preview_timer)
        self._preview_timer = self.root.after(500, self.update_preview)
    
    def update_preview(self):
        """更新预览"""
        if not self.file_path or self.is_updating:
            return
        
        self.is_updating = True
        
        method = self.extraction_method.get()
        preview_img, contours, img_w, img_h = None, None, 0, 0
        
        simplify = self.simplify_eps.get()
        spline = self.spline_smooth.get()
        thick = self.preview_thick.get()
        
        try:
            if method == "Pencil Sketch":
                preview_img, contours, img_w, img_h = process_image_pencil(
                    self.file_path, self.sigma_s.get(), self.sigma_r.get(), 
                    self.shade_factor.get(), simplify, spline, thick)
            
            elif method == "Canny":
                blur = int(self.canny_blur.get())
                if blur % 2 == 0:
                    blur += 1
                preview_img, contours, img_w, img_h = process_image_canny(
                    self.file_path, blur, self.canny_low.get(), 
                    self.canny_high.get(), simplify, spline, thick)
            
            elif method == "Anime2Sketch":
                mode_map = {"外部轮廓": "外部轮廓 (快速)", "所有轮廓": "所有轮廓 (详细)", "骨架提取": "骨架提取 (推荐)"}
                preview_img, contours, img_w, img_h = process_image_anime2sketch(
                    self.file_path, simplify, spline, thick,
                    int(self.anime_threshold.get()), int(self.anime_morph_size.get()),
                    int(self.anime_morph_iter.get()), int(self.anime_min_area.get()),
                    mode_map[self.anime_mode.get()], int(self.anime_pre_blur.get()),
                    self.anime_edge_enhance.get(), self.anime_sigmoid.get(),
                    self.anime_invert.get() == 1, self.anime_adaptive.get() == 1)
        
        except Exception as e:
            self.log(f"预览失败: {e}")
            self.is_updating = False
            return
        
        if preview_img is None:
            self.is_updating = False
            return
        
        # 优化
        if contours and len(contours) > 0:
            contours = remove_backtracking(contours)
            
            jitter = int(self.jitter_correct.get())
            if jitter > 0:
                contours = apply_jitter_correction(contours, jitter)
            
            if self.thin_contours.get() == 1:
                contours = thin_contours_to_skeleton(contours, preview_img.shape)
                preview_img = cv2.cvtColor(cv2.cvtColor(preview_img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                for contour in contours:
                    cv2.polylines(preview_img, [contour], False, (0, 0, 255), int(thick), lineType=cv2.LINE_AA)
            
            skip = int(self.skip_points.get())
            if skip > 1:
                contours = apply_point_skipping(contours, skip)
                preview_img = cv2.cvtColor(cv2.cvtColor(preview_img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                for contour in contours:
                    cv2.polylines(preview_img, [contour], False, (0, 0, 255), int(thick), lineType=cv2.LINE_AA)
        
        self.contours = contours
        self.img_w = img_w
        self.img_h = img_h
        
        img_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
        self.preview_original_img = Image.fromarray(img_rgb)
        self.preview_zoom = 1.0
        self.display_preview()
        self.log(f"预览更新完成，检测到 {len(contours)} 条路径")
        self.is_updating = False
    
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
        
        self.root.iconify()
        self.log("GUI已最小化，3秒后开始绘画...")
        import time
        time.sleep(3)
        
        self.start_btn.configure(state="disabled")
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
            "lift_pause": self.lift_pause.get(),
            "speed_multiplier": self.speed_mult.get()
        }
    
    def set_all_values(self, values):
        """设置所有参数值"""
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
        self.lift_pause.set(values.get("lift_pause", 5))
        self.speed_mult.set(values.get("speed_multiplier", 1.0))
    
    def save_presets(self):
        """保存预设"""
        values = self.get_all_values()
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
            self.set_all_values(values)
            if not silent:
                self.log(f"预设已加载: {self.preset_file}")
        except Exception as e:
            if not silent:
                self.log(f"加载失败: {e}")
    
    def reset_params(self):
        """重置参数"""
        self.log("参数已重置为默认值")
        self.set_all_values({})
        self.on_method_change()
        if self.file_path:
            self.update_preview()


if __name__ == "__main__":
    root = ctk.CTk()
    app = ModernDrawingApp(root)
    root.mainloop()
