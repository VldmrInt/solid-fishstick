"""
Настройка логирования
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from src.config.settings import Settings


def setup_logger(name: str = 'ozon_parser', log_file: Path = None) -> logging.Logger:
    """
    Настраивает логгер с ротацией файлов.

    Args:
        name: Имя логгера
        log_file: Путь к файлу лога (по умолчанию из Settings)

    Returns:
        Настроенный Logger
    """
    if log_file is None:
        log_file = Settings.LOG_FILE

    # Создаем форматтер
    formatter = logging.Formatter(
        Settings.LOG_FORMAT,
        datefmt=Settings.LOG_DATE_FORMAT
    )

    # Файловый handler с ротацией (макс 10MB, 5 файлов)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, Settings.LOG_LEVEL))

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)  # INFO уровень для консоли

    # Настройка корневого логгера для всех модулей
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, Settings.LOG_LEVEL))
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Настройка основного логгера приложения
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, Settings.LOG_LEVEL))

    return logger
