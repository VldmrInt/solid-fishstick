"""
Конфигурация парсера Ozon
"""

import json
import re
from pathlib import Path
from typing import Optional


class Settings:
    """Централизованные настройки приложения"""

    # Пути
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    CONFIG_FILE = PROJECT_ROOT / 'config.json'
    ARCHIVE_DIR = PROJECT_ROOT / 'archive'
    OUTPUT_DIR = PROJECT_ROOT / 'output'
    LOG_FILE = PROJECT_ROOT / 'parser.log'

    # API Ozon
    OZON_API_BASE = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
    OZON_BASE_URL = "https://www.ozon.ru"

    # Параметры Chrome
    CHROME_VERSION = 142
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'

    # Таймауты (в секундах)
    PAGE_LOAD_TIMEOUT = 30
    API_REQUEST_TIMEOUT = 20
    ANTI_BOT_WAIT_TIMEOUT = 60
    RETRY_DELAY = 5

    # Параметры парсинга
    MAX_RETRIES = 3
    REQUEST_DELAY_MIN = 2
    REQUEST_DELAY_MAX = 5

    # Параметры многопоточности
    MAX_WORKERS = 3

    # Логирование
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    @classmethod
    def load_config(cls) -> dict:
        """
        Загружает конфигурацию из config.json

        Returns:
            dict с конфигурацией

        Raises:
            FileNotFoundError: если config.json не найден
            ValueError: если отсутствуют обязательные поля
        """
        if not cls.CONFIG_FILE.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {cls.CONFIG_FILE}")

        with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if 'seller_url' not in config:
            raise ValueError("В config.json отсутствует обязательное поле 'seller_url'")

        return config

    @classmethod
    def get_seller_id(cls, seller_url: str) -> Optional[str]:
        """
        Извлекает ID продавца из URL

        Args:
            seller_url: URL магазина

        Returns:
            ID продавца или None
        """
        # Паттерны для извлечения ID:
        # 1. /seller/magazin-123456/
        # 2. ?miniapp=seller_123456
        # 3. /seller_123456

        patterns = [
            r'/seller/[^/]+-(\d+)',
            r'seller_(\d+)',
            r'/seller/(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, seller_url)
            if match:
                return match.group(1)

        return None

    @classmethod
    def ensure_directories(cls):
        """Создает необходимые директории"""
        cls.ARCHIVE_DIR.mkdir(exist_ok=True)
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
