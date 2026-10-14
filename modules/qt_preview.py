"""预览：提取结果仍在图像空间显示，与落笔前的画布精简分开。"""

import os
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QMessageBox

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
    ensure_lineart_anime_weights,
    get_user_hint,
    infer_anime2sketch_edge_map,
    infer_lineart_anime_edge_map,
    process_image_canny,
    process_image_pencil,
)
from modules.settings_store import ANIME_MODE_TO_PROCESSOR


class _PreviewWheelFilter(QObject):
    """独立过滤器，避免 PreviewMixin.eventFilter 被 QMainWindow 盖掉。"""

    def __init__(self, host):
        super().__init__(host)
        self._host = host

    def eventFilter(self, watched, event):
        preview = getattr(self._host, "preview_label", None)
        if preview is not None and watched is preview and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()
            self._host.on_preview_wheel(delta)
            return True
        return False


class _PreviewBridge(QObject):
    finished = Signal(int, object)


class _PreviewWorker(threading.Thread):
    """常驻后台线程：只做轮廓/起收笔，不跑神经网络。"""

    def __init__(self, bridge):
        super().__init__(daemon=True, name="heytea-preview-post")
        self._bridge = bridge
        self._cv = threading.Condition()
        self._pending = None

    def submit(self, gen, params, pack):
        with self._cv:
            self._pending = (gen, params, pack)
            self._cv.notify()

    def run(self):
        while True:
            with self._cv:
                while self._pending is None:
                    self._cv.wait()
                job = self._pending
                self._pending = None
            gen, params, pack = job
            try:
                if pack == "__download_weights__":
                    path = ensure_lineart_anime_weights()
                    result = ("weights_ready", path)
                else:
                    result = _compute_preview(params, pack)
            except Exception as exc:
                result = ("error", exc)
            self._bridge.finished.emit(gen, result)


