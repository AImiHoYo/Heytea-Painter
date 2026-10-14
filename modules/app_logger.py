"""
会话日志：正常运行写入 logs/run_*.log，报错写入 logs/error_*.log。
终端输出仍保留，模块里的 print 也会进 run 日志。
"""

from __future__ import annotations

import faulthandler
import logging
import os
import signal
import sys
import threading
import traceback
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

LOGGER_NAME = "heytea"
_configured = False
_run_log_path = ""
_error_log_path = ""
_fault_fp = None


class _StreamToLogger:
    """把 stdout/stderr 镜像到 logger，同时继续打到原终端。"""

    def __init__(self, logger: logging.Logger, level: int, original):
        self.logger = logger
        self.level = level
        self.original = original
        self._buf = ""

    def write(self, message):
        if self.original is not None:
            try:
                self.original.write(message)
                self.original.flush()
            except Exception:
                pass
        if not message:
            return
        self._buf += message
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            text = line.rstrip("\r")
            if text:
                self.logger.log(self.level, text)
                for handler in self.logger.handlers:
                    try:
                        handler.flush()
                    except Exception:
                        pass

    def flush(self):
        if self._buf.strip():
            self.logger.log(self.level, self._buf.rstrip("\r"))
            self._buf = ""
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        if self.original is None:
            return False
        return bool(getattr(self.original, "isatty", lambda: False)())


def setup_logging():
    """初始化 logs 目录和本次会话的两个日志文件。重复调用是安全的。"""
    global _configured, _run_log_path, _error_log_path
    if _configured:
        return _run_log_path, _error_log_path

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _run_log_path = os.path.join(LOG_DIR, f"run_{stamp}.log")
    _error_log_path = os.path.join(LOG_DIR, f"error_{stamp}.log")

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    run_handler = logging.FileHandler(_run_log_path, encoding="utf-8")
    run_handler.setLevel(logging.DEBUG)
    run_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(_error_log_path, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.addHandler(run_handler)
    logger.addHandler(error_handler)

    sys.stdout = _StreamToLogger(logger, logging.INFO, sys.__stdout__)
    sys.stderr = _StreamToLogger(logger, logging.ERROR, sys.__stderr__)

    sys.excepthook = _handle_uncaught
    if hasattr(threading, "excepthook"):
        threading.excepthook = _handle_thread_exception

    global _fault_fp
    _fault_fp = open(_error_log_path, "a", encoding="utf-8")
    faulthandler.enable(file=_fault_fp, all_threads=True)
    for sig in (getattr(signal, "SIGTRAP", None), getattr(signal, "SIGABRT", None)):
        if sig is None:
            continue
        try:
            faulthandler.register(sig, file=_fault_fp, all_threads=True)
        except Exception:
            pass

    logger.info("日志已启动")
    logger.info("运行日志: %s", _run_log_path)
    logger.info("错误日志: %s", _error_log_path)
    logger.info("已启用原生崩溃转储（SIGTRAP/SIGABRT 会写入错误日志）")
    _configured = True
    return _run_log_path, _error_log_path


def get_logger():
    if not _configured:
        setup_logging()
    return logging.getLogger(LOGGER_NAME)


def flush_logs():
    logger = logging.getLogger(LOGGER_NAME)
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass


def log_debug(message: str):
    """开发诊断，只写文件，不进界面控制台。"""
    get_logger().debug(message)


def log_info(message: str):
    get_logger().info(message)
    flush_logs()


def log_warning(message: str):
    get_logger().warning(message)


def log_error(message: str, exc: BaseException | None = None):
    logger = get_logger()
    if exc is not None:
        logger.error("%s\n%s", message, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    else:
        logger.error(message)
    flush_logs()


def run_log_path():
    return _run_log_path


def error_log_path():
    return _error_log_path


def _handle_uncaught(exc_type, exc, tb):
    get_logger().error(
        "未捕获异常\n%s",
        "".join(traceback.format_exception(exc_type, exc, tb)),
    )
    if sys.__stderr__ is not None:
        traceback.print_exception(exc_type, exc, tb, file=sys.__stderr__)


def _handle_thread_exception(args):
    _handle_uncaught(args.exc_type, args.exc_value, args.exc_traceback)
