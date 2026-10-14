"""
轮廓优化模块
包含细化、去噪、抖动修正等功能
"""

import cv2
import numpy as np

from modules.app_logger import log_error, log_info

_NEIGH8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def _neighbors8(y, x, h, w, ink):
    out = []
    for dy, dx in _NEIGH8:
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w and ink[ny, nx]:
            out.append((ny, nx))
    return out


def _edge_key(a, b):
    return (a, b) if a <= b else (b, a)


def trace_centerlines(binary, min_length=8):
    """
    把线稿二值图收成单像素骨架，再沿骨架走中心线。
    返回 OpenCV 折线 (N,1,2)，开口路径，不是色块外框。
    """
    if binary is None or binary.size == 0:
        return []
    if not hasattr(cv2, "ximgproc") or not hasattr(cv2.ximgproc, "thinning"):
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        return list(contours)

    skeleton = cv2.ximgproc.thinning(binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    ink = skeleton > 0
    h, w = ink.shape
    ys, xs = np.where(ink)
    if len(ys) == 0:
        return []

    coords = [(int(y), int(x)) for y, x in zip(ys, xs)]
    nbrs = {}
    deg = {}
    for point in coords:
        nearby = _neighbors8(point[0], point[1], h, w, ink)
        nbrs[point] = nearby
        deg[point] = len(nearby)

    used_edges = set()
    paths = []

    def walk(start, nxt):
        path = [start, nxt]
        used_edges.add(_edge_key(start, nxt))
        prev, cur = start, nxt
        while True:
            cand = [
                n for n in nbrs[cur]
                if n != prev and _edge_key(cur, n) not in used_edges
            ]
            if len(cand) != 1:
                break
            nxt = cand[0]
            used_edges.add(_edge_key(cur, nxt))
            path.append(nxt)
            prev, cur = cur, nxt
            if deg[cur] != 2:
                break
        return path

    def flush(path):
        if len(path) < 2:
            return
        pts = np.array([[[p[1], p[0]]] for p in path], dtype=np.int32)
        if cv2.arcLength(pts, False) >= float(min_length):
            paths.append(pts)

    for point in coords:
        if deg[point] != 1:
            continue
        for n in nbrs[point]:
            if _edge_key(point, n) not in used_edges:
                flush(walk(point, n))

    for point in coords:
        if deg[point] < 3:
            continue
        for n in nbrs[point]:
            if _edge_key(point, n) not in used_edges:
                flush(walk(point, n))

    for point in coords:
        for n in nbrs[point]:
            if _edge_key(point, n) not in used_edges:
                flush(walk(point, n))

    log_info(f"中心线 {len(paths)} 条")
    return paths


def _polyline_normals(points):
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    tangents = np.zeros((n, 2), dtype=np.float64)
    if n == 0:
        return tangents
    if n == 1:
        tangents[0] = (1.0, 0.0)
    else:
        tangents[0] = pts[1] - pts[0]
        tangents[-1] = pts[-1] - pts[-2]
        if n > 2:
            tangents[1:-1] = pts[2:] - pts[:-2]
        norms = np.linalg.norm(tangents, axis=1, keepdims=True)
        np.divide(tangents, norms, out=tangents, where=norms > 1e-6)
        tangents[(norms <= 1e-6).ravel()] = (1.0, 0.0)
    return np.column_stack((-tangents[:, 1], tangents[:, 0]))


def end_heavy_envelope(n, taper=0.18, mid=0.15):
    """起收笔顿：两端粗、中间细（粗-细-粗）。"""
    n = int(n)
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    if n < 3:
        return np.ones(n, dtype=np.float64)
    taper = float(np.clip(taper, 0.05, 0.45))
    head = max(1, int(round(n * taper)))
    head = min(head, max(1, n // 2))
    mid = float(np.clip(mid, 0.0, 1.0))
    env = np.full(n, mid, dtype=np.float64)
    u = np.arange(head, dtype=np.float64) / float(head)
    s = u * u * (3.0 - 2.0 * u)
    head_vals = 1.0 - (1.0 - mid) * s
    env[:head] = head_vals
    env[-head:] = head_vals[::-1]
    return env


def _sample_radius(points, dist):
    h, w = dist.shape[:2]
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    xs = np.clip(np.rint(pts[:, 0]), 0, w - 1).astype(np.intp)
    ys = np.clip(np.rint(pts[:, 1]), 0, h - 1).astype(np.intp)
    return dist[ys, xs].astype(np.float64)


def _mask_to_polylines(points, mask, min_len=3):
    segs = []
    start = None
    for i, keep in enumerate(mask):
        if keep and start is None:
            start = i
        elif not keep and start is not None:
            if i - start >= min_len:
                segs.append(points[start:i].reshape(-1, 1, 2).astype(np.int32))
            start = None
    if start is not None and len(points) - start >= min_len:
        segs.append(points[start:].reshape(-1, 1, 2).astype(np.int32))
    return segs


def _is_open_stroke(points):
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return False
    return float(np.linalg.norm(pts[0] - pts[-1])) > 2.0


def expand_taper_paths(
    contours,
    binary=None,
    image_shape=None,
    max_layers=3,
    taper=0.18,
    spacing=1.0,
):
    """
    把中心线扩成可变密度的重叠折线：粗处多层，细处只留中线。
    默认粗-细-粗（起收顿笔）；若有二值图，会叠上线稿实测宽度。
    """
    if not contours:
        return contours
    max_layers = max(1, int(max_layers))
    if max_layers <= 1:
        return list(contours)

    open_strokes = []
    out = []
    skipped_closed = 0
    for contour in contours:
        pts = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
        if len(pts) < 2:
            continue
        if not _is_open_stroke(pts):
            skipped_closed += 1
            out.append(np.asarray(contour).reshape(-1, 1, 2).astype(np.int32))
            continue
        open_strokes.append(pts)

    if not open_strokes:
        if skipped_closed:
            log_info("起收笔路径需要开口中心线，封闭外框已原样保留")
        return out

    if binary is None:
        if image_shape is None:
            return list(contours)
        h, w = image_shape[:2]
        binary = np.zeros((h, w), dtype=np.uint8)
        cv2.polylines(binary, [np.asarray(p, dtype=np.int32) for p in open_strokes], False, 255, 3)
    dist = cv2.distanceTransform((binary > 0).astype(np.uint8), cv2.DIST_L2, 3)

    for pts in open_strokes:
        measured = _sample_radius(pts, dist)
        p90 = max(float(np.percentile(measured, 90)) if len(measured) else 0.6, 0.6)
        meas_n = np.clip(measured / p90, 0.2, 1.0)
        env = end_heavy_envelope(len(pts), taper=taper)
        thick = np.clip(0.4 * meas_n + 0.6 * env, 0.0, 1.0)
        layers = np.clip(
            np.rint(1.0 + thick * (max_layers - 1)), 1, max_layers
        ).astype(np.int32)
        normals = _polyline_normals(pts)
        out.append(pts.reshape(-1, 1, 2).astype(np.int32))
        for k in range(1, max_layers):
            keep = layers >= (k + 1)
            offset = float(k) * float(spacing)
            for sign in (1.0, -1.0):
                shifted = pts + normals * (offset * sign)
                out.extend(_mask_to_polylines(shifted, keep))

    log_info(f"起收笔路径 {len(contours)} → {len(out)} 条")
    return out


def thin_contours_to_skeleton(contours, image_shape):
    """将轮廓细化为单线骨架，再沿中心线跟踪。"""
    try:
        h, w = image_shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)

        for contour in contours:
            cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

        new_contours = trace_centerlines(mask, min_length=4)
        if not new_contours:
            return contours
        log_info(f"细化 {len(contours)} → {len(new_contours)} 条")
        return new_contours
    except Exception as e:
        log_error("细化失败", e)
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
        log_info(f"去回头路 {total_removed} 处")
    
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
    log_info(f"跳点 {original_points} → {skipped_points}（-{reduction_percent:.0f}%）")
    
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
