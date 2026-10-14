"""路径规划：统一识图轮廓到绘制顺序。

不在模块顶层导入 drawing_engine，避免循环依赖。
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np


def _as_pts(path) -> np.ndarray:
    return np.asarray(path).reshape(-1, 2)


def _path_center(pts: np.ndarray) -> Tuple[float, float]:
    return float(np.mean(pts[:, 0])), float(np.mean(pts[:, 1]))


def order_paths_nearest(paths, start=None) -> List[Any]:
    """最近邻接笔：从 start（默认原点）出发，下一条选最近端点，可翻转。"""
    remaining: List[np.ndarray] = []
    for path in paths or []:
        pts = _as_pts(path)
        if len(pts) == 0:
            continue
        remaining.append(pts.astype(np.float64, copy=False))
    ordered: List[Any] = []
    if start is None:
        current = np.array([0.0, 0.0], dtype=np.float64)
    else:
        current = np.asarray(start, dtype=np.float64).reshape(2)
    while remaining:
        best_i = 0
        best_rev = False
        best_d = float("inf")
        for i, pts in enumerate(remaining):
            d_start = float(np.sum((pts[0] - current) ** 2))
            d_end = float(np.sum((pts[-1] - current) ** 2))
            if d_start < best_d:
                best_d, best_i, best_rev = d_start, i, False
            if d_end < best_d:
                best_d, best_i, best_rev = d_end, i, True
        pts = remaining.pop(best_i)
        if best_rev:
            pts = pts[::-1].copy()
        ordered.append(pts.reshape(-1, 1, 2).astype(np.int32))
        current = pts[-1]
    return ordered


def order_paths_bbox_chunks(paths, cell_size: Optional[float] = None) -> List[Any]:
    """按包围盒中心分块，块内最近邻，块间按中心点最近邻串联。"""
    items: List[Tuple[np.ndarray, float, float]] = []
    for path in paths or []:
        pts = _as_pts(path)
        if len(pts) == 0:
            continue
        cx, cy = _path_center(pts)
        items.append((pts, cx, cy))
    if not items:
        return []
    if len(items) == 1:
        return [items[0][0].reshape(-1, 1, 2).astype(np.int32)]

    xs = [it[1] for it in items]
    ys = [it[2] for it in items]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    if cell_size is None or cell_size <= 0:
        n = len(items)
        grid_n = max(2, int(math.ceil(math.sqrt(max(n, 1) / 4.0))))
        cell_size = span / float(grid_n)

    buckets: dict = {}
    for pts, cx, cy in items:
        gx = int((cx - min_x) // cell_size)
        gy = int((cy - min_y) // cell_size)
        buckets.setdefault((gx, gy), []).append(pts)

    cell_keys = list(buckets.keys())
    cell_centers = {
        k: (
            min_x + (k[0] + 0.5) * cell_size,
            min_y + (k[1] + 0.5) * cell_size,
        )
        for k in cell_keys
    }

    ordered_cells: List[Tuple[int, int]] = []
    remaining_keys = set(cell_keys)
    cur = (0.0, 0.0)
    while remaining_keys:
        best = None
        best_d = float("inf")
        for k in remaining_keys:
            cx, cy = cell_centers[k]
            d = (cx - cur[0]) ** 2 + (cy - cur[1]) ** 2
            if d < best_d:
                best_d, best = d, k
        ordered_cells.append(best)
        remaining_keys.remove(best)
        cur = cell_centers[best]

    result: List[Any] = []
    cursor = np.array([0.0, 0.0], dtype=np.float64)
    for key in ordered_cells:
        chunk = buckets[key]
        ordered_chunk = order_paths_nearest(chunk, start=cursor)
        result.extend(ordered_chunk)
        if ordered_chunk:
            cursor = _as_pts(ordered_chunk[-1])[-1].astype(np.float64)
    return result


def bbox_chunk_grid(contours, cell_size: Optional[float] = None):
    """返回与 order_paths_bbox_chunks 一致的分块网格（仅供预览可视化）。

    返回 (rects, cell)：rects 为覆盖路径中心包围区的 (x0, y0, x1, y1) 列表，
    cell 为实际分块边长（像素）。路径不足 2 条时不分块，返回 ([], 0.0)。
    """
    centers = []
    for path in contours or []:
        pts = _as_pts(path)
        if len(pts) == 0:
            continue
        cx, cy = _path_center(pts)
        centers.append((cx, cy))
    if len(centers) <= 1:
        return [], 0.0

    min_x = min(p[0] for p in centers)
    max_x = max(p[0] for p in centers)
    min_y = min(p[1] for p in centers)
    max_y = max(p[1] for p in centers)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    if cell_size is None or cell_size <= 0:
        n = len(centers)
        grid_n = max(2, int(math.ceil(math.sqrt(max(n, 1) / 4.0))))
        cell = span / float(grid_n)
    else:
        cell = float(cell_size)

    nx = max(1, int(math.ceil((max_x - min_x) / cell)))
    ny = max(1, int(math.ceil((max_y - min_y) / cell)))
    rects = []
    for gy in range(ny):
        for gx in range(nx):
            x0 = min_x + gx * cell
            y0 = min_y + gy * cell
            rects.append((
                int(round(x0)), int(round(y0)),
                int(round(min(x0 + cell, max_x))),
                int(round(min(y0 + cell, max_y))),
            ))
    return rects, cell


def draw_chunk_grid(image, contours, cell_size=None, color=(150, 150, 150), thickness=1):
    """在预览图上画分块网格（淡色）。返回 (image, cell, 格数)；无路径时不画。"""
    rects, cell = bbox_chunk_grid(contours, cell_size=cell_size)
    if image is None or not rects:
        return image, cell, 0
    import cv2

    for x0, y0, x1, y1 in rects:
        cv2.rectangle(image, (x0, y0), (x1, y1), color, thickness, lineType=cv2.LINE_AA)
    return image, cell, len(rects)


def plan_draw_paths(
    contours,
    strategy: str = "bbox_chunks",
    cell_size: Optional[float] = None,
) -> List[Any]:
    """返回按绘制顺序排列的轮廓列表。默认 bbox 分块再最近邻。

    cell_size: 分块边长（像素）。None / <=0 表示按路径数量自动估算。
    """
    if contours is None:
        return []
    name = str(strategy or "bbox_chunks").lower().strip()
    if name in ("nearest", "nn", "greedy"):
        return order_paths_nearest(contours)
    try:
        cs = float(cell_size) if cell_size is not None else None
    except (TypeError, ValueError):
        cs = None
    if cs is not None and cs <= 0:
        cs = None
    return order_paths_bbox_chunks(contours, cell_size=cs)


def estimate_path_stats(contours) -> dict:
    if not contours:
        return {"paths": 0, "points": 0, "avg_points": 0.0}
    points = 0
    for c in contours:
        pts = np.asarray(c).reshape(-1, 2)
        points += len(pts)
    n = len(contours)
    return {
        "paths": n,
        "points": int(points),
        "avg_points": (float(points) / n) if n else 0.0,
    }
