"""
Управление Selenium WebDriver с анти-детект техниками
"""

import time
import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from selenium_stealth import stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

try:
    from undetected_chromedriver import Chrome
    HAS_UC = True
except ImportError:
    HAS_UC = False
    Chrome = webdriver.Chrome

from src.config.settings import Settings

logger = logging.getLogger(__name__)


class SeleniumManager:
    """
    Менеджер для работы с Selenium WebDriver.
    Включает продвинутые техники обхода детекции автоматизации.
    """

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None

    def create_driver(self, headless: bool = True) -> webdriver.Chrome:
        """
        Создает Chrome WebDriver с анти-детект настройками.

        Args:
            headless: Запускать в headless режиме

        Returns:
            Настроенный WebDriver
        """
        options = self._create_chrome_options(headless, use_uc=HAS_UC)

        try:
            if HAS_UC:
                # Используем undetected-chromedriver (приоритет)
                driver = Chrome(options=options, version_main=Settings.CHROME_VERSION)
                logger.info("Создан undetected-chromedriver")
            else:
                # Fallback на обычный ChromeDriver
                driver = webdriver.Chrome(options=options)
                logger.warning("undetected-chromedriver недоступен, используется обычный ChromeDriver")

            # Применяем selenium-stealth если доступен
            if HAS_STEALTH:
                self._apply_stealth(driver)
                logger.info("Применен selenium-stealth")
            else:
                logger.warning("selenium-stealth недоступен")

            # Дополнительные анти-детект скрипты
            self._apply_anti_detect_scripts(driver)

            self.driver = driver
            return driver

        except Exception as e:
            logger.error(f"Ошибка создания WebDriver: {e}")
            raise

    def _create_chrome_options(self, headless: bool, use_uc: bool = False) -> ChromeOptions:
        """
        Создает опции Chrome с анти-детект настройками.

        Args:
            headless: Headless режим
            use_uc: Используется ли undetected-chromedriver

        Returns:
            Настроенные опции
        """
        options = ChromeOptions()

        # Базовые опции
        if headless:
            options.add_argument("--headless=new")

        # Флаги для стабильности
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        # Не используем --single-process так как это вызывает ERR_TUNNEL_CONNECTION_FAILED

        # Используем мобильный User-Agent для обхода CloudFlare
        options.add_argument(f"--user-agent={Settings.USER_AGENT_MOBILE}")
        options.add_argument("--log-level=3")

        # Экспериментальные опции только для обычного ChromeDriver
        # undetected-chromedriver управляет этими опциями сам
        if not use_uc:
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2
            })

        return options

    def _apply_stealth(self, driver: webdriver.Chrome):
        """
        Применяет selenium-stealth для обхода детекции.

        Args:
            driver: WebDriver
        """
        stealth(driver,
            languages=["ru-RU", "ru", "en-US", "en"],
            vendor="Google Inc.",
            platform="Linux armv8l",  # Android platform
            webgl_vendor="ARM",  # Mobile GPU
            renderer="Mali-G77 MP11",  # Android GPU
            fix_hairline=True,
        )

    def _apply_anti_detect_scripts(self, driver: webdriver.Chrome):
        """
        Применяет JavaScript скрипты для обхода детекции.

        Args:
            driver: WebDriver
        """
        # Убираем navigator.webdriver
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Переопределяем permissions
        driver.execute_script("""
            Object.defineProperty(navigator, 'permissions', {
                get: () => ({
                    query: () => Promise.resolve({state: 'granted'})
                })
            });
        """)

        # Переопределяем plugins
        driver.execute_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

    def navigate_to_url(self, url: str, wait_for_load: bool = True) -> bool:
        """
        Переходит по URL с обработкой ошибок.

        Args:
            url: URL для перехода
            wait_for_load: Ждать полной загрузки страницы

        Returns:
            True если успешно, False если ошибка

        Raises:
            ValueError: Если driver не инициализирован
        """
        if not self.driver:
            raise ValueError("WebDriver не инициализирован. Вызовите create_driver() сначала.")

        try:
            logger.info(f"Переход по URL: {url}")
            self.driver.get(url)

            if wait_for_load:
                time.sleep(3)  # Базовая задержка
                return self.wait_for_page_load()

            return True

        except WebDriverException as e:
            logger.error(f"Ошибка перехода по URL {url}: {e}")
            return False

    def wait_for_page_load(self, timeout: int = None) -> bool:
        """
        Ожидает полной загрузки страницы и обхода антибот-защиты.

        Args:
            timeout: Максимальное время ожидания в секундах

        Returns:
            True если страница загружена, False если превышен таймаут
        """
        if timeout is None:
            timeout = 10  # Сокращаем таймаут для быстрого fallback на Playwright

        # Ждем загрузки
        time.sleep(3)

        # Проверяем блокировку один раз
        if self.is_page_blocked():
            logger.warning("Обнаружена блокировка - требуется переключение на Playwright")
            return False

        logger.info("Страница загружена успешно")
        return True

    def is_page_blocked(self) -> bool:
        """
        Проверяет признаки блокировки страницы.

        Returns:
            True если страница заблокирована
        """
        if not self.driver:
            return False

        try:
            page_source = self.driver.page_source.lower()

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
                if pattern in page_source:
                    logger.warning(f"Обнаружен индикатор блокировки: {pattern}")
                    return True

            # Проверка на пустую страницу
            if len(page_source) < 1000:
                logger.warning("Страница слишком короткая (возможно блокировка)")
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
        if not self.driver:
            return None

        try:
            # Метод 1: Из <pre> тега (API возвращает JSON в <pre>)
            try:
                pre_element = self.driver.find_element(By.TAG_NAME, 'pre')
                json_text = pre_element.text
                if json_text and len(json_text) > 10:
                    logger.debug("JSON извлечен из <pre> тега")
                    return json_text
            except:
                pass

            # Метод 2: Поиск JSON в page_source
            page_source = self.driver.page_source
            start = page_source.find('{')

            if start != -1:
                # Ищем закрывающую скобку
                brace_count = 0
                for i, char in enumerate(page_source[start:], start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_text = page_source[start:i+1]
                            logger.debug("JSON извлечен из page_source")
                            return json_text

            logger.warning("JSON не найден на странице")
            return None

        except Exception as e:
            logger.error(f"Ошибка извлечения JSON: {e}")
            return None

    def close(self):
        """Закрывает WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver закрыт")
            except Exception as e:
                logger.error(f"Ошибка закрытия WebDriver: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        """Context manager вход"""
        self.create_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager выход"""
        self.close()
