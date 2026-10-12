"""
轮廓优化模块
包含细化、去噪、抖动修正等功能
"""

import cv2
import numpy as np


def _safe_thinning(mask):
    if not hasattr(cv2, "ximgproc") or not hasattr(cv2.ximgproc, "thinning"):
        raise RuntimeError("当前 OpenCV 缺少 ximgproc.thinning，请安装 opencv-contrib-python。")
    return cv2.ximgproc.thinning(mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)


def thin_contours_to_skeleton(contours, image_shape):
    """将轮廓细化为单线骨架"""
    try:
        h, w = image_shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        
        for contour in contours:
            cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
        
        skeleton = _safe_thinning(mask)
        
        new_contours, _ = cv2.findContours(skeleton, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        print(f"  [细化] {len(contours)} → {len(new_contours)} 条骨架线")
        return list(new_contours)
    except Exception as e:
        print(f"细化失败: {e}")
        return contours


def remove_backtracking(contours):
    """移除回头路径"""
    cleaned_contours = []
    total_removed = 0
    
    for contour in contours:
        points = contour.reshape(-1, 2)
        if len(points) < 3:
            cleaned_contours.append(contour)
            continue
        
        visited = set()
        segments = []
        current_segment = [points[0]]
        
        for i in range(1, len(points)):
            point_tuple = tuple(points[i])
            
            if point_tuple in visited:
                if len(current_segment) >= 2:
                    segments.append(np.array(current_segment))
                current_segment = [points[i]]
                total_removed += 1
            else:
                current_segment.append(points[i])
                visited.add(point_tuple)
        
        if len(current_segment) >= 2:
            segments.append(np.array(current_segment))
        
        for seg in segments:
            if len(seg) >= 2:
                new_contour = seg.reshape(-1, 1, 2).astype(np.int32)
                cleaned_contours.append(new_contour)
    
    if total_removed > 0:
        print(f"  [去回头路] 移除 {total_removed} 处回头路径")
    
    return cleaned_contours


def apply_point_skipping(contours, skip_factor):
    """跳点加速"""
    if skip_factor <= 1:
        return contours
    
    skipped_contours = []
    original_points = 0
    skipped_points = 0
    
    for contour in contours:
        points = contour.reshape(-1, 2)
        original_points += len(points)
        
        sampled_points = points[::skip_factor]
        
        if len(sampled_points) < 2 and len(points) >= 2:
            sampled_points = np.array([points[0], points[-1]])
        
        if len(sampled_points) >= 2:
            new_contour = sampled_points.reshape(-1, 1, 2).astype(np.int32)
            skipped_contours.append(new_contour)
            skipped_points += len(sampled_points)
    
    reduction_percent = (1 - skipped_points / original_points) * 100 if original_points > 0 else 0
    print(f"  [跳点加速] {original_points} → {skipped_points} 点 (-{reduction_percent:.1f}%, {skip_factor}x)")
    
    return skipped_contours


def apply_jitter_correction(contours, strength):
    """抖动修正 - 移动平均平滑"""
    if strength <= 0:
        return contours
    
    corrected_contours = []
    window_size = min(strength + 2, 11)
    
    for contour in contours:
        points = contour.reshape(-1, 2).astype(np.float32)
        
        if len(points) < window_size:
            corrected_contours.append(contour)
            continue
        
        smoothed_points = np.copy(points)
        for i in range(len(points)):
            half_window = window_size // 2
            start = max(0, i - half_window)
            end = min(len(points), i + half_window + 1)
            smoothed_points[i] = np.mean(points[start:end], axis=0)
        
        new_contour = smoothed_points.astype(np.int32).reshape(-1, 1, 2)
        corrected_contours.append(new_contour)
    
    return corrected_contours
