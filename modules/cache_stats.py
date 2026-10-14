"""边图推理缓存命中统计：Anime2Sketch / LineartAnime 预览缓存命中率日志。"""

from __future__ import annotations

from typing import Dict, Tuple

from modules.app_logger import log_info


class EdgeCacheStats:
    """按方法统计边图缓存命中 / 未命中，生成累计命中率日志行。"""

    def __init__(self) -> None:
        self._hits: Dict[str, int] = {}
        self._misses: Dict[str, int] = {}

    def counts(self, method: str) -> Tuple[int, int]:
        """返回 (命中次数, 未命中次数)。"""
        return self._hits.get(method, 0), self._misses.get(method, 0)

    def hit_rate(self, method: str) -> float:
        hit, miss = self.counts(method)
        total = hit + miss
        return (hit / total) if total else 0.0

    def summary(self, method: str) -> str:
        """如 `Anime2Sketch 累计 2/3 命中（67%）`。"""
        hit, miss = self.counts(method)
        total = hit + miss
        rate = (100.0 * hit / total) if total else 0.0
        return f"{method} 累计 {hit}/{total} 命中（{rate:.0f}%）"

    def record_hit(self, method: str) -> str:
        """记一次命中并写日志，返回日志行。"""
        self._hits[method] = self._hits.get(method, 0) + 1
        line = f"推理缓存命中 {method}｜{self.summary(method)}"
        log_info(line)
        return line

    def record_miss(self, method: str) -> str:
        """记一次未命中（重新推理）并写日志，返回日志行。"""
        self._misses[method] = self._misses.get(method, 0) + 1
        line = f"推理缓存未命中 {method}，重新推理｜{self.summary(method)}"
        log_info(line)
        return line