def _file_stamp(path):
    try:
        st = os.stat(path)
        return (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return (path, 0, 0)


def _infer_cache_key(params):
    method = params["method"]
    stamp = _file_stamp(params["file_path"])
    if method == "Anime2Sketch":
        return (method, stamp, float(params["anime_sigmoid"]))
    if method == "LineartAnime":
        return (method, stamp, int(params["lineart_detect"]), bool(params["lineart_invert"]))
    return None


def _redraw_contours(preview_img, contours, thick):
    if preview_img is None:
        return preview_img
    if preview_img.ndim == 3:
        gray = cv2.cvtColor(preview_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = preview_img
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if contours:
        cv2.polylines(canvas, list(contours), False, (0, 0, 255), int(thick), lineType=cv2.LINE_AA)
    return canvas


def _apply_path_optimize(preview_img, contours, params):
    note = None
    if not contours:
        return preview_img, contours, note

    contours = remove_backtracking(contours)
    jitter = int(params["jitter"])
    if jitter > 0:
        contours = apply_jitter_correction(contours, jitter)
    if params["thin_contours"]:
        contours = thin_contours_to_skeleton(contours, preview_img.shape)
    skip = int(params["skip_points"])
    if skip > 1:
        contours = apply_point_skipping(contours, skip)
    if params["taper_paths"]:
        before = len(contours)
        contours = expand_taper_paths(
            contours,
            image_shape=preview_img.shape,
            max_layers=int(params["taper_layers"]),
            taper=params["taper_ratio"],
            spacing=params["taper_spacing"],
        )
        if params["announce"] and before and len(contours) == before:
            note = "taper_noop"

    preview_img = _redraw_contours(preview_img, contours, params["thick"])
    if params.get("show_grid") and contours:
        cell_raw = float(params.get("grid_cell_size") or 0)
        preview_img, cell_used, cells = draw_chunk_grid(
            preview_img, contours, cell_size=cell_raw if cell_raw > 0 else None)
        log_debug(f"分块网格 cell={cell_used:.0f}px 共 {cells} 格")
    return preview_img, contours, note


def _vectorize_from_pack(params, pack):
    method = params["method"]
    t0 = time.perf_counter()
    if pack is None:
        return None, None, 0, 0, None
    if "error_img" in pack:
        return pack["error_img"], pack.get("contours", []), pack.get("original_w", 0), pack.get("original_h", 0), None

    if method == "Anime2Sketch":
        processor_mode = ANIME_MODE_TO_PROCESSOR.get(params["anime_mode"], "外部轮廓 (快速)")
        preview_img, contours, img_w, img_h = contours_from_anime_pack(
            pack, params["simplify"], params["spline"], params["thick"],
            int(params["anime_threshold"]), int(params["anime_morph_size"]),
            int(params["anime_morph_iter"]), int(params["anime_min_area"]),
            processor_mode, int(params["anime_pre_blur"]),
            params["anime_edge_enhance"], params["anime_invert"], params["anime_adaptive"],
            draw_preview=False,
        )
    elif method == "LineartAnime":
        processor_mode = ANIME_MODE_TO_PROCESSOR.get(params["lineart_mode"], "外部轮廓 (快速)")
        preview_img, contours, img_w, img_h = contours_from_lineart_pack(
            pack, params["simplify"], params["spline"], params["thick"],
            int(params["lineart_min_area"]), processor_mode, draw_preview=False,
        )
    else:
        return None, None, 0, 0, None

    preview_img, contours, note = _apply_path_optimize(preview_img, contours, params)
    log_info(f"轮廓/起收笔 {(time.perf_counter() - t0) * 1000:.0f}ms")
    return preview_img, contours, img_w, img_h, note


def _compute_classic(params):
    method = params["method"]
    file_path = params["file_path"]
    simplify = params["simplify"]
    spline = params["spline"]
    thick = params["thick"]
    t0 = time.perf_counter()
    if method == "Pencil Sketch":
        preview_img, contours, img_w, img_h = process_image_pencil(
            file_path, params["sigma_s"], params["sigma_r"],
            params["shade_factor"], simplify, spline, thick)
    elif method == "Canny":
        blur = int(params["canny_blur"])
        if blur % 2 == 0:
            blur += 1
        preview_img, contours, img_w, img_h = process_image_canny(
            file_path, blur, params["canny_low"], params["canny_high"],
            simplify, spline, thick)
    else:
        return None, None, 0, 0, None
    if preview_img is None:
        return None, None, 0, 0, None
    preview_img, contours, note = _apply_path_optimize(preview_img, contours, params)
    log_info(f"轮廓/起收笔 {(time.perf_counter() - t0) * 1000:.0f}ms")
    return preview_img, contours, img_w, img_h, note


def _compute_preview(params, pack=None):
    """后台：经典算法整段，或神经网络的轮廓后处理。"""
    if pack is None and params["method"] in ("Pencil Sketch", "Canny"):
        return _compute_classic(params)
    return _vectorize_from_pack(params, pack)


def _infer_neural(params):
    method = params["method"]
    if method == "Anime2Sketch":
        return infer_anime2sketch_edge_map(params["file_path"], params["anime_sigmoid"])
    if method == "LineartAnime":
        return infer_lineart_anime_edge_map(
            params["file_path"],
            int(params["lineart_detect"]),
            params["lineart_invert"],
        )
    return None


def _bgr_to_qimage(preview_img):
    if preview_img is None:
        return None
    if preview_img.ndim == 2:
        rgb = cv2.cvtColor(preview_img, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()


class PreviewMixin:
    """Qt 预览。主窗口建好 preview_label 后调用 install_preview_wheel()。"""

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
            QMessageBox.warning(self, "模型未就绪", text)
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

    def install_preview_wheel(self):
        label = getattr(self, "preview_label", None)
        if label is None:
            return
        filt = _PreviewWheelFilter(self)
        self._preview_wheel_filter = filt
        label.installEventFilter(filt)
        self._ensure_preview_bridge()

    def _ensure_preview_bridge(self):
        if not isinstance(getattr(self, "_preview_bridge", None), _PreviewBridge):
            self._preview_bridge = _PreviewBridge(self)
            self._preview_bridge.finished.connect(self._apply_preview)
        if not isinstance(getattr(self, "_preview_worker", None), _PreviewWorker):
            self._preview_worker = _PreviewWorker(self._preview_bridge)
            self._preview_worker.start()
        if not hasattr(self, "_preview_gen"):
            self._preview_gen = 0
        if not hasattr(self, "_preview_dirty"):
            self._preview_dirty = False
        if not hasattr(self, "_edge_cache"):
            self._edge_cache = None
        if not hasattr(self, "_preview_qimage"):
            self._preview_qimage = None
        if not hasattr(self, "_preview_job_params"):
            self._preview_job_params = None

    def _snapshot_extract_params(self):
        return {
            "file_path": self.file_path,
            "method": self.extraction_method.get(),
            "simplify": self.simplify_eps.get(),
            "spline": self.spline_smooth.get(),
            "thick": self.preview_thick.get(),
            "sigma_s": self.sigma_s.get(),
            "sigma_r": self.sigma_r.get(),
            "shade_factor": self.shade_factor.get(),
            "canny_blur": self.canny_blur.get(),
            "canny_low": self.canny_low.get(),
            "canny_high": self.canny_high.get(),
            "anime_mode": self.anime_mode.get(),
            "anime_threshold": self.anime_threshold.get(),
            "anime_morph_size": self.anime_morph_size.get(),
            "anime_morph_iter": self.anime_morph_iter.get(),
            "anime_min_area": self.anime_min_area.get(),
            "anime_pre_blur": self.anime_pre_blur.get(),
            "anime_edge_enhance": self.anime_edge_enhance.get(),
            "anime_sigmoid": self.anime_sigmoid.get(),
            "anime_invert": self.anime_invert.get() == 1,
            "anime_adaptive": self.anime_adaptive.get() == 1,
            "lineart_mode": self.lineart_mode.get(),
            "lineart_detect": self.lineart_detect.get(),
            "lineart_min_area": self.lineart_min_area.get(),
            "lineart_invert": self.lineart_invert.get() == 1,
            "jitter": self.jitter_correct.get(),
            "thin_contours": self.thin_contours.get() == 1,
            "skip_points": self.skip_points.get(),
            "taper_paths": self.taper_paths.get() == 1,
            "taper_layers": self.taper_layers.get(),
            "taper_ratio": self.taper_ratio.get(),
            "taper_spacing": self.taper_spacing.get(),
            "show_grid": self.show_chunk_grid.get() == 1 if hasattr(self, "show_chunk_grid") else False,
            "grid_cell_size": self.bbox_cell_size.get() if hasattr(self, "bbox_cell_size") else 0,
            "announce": bool(self._announce_extract),
        }

    def update_preview_throttled(self):
        """延迟更新：拖动时不立刻提取。"""
        self._preview_dirty = True
        timer = getattr(self, "_preview_timer", None)
        if not isinstance(timer, QTimer):
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.timeout.connect(self.update_preview)
        self._preview_timer.start(280)

    def update_preview(self):
        """排队提取。已在跑则只做标记，跑完再跟最新参数。"""
        if not self.file_path:
            return
        self._ensure_preview_bridge()
        timer = getattr(self, "_preview_timer", None)
        if isinstance(timer, QTimer):
            timer.stop()
        if self.is_updating:
            self._preview_dirty = True
            return

        self.is_updating = True
        self._preview_dirty = False
        self._preview_gen = int(getattr(self, "_preview_gen", 0)) + 1
        gen = self._preview_gen
        announce = bool(self._announce_extract)
        if self.extraction_method.get() == "LineartAnime" and announce and not os.path.isfile(LINEART_ANIME_PATH):
            self.log("首次使用 LineartAnime，正在检查/下载权重…")
        params = self._snapshot_extract_params()
        params["announce"] = announce
        self._preview_job_params = params
        QTimer.singleShot(0, lambda: self._run_preview_job(gen, params))

    def _run_preview_job(self, gen, params):
        """主线程：神经网络前向（MPS）；后处理交给常驻线程。"""
        if gen != getattr(self, "_preview_gen", 0):
            return
        method = params["method"]
        worker = self._preview_worker

        if method == "LineartAnime" and not os.path.isfile(LINEART_ANIME_PATH):
            worker.submit(gen, params, "__download_weights__")
            return

        if method in ("Anime2Sketch", "LineartAnime"):
            key = _infer_cache_key(params)
            cache = getattr(self, "_edge_cache", None)
            if cache is not None and cache.get("key") == key:
                self._ensure_cache_stats().record_hit(method)
                worker.submit(gen, params, cache["pack"])
                return
            self._ensure_cache_stats().record_miss(method)
            pack = _infer_neural(params)
            if pack is not None and "error_img" not in pack:
                self._edge_cache = {"key": key, "pack": pack}
            else:
                self._edge_cache = None
            worker.submit(gen, params, pack)
            return

        worker.submit(gen, params, None)

    def _apply_preview(self, gen, result):
        if gen != getattr(self, "_preview_gen", 0):
            return

        if isinstance(result, tuple) and len(result) == 2 and result[0] == "weights_ready":
            if not result[1]:
                self.is_updating = False
                self._alert_model_missing(get_user_hint(clear=True) or "提取失败，请检查图片或模型文件")
                self._announce_extract = False
                if self._preview_dirty:
                    self.update_preview()
                return
            params = getattr(self, "_preview_job_params", None)
            if params is None:
                self.is_updating = False
                return
            QTimer.singleShot(0, lambda: self._run_preview_job(gen, params))
            return

        self.is_updating = False
        if isinstance(result, tuple) and len(result) == 2 and result[0] == "error":
            self.log("预览失败")
            log_error("预览失败", result[1])
            self._announce_extract = False
            if self._preview_dirty:
                self.update_preview()
            return

        preview_img, contours, img_w, img_h, note = result
        if preview_img is None:
            self._alert_model_missing(get_user_hint(clear=True) or "提取失败，请检查图片或模型文件")
            self._announce_extract = False
            if self._preview_dirty:
                self.update_preview()
            return

        if note == "taper_noop" and self._announce_extract:
            self.log("起收笔未生效：请改用「中心线」，不要用封闭外框")

        self.contours = contours
        self.img_w = img_w
        self.img_h = img_h

        t0 = time.perf_counter()
        self._preview_qimage = _bgr_to_qimage(preview_img)
        self.preview_original_img = self._preview_qimage
        self.preview_zoom = 1.0
        self.display_preview()
        log_info(f"预览显示 {(time.perf_counter() - t0) * 1000:.0f}ms")
        count = 0 if contours is None else len(contours)
        hint = get_user_hint(clear=True)
        method = getattr(self, "_last_preview_method", None) or (
            self.extraction_method.get() if hasattr(self, "extraction_method") else ""
        )
        if count == 0 and hint and method in ("Anime2Sketch", "LineartAnime"):
            self._alert_model_missing(hint)
            self._announce_extract = False
        elif self._announce_extract:
            self.log(f"提取完成：{count} 条路径")
            self._announce_extract = False
        else:
            log_info(f"预览更新：{count} 条路径")
        if self._preview_dirty:
            self.update_preview()

    def display_preview(self):
        """显示预览"""
        qimage = getattr(self, "_preview_qimage", None)
        if qimage is None or qimage.isNull():
            return

        rect = self.preview_label.contentsRect()
        canvas_w = rect.width()
        canvas_h = rect.height()

        if canvas_w < 50 or canvas_h < 50:
            canvas_w, canvas_h = 800, 600

        img_w = qimage.width()
        img_h = qimage.height()
        if img_w <= 0 or img_h <= 0:
            return

        scale = min(canvas_w / img_w, canvas_h / img_h) * self.preview_zoom
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        if new_w > 0 and new_h > 0:
            pixmap = QPixmap.fromImage(qimage).scaled(
                new_w,
                new_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.preview_label.setPixmap(pixmap)

    def on_preview_wheel(self, delta: int):
        """滚轮缩放。delta > 0 放大。"""
        if self.preview_original_img is None:
            return

        if delta > 0:
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
