"""
图像处理模块
包含线条提取算法：Pencil Sketch, Canny, Anime2Sketch, LineartAnime
"""

import os
import threading
import time

import cv2
import numpy as np
from scipy.interpolate import splprep, splev
from modules.smart_resize import adaptive_resize, calculate_optimal_size
from modules.contour_optimizer import trace_centerlines
from modules.app_logger import log_debug, log_error, log_info, log_warning

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(APP_ROOT, "models")
LINEART_ANIME_PATH = os.path.join(MODELS_DIR, "lineart_anime.pth")
LINEART_HF_REPO = "lllyasviel/Annotators"
LINEART_HF_FILE = "netG.pth"

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    log_warning("PyTorch 未安装，Anime2Sketch 不可用")


# --- Anime2Sketch 模型定义 ---
if TORCH_AVAILABLE:
    class UnetGenerator(nn.Module):
        def __init__(self, input_nc=3, output_nc=1, num_downs=8, ngf=64):
            super(UnetGenerator, self).__init__()
            unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=None, norm_layer=nn.InstanceNorm2d, innermost=True)
            for i in range(num_downs - 5):
                unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=unet_block, norm_layer=nn.InstanceNorm2d, use_dropout=True)
            unet_block = UnetSkipConnectionBlock(ngf * 4, ngf * 8, input_nc=None, submodule=unet_block, norm_layer=nn.InstanceNorm2d)
            unet_block = UnetSkipConnectionBlock(ngf * 2, ngf * 4, input_nc=None, submodule=unet_block, norm_layer=nn.InstanceNorm2d)
            unet_block = UnetSkipConnectionBlock(ngf, ngf * 2, input_nc=None, submodule=unet_block, norm_layer=nn.InstanceNorm2d)
            self.model = UnetSkipConnectionBlock(output_nc, ngf, input_nc=input_nc, submodule=unet_block, outermost=True, norm_layer=nn.InstanceNorm2d)

        def forward(self, input):
            return self.model(input)

    class UnetSkipConnectionBlock(nn.Module):
        def __init__(self, outer_nc, inner_nc, input_nc=None, submodule=None, outermost=False, innermost=False, norm_layer=nn.InstanceNorm2d, use_dropout=False):
            super(UnetSkipConnectionBlock, self).__init__()
            self.outermost = outermost
            if input_nc is None:
                input_nc = outer_nc
            downconv = nn.Conv2d(input_nc, inner_nc, kernel_size=4, stride=2, padding=1, bias=False)
            downrelu = nn.LeakyReLU(0.2, True)
            downnorm = norm_layer(inner_nc)
            uprelu = nn.ReLU(True)
            upnorm = norm_layer(outer_nc)

            if outermost:
                upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, kernel_size=4, stride=2, padding=1)
                down = [downconv]
                up = [uprelu, upconv, nn.Tanh()]
                model = down + [submodule] + up
            elif innermost:
                upconv = nn.ConvTranspose2d(inner_nc, outer_nc, kernel_size=4, stride=2, padding=1, bias=False)
                down = [downrelu, downconv]
                up = [uprelu, upconv, upnorm]
                model = down + up
            else:
                upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, kernel_size=4, stride=2, padding=1, bias=False)
                down = [downrelu, downconv, downnorm]
                up = [uprelu, upconv, upnorm]
                if use_dropout:
                    model = down + [submodule] + up + [nn.Dropout(0.5)]
                else:
                    model = down + [submodule] + up

            self.model = nn.Sequential(*model)

        def forward(self, x):
            if self.outermost:
                return self.model(x)
            else:
                return torch.cat([x, self.model(x)], 1)


# --- 全局模型缓存 ---
anime2sketch_model = None
lineart_anime_model = None
LAST_USER_HINT = ""  # 最近一次面向用户的中文提示（缺模型等）


def get_torch_device():
    """cuda → mps → cpu。"""
    if not TORCH_AVAILABLE:
        return None
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _sync_torch(device):
    if device is None or not TORCH_AVAILABLE:
        return
    if device.type == "cuda":
        torch.cuda.synchronize()
    elif device.type == "mps" and hasattr(torch, "mps"):
        torch.mps.synchronize()


def _thread_note():
    return "主线程" if threading.current_thread() is threading.main_thread() else "后台线程"


