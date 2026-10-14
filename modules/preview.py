"""预览：提取结果仍在图像空间显示，与落笔前的画布精简分开。

Anime2Sketch / LineartAnime 对齐 Qt：边图按缓存键复用，滑条拖动只重跑轮廓。
"""

import os

import cv2
from PIL import Image, ImageTk

from modules.app_logger import log_debug, log_error, log_info
from modules.cache_stats import EdgeCacheStats
from modules.contour_optimizer import (
    apply_jitter_correction,
    apply_point_skipping,
    expand_taper_paths,
    remove_backtracking,
    thin_contours_to_skeleton,
)
from modules.path_planner import draw_chunk_grid
from modules.image_processor import (
    LINEART_ANIME_PATH,
    contours_from_anime_pack,
    contours_from_lineart_pack,
    get_user_hint,
    infer_anime2sketch_edge_map,
    infer_lineart_anime_edge_map,
    process_image_canny,
    process_image_pencil,
)
from modules.settings_store import ANIME_MODE_TO_PROCESSOR


def _file_stamp(path):
    try:
        st = os.stat(path)
        return (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return (path, 0, 0)


def _infer_cache_key(method, file_path, sigmoid=None, detect=None, invert=None):
    stamp = _file_stamp(file_path)
    if method == "Anime2Sketch":
        return (method, stamp, float(sigmoid))
    if method == "LineartAnime":
        return (method, stamp, int(detect), bool(invert))
    return None


class PreviewMixin:
    def update_preview_throttled(self):
        """延迟更新，防止画面撕裂"""
        if self.is_updating:
            return
        if hasattr(self, "_preview_timer"):
            self.root.after_cancel(self._preview_timer)
        self._preview_timer = self.root.after(500, self.update_preview)

    def _alert_model_missing(self, hint):
        """日志 + 弹窗，缺模型时更醒目。"""
        text = str(hint or "").strip()
        if not text:
            return
        if getattr(self, "_last_model_alert", None) == text:
            self.log(text)
            return
        self._last_model_alert = text
        self.log(text)
        try:
            from tkinter import messagebox
            messagebox.showwarning("模型未就绪", text, parent=getattr(self, "root", None))
        except Exception:
            pass

    def _ensure_cache_stats(self):
        """边图缓存命中统计（命中率日志）。"""
        if not isinstance(getattr(self, "_edge_cache_stats", None), EdgeCacheStats):
            self._edge_cache_stats = EdgeCacheStats()
        return self._edge_cache_stats

    def clear_edge_cache(self):
        """强制重推理：清空边图缓存，下次预览重新跑网络。"""
        self._edge_cache = None
        log_info("已清空边图缓存（强制重推理）")

    def _get_edge_pack(self, method, file_path, **infer_kw):
        """复用边图；缓存未命中才推理。命中/未命中都计入命中率日志。"""
        stats = self._ensure_cache_stats()
        if method == "Anime2Sketch":
            key = _infer_cache_key(method, file_path, sigmoid=infer_kw.get("sigmoid"))
        else:
            key = _infer_cache_key(
                method, file_path,
                detect=infer_kw.get("detect"),
                invert=infer_kw.get("invert"),
            )
        cache = getattr(self, "_edge_cache", None)
        if cache and cache.get("key") == key and cache.get("pack") is not None:
            pack = cache["pack"]
            if "error_img" not in pack:
                stats.record_hit(method)
                return pack
        stats.record_miss(method)
        if method == "Anime2Sketch":
            pack = infer_anime2sketch_edge_map(file_path, infer_kw.get("sigmoid", 0.5))
        else:
            pack = infer_lineart_anime_edge_map(
                file_path,
                detect_resolution=infer_kw.get("detect", 512),
                invert=infer_kw.get("invert", True),
            )
        if pack is not None and "error_img" not in pack:
            self._edge_cache = {"key": key, "pack": pack}
        else:
            self._edge_cache = None
        return pack

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
                pack = self._get_edge_pack(
                    method, self.file_path, sigmoid=self.anime_sigmoid.get()
                )
                if pack is None:
                    preview_img, contours, img_w, img_h = None, None, 0, 0
                elif "error_img" in pack:
                    preview_img = pack["error_img"]
                    contours = pack.get("contours", [])
                    img_w, img_h = pack.get("original_w", 500), pack.get("original_h", 300)
                else:
                    processor_mode = ANIME_MODE_TO_PROCESSOR.get(
                        self.anime_mode.get(), "外部轮廓 (快速)"
                    )
                    preview_img, contours, img_w, img_h = contours_from_anime_pack(
                        pack, simplify, spline, thick,
                        int(self.anime_threshold.get()), int(self.anime_morph_size.get()),
                        int(self.anime_morph_iter.get()), int(self.anime_min_area.get()),
                        processor_mode, int(self.anime_pre_blur.get()),
                        self.anime_edge_enhance.get(),
                        self.anime_invert.get() == 1, self.anime_adaptive.get() == 1,
                    )

            elif method == "LineartAnime":
                if getattr(self, "log", None) and not os.path.isfile(LINEART_ANIME_PATH):
                    self.log("首次使用 LineartAnime，正在检查/下载权重…")
                pack = self._get_edge_pack(
                    method, self.file_path,
                    detect=int(self.lineart_detect.get()),
                    invert=self.lineart_invert.get() == 1,
                )
                if pack is None:
                    preview_img, contours, img_w, img_h = None, None, 0, 0
                elif "error_img" in pack:
                    preview_img = pack["error_img"]
                    contours = pack.get("contours", [])
                    img_w, img_h = pack.get("original_w", 500), pack.get("original_h", 300)
                else:
                    processor_mode = ANIME_MODE_TO_PROCESSOR.get(
                        self.lineart_mode.get(), "外部轮廓 (快速)"
                    )
                    preview_img, contours, img_w, img_h = contours_from_lineart_pack(
                        pack, simplify, spline, thick,
                        int(self.lineart_min_area.get()), processor_mode,
                    )

        except Exception as e:
            self.log("预览失败")
            log_error("预览失败", e)
            self._announce_extract = False
            self.is_updating = False
            return

        if preview_img is None:
            hint = get_user_hint(clear=True) or "提取失败，请检查图片或模型文件"
            if method in ("Anime2Sketch", "LineartAnime"):
                self._alert_model_missing(hint)
            else:
                self.log(hint)
            self._announce_extract = False
            self.is_updating = False
            return

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

            if self.taper_paths.get() == 1:
                before = len(contours)
                contours = expand_taper_paths(
                    contours,
                    image_shape=preview_img.shape,
                    max_layers=int(self.taper_layers.get()),
                    taper=self.taper_ratio.get(),
                    spacing=self.taper_spacing.get(),
                )
                preview_img = cv2.cvtColor(cv2.cvtColor(preview_img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                for contour in contours:
                    cv2.polylines(preview_img, [contour], False, (0, 0, 255), int(thick), lineType=cv2.LINE_AA)
                if self._announce_extract and before and len(contours) == before:
                    self.log("起收笔未生效：请改用「中心线」，不要用封闭外框")

            if (getattr(self, "show_chunk_grid", None) is not None
                    and self.show_chunk_grid.get() == 1):
                try:
                    cell_raw = float(self.bbox_cell_size.get()) if hasattr(self, "bbox_cell_size") else 0.0
                except Exception:
                    cell_raw = 0.0
                preview_img, cell_used, cells = draw_chunk_grid(
                    preview_img, contours, cell_size=cell_raw if cell_raw > 0 else None)
                log_debug(f"分块网格 cell={cell_used:.0f}px 共 {cells} 格")

        self.contours = contours
        self.img_w = img_w
        self.img_h = img_h

        if self.preview_original_img is not None:
            try:
                self.preview_original_img.close()
            except Exception:
                pass

        img_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
        self.preview_original_img = Image.fromarray(img_rgb)
        self.preview_zoom = 1.0
        self.display_preview()
        count = 0 if contours is None else len(contours)
        hint = get_user_hint(clear=True)
        if count == 0 and hint and method in ("Anime2Sketch", "LineartAnime"):
            self._alert_model_missing(hint)
            self._announce_extract = False
        elif self._announce_extract:
            self.log(f"提取完成：{count} 条路径")
            self._announce_extract = False
        else:
            log_info(f"预览更新：{count} 条路径")
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
        """滚轮缩放（兼容 Windows / macOS / Linux）"""
        if self.preview_original_img is None:
            return

        delta = getattr(event, "delta", 0)
        num = getattr(event, "num", 0)
        zoom_in = delta > 0 or num == 4
        if zoom_in:
            self.preview_zoom *= 1.1
        else:
            self.preview_zoom /= 1.1

        self.preview_zoom = max(0.1, min(self.preview_zoom, 5.0))
        self.display_preview()

    def zoom_in(self):
        if self.preview_original_img:
            self.preview_zoom *= 1.2
            self.preview_zoom = min(self.preview_zoom, 5.0)
            self.display_preview()

    def zoom_out(self):
        if self.preview_original_img:
            self.preview_zoom /= 1.2
            self.preview_zoom = max(self.preview_zoom, 0.1)
            self.display_preview()

    def reset_zoom(self):
        if self.preview_original_img:
            self.preview_zoom = 1.0
            self.display_preview()
