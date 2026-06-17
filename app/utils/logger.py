import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


_settings = None


def _get_settings():
    global _settings
    if _settings is not None:
        return _settings
    try:
        from ..config import settings as cfg
        _settings = cfg
        return _settings
    except Exception as e:
        _settings = type('MockSettings', (), {
            'LOG_LEVEL': 'INFO',
            'APP_DEBUG': False,
            'LOG_FILE': './logs/app.log',
            'LOG_MAX_BYTES': 10 * 1024 * 1024,
            'LOG_BACKUP_COUNT': 10,
        })()
        print(f"[WARN] Using mock settings for logger: {e}")
        return _settings


_logger_instance: Optional[logging.Logger] = None


def setup_logger(name: str = None) -> logging.Logger:
    global _logger_instance
    settings = _get_settings()

    logger_obj = logging.getLogger(name or "ops_monitor")
    logger_obj.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    if logger_obj.handlers and _logger_instance is not None:
        return logger_obj

    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(process)d | %(thread)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    has_console = any(isinstance(h, logging.StreamHandler) for h in logger_obj.handlers)
    if not has_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        console_handler.setLevel(logging.DEBUG if settings.APP_DEBUG else logging.INFO)
        logger_obj.addHandler(console_handler)

    try:
        log_dir = os.path.dirname(settings.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        has_file = any(isinstance(h, RotatingFileHandler) for h in logger_obj.handlers)
        if not has_file:
            file_handler = RotatingFileHandler(
                settings.LOG_FILE,
                maxBytes=settings.LOG_MAX_BYTES,
                backupCount=settings.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(log_format)
            file_handler.setLevel(logging.DEBUG)
            logger_obj.addHandler(file_handler)
    except Exception as e:
        print(f"[WARN] Failed to setup file logger: {e}")

    logger_obj.propagate = False
    _logger_instance = logger_obj
    return logger_obj


def get_logger(name: str = None) -> logging.Logger:
    return setup_logger(name)


logger = setup_logger()
