"""
Управление Playwright для обхода анти-бот защиты
"""

import time
import logging
from typing import Optional

try:
    from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Browser = None
    Page = None

from src.config.settings import Settings

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """
    Менеджер для работы с Playwright.
    Используется как альтернатива Selenium для обхода блокировок.
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None

    def create_browser(self, headless: bool = True) -> Page:
        """
        Создает браузер Playwright с анти-детект настройками.

        Args:
            headless: Запускать в headless режиме

        Returns:
            Настроенная страница (Page)

        Raises:
            ImportError: Если Playwright не установлен
        """
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "Playwright не установлен. Установите: pip install playwright && playwright install chromium"
            )

        try:
            # Запуск Playwright
            self.playwright = sync_playwright().start()

            # Создание браузера с анти-детект настройками
            self.browser = self.playwright.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )

            # Создание контекста с реалистичными настройками
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=Settings.USER_AGENT,
                locale='ru-RU',
                timezone_id='Europe/Moscow',
                permissions=['geolocation'],
                color_scheme='light',
                extra_http_headers={
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                }
            )

            # Создание страницы
            self.page = self.context.new_page()

            # Применяем дополнительные анти-детект скрипты
            self._apply_anti_detect_scripts()

            logger.info("Создан Playwright браузер")
            return self.page

        except Exception as e:
            logger.error(f"Ошибка создания Playwright браузера: {e}")
            self.close()
            raise

    def _apply_anti_detect_scripts(self):
        """Применяет JavaScript скрипты для обхода детекции"""
        if not self.page:
            return

        # Скрываем webdriver
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Переопределяем permissions
        self.page.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        # Добавляем плагины
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

    def navigate_to_url(self, url: str, wait_for_load: bool = True, timeout: int = None) -> bool:
        """
        Переходит по URL с обработкой ошибок.

        Args:
            url: URL для перехода
            wait_for_load: Ждать полной загрузки страницы
            timeout: Таймаут в миллисекундах

        Returns:
            True если успешно, False если ошибка
        """
        if not self.page:
            raise ValueError("Браузер не инициализирован. Вызовите create_browser() сначала.")

        if timeout is None:
            timeout = Settings.PAGE_LOAD_TIMEOUT * 1000  # Convert to ms

        try:
            logger.info(f"Playwright: Переход по URL: {url}")

            # Переход с увеличенным таймаутом
            self.page.goto(url, wait_until='domcontentloaded', timeout=timeout)

            if wait_for_load:
                # Дополнительное ожидание для загрузки динамического контента
                time.sleep(3)

                # Ждем загрузки сетевых запросов
                self.page.wait_for_load_state('networkidle', timeout=timeout)

            return not self.is_page_blocked()

        except PlaywrightTimeout:
            logger.error(f"Таймаут при переходе по URL: {url}")
            return False
        except Exception as e:
            logger.error(f"Ошибка перехода по URL {url}: {e}")
            return False

    def is_page_blocked(self) -> bool:
        """
        Проверяет признаки блокировки страницы.

        Returns:
            True если страница заблокирована
        """
        if not self.page:
            return False

        try:
            content = self.page.content().lower()

            # Индикаторы блокировки (более специфичные паттерны)
            block_patterns = [
                "cloudflare",
                "ddos-guard",
                "доступ ограничен",
                "access denied",
                "checking your browser",
                "just a moment",
                "captcha",
                "подтвердите, что вы не робот",
                "are you a robot",
                "verify you are human",
                "bot detected",
                "security check",
                "проверка безопасности",
            ]

            for pattern in block_patterns:
                if pattern in content:
                    logger.warning(f"Playwright: Обнаружен индикатор блокировки: {pattern}")
                    return True

            # Проверка на пустую страницу
            if len(content) < 1000:
                logger.warning("Playwright: Страница слишком короткая")
                return True

            return False

        except Exception as e:
            logger.error(f"Ошибка проверки блокировки: {e}")
            return True

    def extract_json_from_page(self) -> Optional[str]:
        """
        Извлекает JSON из страницы API.

        Returns:
            JSON строка или None если не найдено
        """
        if not self.page:
            return None

        try:
            # Метод 1: Из <pre> тега
            try:
                pre_content = self.page.locator('pre').first.inner_text()
                if pre_content and len(pre_content) > 10:
                    logger.debug("Playwright: JSON извлечен из <pre> тега")
                    return pre_content
            except:
                pass

            # Метод 2: Из page content
            content = self.page.content()
            start = content.find('{')

            if start != -1:
                brace_count = 0
                for i, char in enumerate(content[start:], start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_text = content[start:i+1]
                            logger.debug("Playwright: JSON извлечен из content")
                            return json_text

            logger.warning("Playwright: JSON не найден на странице")
            return None

        except Exception as e:
            logger.error(f"Ошибка извлечения JSON: {e}")
            return None

    def wait_for_timeout(self, seconds: float):
        """Ожидание в секундах"""
        if self.page:
            self.page.wait_for_timeout(seconds * 1000)

    def close(self):
        """Закрывает браузер Playwright"""
        try:
            if self.page:
                self.page.close()
                self.page = None
                logger.debug("Playwright: страница закрыта")

            if self.context:
                self.context.close()
                self.context = None
                logger.debug("Playwright: контекст закрыт")

            if self.browser:
                self.browser.close()
                self.browser = None
                logger.debug("Playwright: браузер закрыт")

            if self.playwright:
                self.playwright.stop()
                self.playwright = None
                logger.info("Playwright остановлен")

        except Exception as e:
            logger.error(f"Ошибка закрытия Playwright: {e}")

    def __enter__(self):
        """Context manager вход"""
        self.create_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager выход"""
        self.close()