MODEL_HINTS = {
    "torch": "未安装 PyTorch，无法使用 Anime2Sketch / LineartAnime。请在 heytea-painter 环境中安装 torch。",
    "anime2sketch": "未找到 Anime2Sketch 模型。请将 netG.pth 放到项目 models/ 目录后重试。",
    "lineart": "未找到 LineartAnime 模型。请将 lineart_anime.pth 放到 models/，或安装 huggingface_hub 自动下载。",
    "anime_load": "Anime2Sketch 模型加载失败。请检查 models/netG.pth 是否完整，或查看 logs/ 错误日志。",
    "lineart_load": "LineartAnime 模型加载失败。请检查 models/lineart_anime.pth，或查看 logs/ 错误日志。",
}


def set_user_hint(text):
    """记录面向用户的中文提示，供预览界面读取。"""
    global LAST_USER_HINT
    LAST_USER_HINT = str(text or "").strip()
    if LAST_USER_HINT:
        log_error(LAST_USER_HINT)


def get_user_hint(clear=False):
    global LAST_USER_HINT
    hint = LAST_USER_HINT
    if clear:
        LAST_USER_HINT = ""
    return hint


def _placeholder_error(message, hint_key=None, user_message=None):
    """预览占位图（英文短句，OpenCV 字体不支持中文）+ 中文用户提示。"""
    global LAST_USER_HINT
    hint = user_message or MODEL_HINTS.get(hint_key or "", "") or str(message)
    LAST_USER_HINT = hint
    log_error(hint)
    error_img = np.zeros((300, 500, 3), dtype=np.uint8)
    # 画面用英文短句；中文走日志/界面
    lines = str(message).splitlines()
    y = 120
    for line in lines[:3]:
        cv2.putText(error_img, line[:40], (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y += 36
    cv2.putText(error_img, "See log / models folder", (24, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
    return {
        "error_img": error_img,
        "contours": [],
        "original_w": 500,
        "original_h": 300,
        "user_message": hint,
    }


def _load_unet_weights(model_path, device):
    model = UnetGenerator(input_nc=3, output_nc=1, num_downs=8, ngf=64)
    state_dict = torch.load(model_path, map_location=device)
    if isinstance(state_dict, dict) and "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    new_state_dict = {}
    for key, value in state_dict.items():
        new_state_dict[key[7:] if key.startswith("module.") else key] = value
    missing_keys, unexpected_keys = model.load_state_dict(new_state_dict, strict=False)
    if missing_keys:
        log_debug(f"模型缺少键: {len(missing_keys)}")
    if unexpected_keys:
        log_debug(f"模型多余键: {len(unexpected_keys)}")
    model.to(device)
    model.eval()
    return model


def get_anime2sketch_model():
    """加载或获取缓存的 Anime2Sketch 模型"""
    global anime2sketch_model
    
    if anime2sketch_model is not None:
        return anime2sketch_model
    
    if not TORCH_AVAILABLE:
        log_error("PyTorch 未安装")
        anime2sketch_model = "error"
        return None
    
    if anime2sketch_model == "error":
        return None
    
    # 尝试加载模型
    try:
        import os
        # 模型路径：使用绝对路径，支持中文路径
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(script_dir, "models", "netG.pth")
        
        # 确保路径存在
        if not os.path.exists(model_path):
            # 尝试其他可能的路径
            alternative_paths = [
                os.path.join(os.getcwd(), "models", "netG.pth"),
                os.path.join(script_dir, "netG.pth"),
                "models/netG.pth",
                "netG.pth"
            ]
            
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    model_path = alt_path
                    log_info(f"Anime2Sketch 模型: {model_path}")
                    break
            else:
                set_user_hint(MODEL_HINTS["anime2sketch"]); log_error(f"找不到 Anime2Sketch 模型，请放到 {os.path.join(script_dir, 'models', 'netG.pth')}")
                anime2sketch_model = "error"
                return None
        
        model_path = os.path.abspath(model_path)
        
        if not os.path.exists(model_path):
            set_user_hint(MODEL_HINTS["anime2sketch"]); log_error(f"找不到模型文件: {model_path}")
            anime2sketch_model = "error"
            return None
        
        device = get_torch_device()
        anime2sketch_model = _load_unet_weights(model_path, device)
        log_info(f"Anime2Sketch 已加载（{device}）")
    except Exception as e:
        set_user_hint(MODEL_HINTS["anime_load"]); log_error("无法加载 Anime2Sketch 模型", e)
        anime2sketch_model = "error"
        return None
    
    return anime2sketch_model


def ensure_lineart_anime_weights():
    """本地没有权重时从 Hugging Face 下载到 models/lineart_anime.pth。"""
    if os.path.isfile(LINEART_ANIME_PATH):
        return LINEART_ANIME_PATH
    os.makedirs(MODELS_DIR, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        set_user_hint(MODEL_HINTS["lineart"]); log_error("未安装 huggingface_hub，无法下载 LineartAnime。请 pip install huggingface_hub")
        return None
    try:
        log_info("正在下载 LineartAnime 权重（lllyasviel/Annotators）…")
        downloaded = hf_hub_download(
            repo_id=LINEART_HF_REPO,
            filename=LINEART_HF_FILE,
            local_dir=MODELS_DIR,
            local_dir_use_symlinks=False,
        )
        if os.path.abspath(downloaded) != os.path.abspath(LINEART_ANIME_PATH):
            import shutil
            shutil.copy2(downloaded, LINEART_ANIME_PATH)
            leftover = os.path.join(MODELS_DIR, LINEART_HF_FILE)
            if os.path.isfile(leftover) and os.path.abspath(leftover) != os.path.abspath(LINEART_ANIME_PATH):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
        log_info(f"LineartAnime 权重: {LINEART_ANIME_PATH}")
        return LINEART_ANIME_PATH
    except Exception as exc:
        set_user_hint(MODEL_HINTS["lineart"]); log_error(f"下载 LineartAnime 失败，请手动放到 {LINEART_ANIME_PATH}", exc)
        return None


def get_lineart_anime_model():
    global lineart_anime_model
    if lineart_anime_model is not None and lineart_anime_model != "error":
        return lineart_anime_model
    if lineart_anime_model == "error":
        return None
    if not TORCH_AVAILABLE:
        log_error("PyTorch 未安装")
        lineart_anime_model = "error"
        return None
    path = ensure_lineart_anime_weights()
    if not path:
        lineart_anime_model = "error"
        return None
    try:
        device = get_torch_device()
        lineart_anime_model = _load_unet_weights(path, device)
        log_info(f"LineartAnime 已加载（{device}）")
        return lineart_anime_model
    except Exception as exc:
        set_user_hint(MODEL_HINTS["lineart_load"]); log_error("无法加载 LineartAnime 模型", exc)
        lineart_anime_model = "error"
        return None


def edge_map_to_contours(
    edge_map,
    simplify_eps,
    spline_smoothness,
    preview_thickness,
    threshold_val,
    morph_size,
    morph_iter,
    min_area,
    contour_mode="外部轮廓 (快速)",
    pre_blur=0,
    edge_enhance=0,
    invert=False,
    adaptive=False,
    label="提取",
    draw_preview=True,
):
    """灰度线稿 → 轮廓。Anime2Sketch / LineartAnime 共用。"""
    work = edge_map.copy()
    if pre_blur > 0:
        blur_size = pre_blur if pre_blur % 2 == 1 else pre_blur + 1
        work = cv2.GaussianBlur(work, (blur_size, blur_size), 0)
        log_debug(f"预处理模糊 {blur_size}x{blur_size}")
    if edge_enhance > 0:
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]]) * edge_enhance / 3.0
        work = cv2.filter2D(work, -1, kernel)
        work = np.clip(work, 0, 255).astype(np.uint8)
        log_debug(f"边缘增强 {edge_enhance:.1f}")
    if adaptive:
        binary = cv2.adaptiveThreshold(
            work, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV if not invert else cv2.THRESH_BINARY, 11, 2,
        )
        log_debug("自适应二值化")
    else:
        thresh_type = cv2.THRESH_BINARY_INV if not invert else cv2.THRESH_BINARY
        _, binary = cv2.threshold(work, threshold_val, 255, thresh_type)
        log_debug(f"二值化阈值 {threshold_val}")

    white_before = np.sum(binary == 255)
    iters = max(0, int(morph_iter))
    if iters > 0:
        kernel = np.ones((max(1, int(morph_size)), max(1, int(morph_size))), np.uint8)
        binary = cv2.dilate(binary, kernel, iterations=iters)
    if white_before > 0:
        increase = (np.sum(binary == 255) - white_before) / white_before * 100
        log_debug(f"形态学 {morph_size}x{morph_size}×{morph_iter} +{increase:.0f}%")

    use_centerline = "中心线" in contour_mode or "骨架提取" in contour_mode
    if use_centerline:
        min_length = max(4.0, float(min_area))
        contours = trace_centerlines(binary, min_length=min_length)
        closed = False
    elif "所有轮廓" in contour_mode:
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        contours = [c for c in contours if cv2.contourArea(c) > min_area]
        closed = True
    else:
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = [c for c in contours if cv2.contourArea(c) > min_area]
        closed = True

    log_debug(f"{contour_mode} 过滤后 {len(contours)} 条")
    simplified = [cv2.approxPolyDP(c, simplify_eps, closed) for c in contours]
    if spline_smoothness > 0:
        simplified = smooth_contours(simplified, spline_smoothness)
    preview = cv2.cvtColor(work, cv2.COLOR_GRAY2BGR)
    if draw_preview and simplified:
        cv2.polylines(preview, simplified, False, (0, 0, 255), int(preview_thickness), lineType=cv2.LINE_AA)
    total_points = sum(len(c) for c in simplified)
    log_info(f"{label} {len(simplified)} 条，{total_points} 点")
    return preview, simplified


# --- 图像处理函数 ---

def load_image_with_unicode(file_path, target_size=None):
    """
    支持 Unicode 路径的图片加载并自动调整到合理尺寸
    
    参数:
        file_path: 图片路径（支持中文）
        target_size: 目标尺寸（可选），如果提供则优先使用
    
    返回:
        image: BGR 图像数组
    """
    try:
        # 使用 numpy 读取文件字节，然后用 cv2 解码
        with open(file_path, 'rb') as f:
            file_bytes = np.frombuffer(f.read(), dtype=np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if image is None:
            log_error(f"无法解码图像: {file_path}")
            return None
        
        # 获取原始尺寸
        h, w = image.shape[:2]
        original_size = f"{w}x{h}"
        
        # 智能缩放策略：使用高质量算法防止精度损失
        MAX_SIZE = 2048       # 绝对上限（防止内存问题）
        MIN_SIZE = 256        # 绝对下限
        DEFAULT_TARGET = 1024 # 默认目标尺寸
        
        # 如果没有指定目标尺寸，使用默认策略
        if target_size is None:
            target_size = DEFAULT_TARGET
        
        max_dim = max(h, w)
        
        # 智能缩放逻辑（使用高质量算法）
        if max_dim > MAX_SIZE:
            # 超大图片：使用智能下采样
            scale = MAX_SIZE / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            log_info(f"图片过大 {original_size} → {new_w}x{new_h}")
            image = adaptive_resize(image, new_w, new_h, preserve_detail=True)
            
        elif max_dim > target_size * 1.5:
            # 图片较大：使用智能下采样
            scale = target_size / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            log_info(f"图片较大 {original_size} → {new_w}x{new_h}")
            image = adaptive_resize(image, new_w, new_h, preserve_detail=True)
            
        elif max_dim < MIN_SIZE:
            # 图片太小：使用智能上采样
            scale = MIN_SIZE / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            log_info(f"图片过小 {original_size} → {new_w}x{new_h}")
            image = adaptive_resize(image, new_w, new_h, preserve_detail=True)
        
        else:
            log_debug(f"图片尺寸 {original_size}")
        
        return image
    except FileNotFoundError:
        log_error(f"文件不存在: {file_path}")
        return None
    except PermissionError:
        log_error(f"没有读取权限: {file_path}")
        return None
    except Exception as e:
        log_error(f"加载图像失败: {file_path}", e)
        return None


def process_image_pencil(file_path, sigma_s, sigma_r, shade_factor, 
                         simplify_eps, spline_smoothness, preview_thickness):
    """Pencil Sketch 线条提取"""
    try:
        image_rgb = load_image_with_unicode(file_path)
        if image_rgb is None:
            log_error("无法加载图像")
            return None, None, 0, 0
        
        img_gray, img_blur = cv2.pencilSketch(
            image_rgb,
            sigma_s=sigma_s,
            sigma_r=sigma_r,
            shade_factor=shade_factor
        )
        
        _, edges = cv2.threshold(img_gray, 240, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        simplified_contours = [cv2.approxPolyDP(c, simplify_eps, True) for c in contours]
        
        final_contours = simplified_contours
        if spline_smoothness > 0:
            final_contours = smooth_contours(simplified_contours, spline_smoothness)
        
        preview_canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
        for contour in final_contours:
            cv2.polylines(preview_canvas, [contour], False, (0, 0, 255), int(preview_thickness), lineType=cv2.LINE_AA)
        
        total_points = sum(len(c) for c in final_contours)
        log_info(f"Pencil {len(final_contours)} 条，{total_points} 点")
        
        return preview_canvas, final_contours, image_rgb.shape[1], image_rgb.shape[0]
    
    except Exception as e:
        log_error("Pencil Sketch 处理失败", e)
        return None, None, 0, 0


def process_image_canny(file_path, blur_kernel, low_thresh, high_thresh,
                        simplify_eps, spline_smoothness, preview_thickness):
    """Canny 边缘检测"""
    try:
        image_rgb = load_image_with_unicode(file_path)
        if image_rgb is None:
            log_error("无法加载图像")
            return None, None, 0, 0
        
        img_gray = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2GRAY)
        img_blur = cv2.GaussianBlur(img_gray, (blur_kernel, blur_kernel), 0)
        edges = cv2.Canny(img_blur, low_thresh, high_thresh)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        simplified_contours = [cv2.approxPolyDP(c, simplify_eps, True) for c in contours]
        
        final_contours = simplified_contours
        if spline_smoothness > 0:
            final_contours = smooth_contours(simplified_contours, spline_smoothness)
        
        preview_canvas = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        for contour in final_contours:
            cv2.polylines(preview_canvas, [contour], False, (0, 0, 255), int(preview_thickness), lineType=cv2.LINE_AA)
        
        total_points = sum(len(c) for c in final_contours)
        log_info(f"Canny {len(final_contours)} 条，{total_points} 点")
        
        return preview_canvas, final_contours, image_rgb.shape[1], image_rgb.shape[0]
    
    except Exception as e:
        log_error("Canny 处理失败", e)
        return None, None, 0, 0


def infer_anime2sketch_edge_map(file_path, sigmoid_threshold=0.5):
    """只跑 Anime2Sketch 网络。请在加载模型的同一线程调用（推荐 GUI 主线程 / MPS）。"""
    try:
        if not TORCH_AVAILABLE:
            return _placeholder_error("PyTorch Not Installed", hint_key="torch")

        image_rgb = load_image_with_unicode(file_path)
        if image_rgb is None:
            log_error("无法加载图像")
            return None

        model = get_anime2sketch_model()
        if model is None:
            return _placeholder_error("Anime2Sketch Missing", hint_key="anime2sketch")

        h, w = image_rgb.shape[:2]
        original_h, original_w = h, w
        target_h = ((h - 1) // 256 + 1) * 256
        target_w = ((w - 1) // 256 + 1) * 256

        max_size = 1024
        need_restore_size = False

        if target_h > max_size or target_w > max_size:
            need_restore_size = True
            scale = min(max_size / target_h, max_size / target_w)
            new_h = int(h * scale)
            new_w = int(w * scale)
            image_resized = cv2.resize(image_rgb, (new_w, new_h))
            target_h = ((new_h - 1) // 256 + 1) * 256
            target_w = ((new_w - 1) // 256 + 1) * 256
        else:
            image_resized = image_rgb

        pad_h = target_h - image_resized.shape[0]
        pad_w = target_w - image_resized.shape[1]
        image_padded = cv2.copyMakeBorder(image_resized, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)

        image = cv2.cvtColor(image_padded, cv2.COLOR_BGR2RGB)
        image = image.astype(np.float32) / 255.0
        image = np.transpose(image, (2, 0, 1))
        image = torch.from_numpy(image).unsqueeze(0).float()

        device = next(model.parameters()).device
        image = image.to(device)

        t0 = time.perf_counter()
        with torch.no_grad():
            edge = model(image)
            edge = torch.sigmoid((edge - float(sigmoid_threshold)) * 10)
        _sync_torch(device)
        infer_ms = (time.perf_counter() - t0) * 1000.0

        edge_map = edge.squeeze().cpu().numpy()
        edge_map = edge_map[:image_resized.shape[0], :image_resized.shape[1]]
        edge_map = (edge_map * 255.0).astype(np.uint8)

        if need_restore_size:
            log_debug(f"缩放恢复 {image_resized.shape[1]}x{image_resized.shape[0]} → {original_w}x{original_h}")
            edge_map = cv2.resize(edge_map, (original_w, original_h), interpolation=cv2.INTER_LINEAR)

        set_user_hint(""); log_info(f"推理 Anime2Sketch {infer_ms:.0f}ms（{device}/{_thread_note()}）")
        return {
            "edge_map": edge_map,
            "original_w": original_w,
            "original_h": original_h,
        }
    except Exception as e:
        log_error("Anime2Sketch 处理失败", e)
        return None


def contours_from_anime_pack(
    pack, simplify_eps, spline_smoothness, preview_thickness,
    threshold_val, morph_size, morph_iter, min_area, contour_mode="外部轮廓 (快速)",
    pre_blur=0, edge_enhance=0, invert=False, adaptive=False, draw_preview=True,
):
    preview_canvas, final_contours = edge_map_to_contours(
        pack["edge_map"], simplify_eps, spline_smoothness, preview_thickness,
        threshold_val, morph_size, morph_iter, min_area, contour_mode,
        pre_blur, edge_enhance, invert, adaptive, label="Anime2Sketch",
        draw_preview=draw_preview,
    )
    return preview_canvas, final_contours, pack["original_w"], pack["original_h"]


def process_image_anime2sketch(file_path, simplify_eps, spline_smoothness, preview_thickness, 
                                threshold_val, morph_size, morph_iter, min_area, contour_mode="外部轮廓 (快速)",
                                pre_blur=0, edge_enhance=0, sigmoid_threshold=0.5, invert=False, adaptive=False):
    """Anime2Sketch AI 线条提取"""
    pack = infer_anime2sketch_edge_map(file_path, sigmoid_threshold)
    if pack is None:
        return None, None, 0, 0
    if "error_img" in pack:
        return pack["error_img"], pack.get("contours", []), pack["original_w"], pack["original_h"]
    return contours_from_anime_pack(
        pack, simplify_eps, spline_smoothness, preview_thickness,
        threshold_val, morph_size, morph_iter, min_area, contour_mode,
        pre_blur, edge_enhance, invert, adaptive,
    )


def _scale_contours(contours, sx, sy):
    """把检测分辨率上的折线映射回原图像素。"""
    scaled = []
    for contour in contours:
        pts = contour.reshape(-1, 2).astype(np.float64)
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        scaled.append(np.round(pts).astype(np.int32).reshape(-1, 1, 2))
    return scaled


def _resize_lineart_detect(image, detect_resolution):
    """controlnet_aux.resize_image：短边对齐到 detect_resolution，边长取 64 倍数。"""
    height, width = image.shape[:2]
    detect_resolution = max(256, int(detect_resolution))
    scale = float(detect_resolution) / float(min(height, width))
    new_h = int(np.round(height * scale / 64.0)) * 64
    new_w = int(np.round(width * scale / 64.0)) * 64
    new_h = max(64, new_h)
    new_w = max(64, new_w)
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA
    return cv2.resize(image, (new_w, new_h), interpolation=interp)


def infer_lineart_anime_edge_map(file_path, detect_resolution=512, invert=True):
    """只跑 LineartAnime 网络。请在加载模型的同一线程调用（推荐 GUI 主线程 / MPS）。"""
    try:
        if not TORCH_AVAILABLE:
            return _placeholder_error("PyTorch Not Installed", hint_key="torch")

        image_bgr = load_image_with_unicode(file_path)
        if image_bgr is None:
            log_error("无法加载图像")
            return None

        model = get_lineart_anime_model()
        if model is None:
            return _placeholder_error("LineartAnime Missing", hint_key="lineart")

        original_h, original_w = image_bgr.shape[:2]
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        detect = _resize_lineart_detect(image_rgb, detect_resolution)
        dh, dw = detect.shape[:2]
        target_h = 256 * int(np.ceil(float(dh) / 256.0))
        target_w = 256 * int(np.ceil(float(dw) / 256.0))
        padded = cv2.resize(detect, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
        tensor = padded.astype(np.float32) / 127.5 - 1.0
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = torch.from_numpy(tensor).unsqueeze(0).float()
        device = next(model.parameters()).device
        tensor = tensor.to(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            line = model(tensor)[0, 0] * 127.5 + 127.5
        _sync_torch(device)
        infer_ms = (time.perf_counter() - t0) * 1000.0
        edge_map = line.cpu().numpy()
        edge_map = cv2.resize(edge_map, (dw, dh), interpolation=cv2.INTER_CUBIC)
        edge_map = np.clip(edge_map, 0, 255).astype(np.uint8)
        if invert:
            edge_map = 255 - edge_map
        bright_lines = float(edge_map.mean()) < 127
        set_user_hint(""); log_info(f"推理 LineartAnime {infer_ms:.0f}ms（{device}/{_thread_note()}）")
        log_debug(
            f"LineartAnime detect={detect_resolution} infer={dw}x{dh} "
            f"invert={invert} mean={edge_map.mean():.1f}"
        )
        return {
            "edge_map": edge_map,
            "original_w": original_w,
            "original_h": original_h,
            "detect_w": dw,
            "detect_h": dh,
            "bright_lines": bright_lines,
        }
    except Exception as e:
        log_error("LineartAnime 处理失败", e)
        return None


def contours_from_lineart_pack(
    pack, simplify_eps, spline_smoothness, preview_thickness,
    min_area=10, contour_mode="外部轮廓 (快速)", draw_preview=True,
):
    edge_map = pack["edge_map"]
    original_w = pack["original_w"]
    original_h = pack["original_h"]
    dw = pack["detect_w"]
    dh = pack["detect_h"]
    _, detect_contours = edge_map_to_contours(
        edge_map, simplify_eps, spline_smoothness, preview_thickness,
        127, 1, 0, min_area, contour_mode,
        0, 0, pack["bright_lines"], False, label="LineartAnime",
        draw_preview=False,
    )
    sx = original_w / float(dw)
    sy = original_h / float(dh)
    final_contours = _scale_contours(detect_contours, sx, sy)
    preview_gray = cv2.resize(edge_map, (original_w, original_h), interpolation=cv2.INTER_LINEAR)
    preview_canvas = cv2.cvtColor(preview_gray, cv2.COLOR_GRAY2BGR)
    if draw_preview and final_contours:
        cv2.polylines(
            preview_canvas, final_contours, False, (0, 0, 255),
            int(preview_thickness), lineType=cv2.LINE_AA,
        )
    return preview_canvas, final_contours, original_w, original_h


def process_image_lineart_anime(
    file_path, simplify_eps, spline_smoothness, preview_thickness,
    detect_resolution=512, min_area=10, contour_mode="外部轮廓 (快速)",
    invert=True,
):
    """
    ControlNet LineartAnime：detect_resolution → 256 对齐 → [-1,1] → 推理。
    invert=True 时做官方 255-x；轮廓提取只用最小面积和轮廓模式。
    """
    pack = infer_lineart_anime_edge_map(file_path, detect_resolution, invert)
    if pack is None:
        return None, None, 0, 0
    if "error_img" in pack:
        return pack["error_img"], pack.get("contours", []), pack["original_w"], pack["original_h"]
    return contours_from_lineart_pack(
        pack, simplify_eps, spline_smoothness, preview_thickness,
        min_area, contour_mode,
    )


def smooth_contours(contours, smoothness_s, new_points_factor=1.5):
    """B-spline 样条平滑"""
    smoothed_contours = []
    
    for c in contours:
        if len(c) < 4:
            smoothed_contours.append(c)
            continue
        
        try:
            x, y = c[:, 0, 0], c[:, 0, 1]
            tck, u = splprep([x, y], s=smoothness_s, k=3, per=0)
            num_new_points = int(len(c) * new_points_factor)
            if num_new_points < 4:
                num_new_points = 4
            u_new = np.linspace(u.min(), u.max(), num_new_points)
            x_new, y_new = splev(u_new, tck)
            new_contour = np.array([x_new, y_new]).T.reshape(-1, 1, 2).astype(np.int32)
            smoothed_contours.append(new_contour)
        except:
            smoothed_contours.append(c)
    
    return smoothed_contours
