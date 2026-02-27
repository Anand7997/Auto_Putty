"""
Web Automation Healer Module

This module provides healing mechanisms for web automation tests using Selenium and Playwright.
It implements various healing strategies to make tests more robust and resilient to common web application issues.

Healing Mechanisms:
1. Stale Element Reference Healer - Automatically re-locates elements when they become stale
2. Element Obscured Healer - Handles elements obscured by overlays, popups, etc.
3. Dynamic Wait Healer - Implements intelligent polling for dynamic content
4. Navigation and Page Load Healer - Handles navigation timeouts and retries
5. Selector Fallback Healer - Provides fallback selectors when primary selectors fail
6. Iframe Healer - Automatically handles iframe context switching

Usage:
    from healer import WebHealer

    # For Selenium
    healer = WebHealer(driver=selenium_driver, framework='selenium')
    healed_element = healer.find_element_with_healing(By.XPATH, "//button[@id='submit']")

    # For Playwright
    healer = WebHealer(page=playwright_page, framework='playwright')
    healed_locator = healer.find_locator_with_healing("xpath=//button[@id='submit']")
"""

import time
import logging
import re
from typing import Union, Optional, Callable, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebHealer:
    """
    Main healer class that provides healing mechanisms for web automation.
    Supports both Selenium WebDriver and Playwright.
    """

    def __init__(self, driver=None, page=None, framework='selenium', max_retries=3, healing_enabled=True):
        """
        Initialize the healer.

        Args:
            driver: Selenium WebDriver instance
            page: Playwright Page instance
            framework: 'selenium' or 'playwright'
            max_retries: Maximum number of healing attempts
            healing_enabled: Whether healing is enabled
        """
        self.driver = driver
        self.page = page
        self.framework = framework.lower()
        self.max_retries = max_retries
        self.healing_enabled = healing_enabled

        # Validate framework
        if self.framework not in ['selenium', 'playwright']:
            raise ValueError(f"Unsupported framework: {framework}. Must be 'selenium' or 'playwright'")

        # Validate that we have the right driver/page
        if self.framework == 'selenium' and not self.driver:
            raise ValueError("Selenium framework requires a driver instance")
        if self.framework == 'playwright' and not self.page:
            raise ValueError("Playwright framework requires a page instance")

        logger.info(f"WebHealer initialized for {framework} with healing {'enabled' if healing_enabled else 'disabled'}")

    def find_element_with_healing(self, by: str, selector: str, timeout: int = 10) -> Any:
        """
        Find element with healing mechanisms applied.

        Args:
            by: Locator strategy (for Selenium)
            selector: Selector string
            timeout: Timeout in seconds

        Returns:
            Element/Locator object
        """
        if not self.healing_enabled:
            return self._find_element_basic(by, selector, timeout)

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Healing attempt {attempt + 1} for selector: {selector}")

                # Try basic find first
                element = self._find_element_basic(by, selector, timeout)

                # Apply healing mechanisms
                element = self._apply_element_healing(element, selector)

                return element

            except Exception as e:
                last_exception = e
                logger.warning(f"Healing attempt {attempt + 1} failed: {str(e)}")

                # Wait before retry (exponential backoff)
                if attempt < self.max_retries - 1:
                    time.sleep(0.5 * (2 ** attempt))

        # All healing attempts failed
        logger.error(f"All healing attempts failed for selector: {selector}")
        raise last_exception

    def find_locator_with_healing(self, selector: str, timeout: int = 10) -> Any:
        """
        Find locator with healing mechanisms (Playwright version).

        Args:
            selector: Playwright selector string
            timeout: Timeout in seconds

        Returns:
            Playwright Locator object
        """
        if not self.healing_enabled:
            return self._find_locator_basic(selector, timeout)

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Healing attempt {attempt + 1} for selector: {selector}")

                # Try basic find first
                locator = self._find_locator_basic(selector, timeout)

                # Apply healing mechanisms
                locator = self._apply_locator_healing(locator, selector)

                return locator

            except Exception as e:
                last_exception = e
                logger.warning(f"Healing attempt {attempt + 1} failed: {str(e)}")

                # Wait before retry (exponential backoff)
                if attempt < self.max_retries - 1:
                    time.sleep(0.5 * (2 ** attempt))

        # All healing attempts failed
        logger.error(f"All healing attempts failed for selector: {selector}")
        raise last_exception

    def click_with_healing(self, element=None, locator=None, selector=None, timeout: int = 10) -> bool:
        """
        Click element/locator with healing mechanisms.

        Args:
            element: Selenium element (mutually exclusive with locator)
            locator: Playwright locator (mutually exclusive with element)
            selector: Selector string if element/locator not provided
            timeout: Timeout in seconds

        Returns:
            True if click successful
        """
        if element and self.framework == 'selenium':
            return self._click_element_with_healing(element, selector)
        elif locator and self.framework == 'playwright':
            return self._click_locator_with_healing(locator, selector)
        elif selector:
            if self.framework == 'selenium':
                element = self.find_element_with_healing(By.XPATH, selector, timeout)
                return self._click_element_with_healing(element, selector)
            else:
                locator = self.find_locator_with_healing(f"xpath={selector}", timeout)
                return self._click_locator_with_healing(locator, selector)
        else:
            raise ValueError("Must provide either element/locator or selector")

    def type_with_healing(self, text: str, element=None, locator=None, selector=None, timeout: int = 10) -> bool:
        """
        Type text with healing mechanisms.

        Args:
            text: Text to type
            element: Selenium element
            locator: Playwright locator
            selector: Selector string
            timeout: Timeout in seconds

        Returns:
            True if typing successful
        """
        if element and self.framework == 'selenium':
            return self._type_element_with_healing(element, text, selector)
        elif locator and self.framework == 'playwright':
            return self._type_locator_with_healing(locator, text, selector)
        elif selector:
            if self.framework == 'selenium':
                element = self.find_element_with_healing(By.XPATH, selector, timeout)
                return self._type_element_with_healing(element, text, selector)
            else:
                locator = self.find_locator_with_healing(f"xpath={selector}", timeout)
                return self._type_locator_with_healing(locator, text, selector)
        else:
            raise ValueError("Must provide either element/locator or selector")

    def navigate_with_healing(self, url: str, timeout: int = 30) -> bool:
        """
        Navigate to URL with healing mechanisms.

        Args:
            url: URL to navigate to
            timeout: Navigation timeout in seconds

        Returns:
            True if navigation successful
        """
        if not self.healing_enabled:
            return self._navigate_basic(url, timeout)

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Navigation healing attempt {attempt + 1} for URL: {url}")
                success = self._navigate_basic(url, timeout)

                # Verify page loaded successfully
                if self._verify_page_load():
                    logger.info("Navigation successful with page load verification")
                    return True
                else:
                    raise Exception("Page load verification failed")

            except Exception as e:
                last_exception = e
                logger.warning(f"Navigation attempt {attempt + 1} failed: {str(e)}")

                # Wait before retry
                if attempt < self.max_retries - 1:
                    time.sleep(2 * (attempt + 1))

        logger.error(f"All navigation healing attempts failed for URL: {url}")
        raise last_exception

    # ============================================================================
    # BASIC OPERATIONS (Framework-specific implementations)
    # ============================================================================

    def _find_element_basic(self, by: str, selector: str, timeout: int = 10):
        """Basic element finding without healing."""
        if self.framework != 'selenium':
            raise ValueError("Basic element finding only supported for Selenium")

        wait = WebDriverWait(self.driver, timeout)
        return wait.until(EC.presence_of_element_located((by, selector)))

    def _find_locator_basic(self, selector: str, timeout: int = 10):
        """Basic locator finding without healing."""
        if self.framework != 'playwright':
            raise ValueError("Basic locator finding only supported for Playwright")

        return self.page.locator(selector)

    def _navigate_basic(self, url: str, timeout: int = 30) -> bool:
        """Basic navigation without healing."""
        try:
            if self.framework == 'selenium':
                self.driver.get(url)
                # Wait for page to load
                WebDriverWait(self.driver, timeout).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
            else:  # playwright
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout*1000)

            return True
        except Exception as e:
            logger.error(f"Basic navigation failed: {str(e)}")
            raise e

    # ============================================================================
    # HEALING MECHANISMS IMPLEMENTATION
    # ============================================================================

    def _apply_element_healing(self, element, selector: str):
        """Apply all healing mechanisms to a Selenium element."""
        # 1. Stale Element Reference Healing
        element = self._heal_stale_element(element, selector)

        # 2. Element Obscured Healing
        element = self._heal_obscured_element(element, selector)

        # 3. Dynamic Wait Healing
        element = self._heal_dynamic_wait(element, selector)

        # 4. Iframe Healing
        element = self._heal_iframe_context(element, selector)

        return element

    def _apply_locator_healing(self, locator, selector: str):
        """Apply all healing mechanisms to a Playwright locator."""
        # 1. Element Obscured Healing
        locator = self._heal_obscured_locator(locator, selector)

        # 2. Dynamic Wait Healing
        locator = self._heal_dynamic_wait_locator(locator, selector)

        # 3. Iframe Healing
        locator = self._heal_iframe_context_locator(locator, selector)

        return locator

    # ============================================================================
    # INDIVIDUAL HEALING MECHANISMS
    # ============================================================================

    def _heal_stale_element(self, element, selector: str):
        """Heal stale element references by re-locating the element."""
        try:
            # Test if element is stale by accessing a property
            element.is_displayed()
            return element
        except StaleElementReferenceException:
            logger.info(f"Stale element detected, re-locating: {selector}")
            # Re-locate the element
            return self._find_element_basic(By.XPATH, selector, 5)

    def _heal_obscured_element(self, element, selector: str):
        """Heal elements obscured by overlays, popups, etc."""
        try:
            # Try to click and see if it's intercepted
            element.click()
            return element
        except ElementClickInterceptedException:
            logger.info(f"Element obscured, attempting to heal: {selector}")

            # Strategy 1: Press Escape to dismiss overlays
            try:
                self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                time.sleep(0.5)
                # Try click again
                element.click()
                return element
            except:
                pass

            # Strategy 2: Look for and click common close buttons
            close_selectors = [
                "//button[contains(@class, 'close')]",
                "//button[contains(@aria-label, 'close')]",
                "//div[contains(@class, 'modal')]//button",
                "//div[contains(@class, 'overlay')]//button"
            ]

            for close_selector in close_selectors:
                try:
                    close_buttons = self.driver.find_elements(By.XPATH, close_selector)
                    for button in close_buttons:
                        if button.is_displayed():
                            button.click()
                            time.sleep(0.5)
                            # Try the original click again
                            element.click()
                            return element
                except:
                    continue

            # Strategy 3: Use JavaScript click to bypass overlay
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return element
            except:
                pass

            raise ElementClickInterceptedException(f"Could not heal obscured element: {selector}")

    def _heal_dynamic_wait(self, element, selector: str):
        """Implement dynamic polling for elements that appear after delays."""
        # This is already handled by the retry mechanism in find_element_with_healing
        # Additional dynamic waiting can be implemented here if needed
        return element

    def _heal_iframe_context(self, element, selector: str):
        """Automatically handle iframe context switching."""
        # If element is not found in main context, try iframes
        try:
            element.is_displayed()
            return element
        except (NoSuchElementException, StaleElementReferenceException):
            logger.info(f"Element not found in main context, checking iframes: {selector}")

            # Store original context
            original_window = self.driver.current_window_handle

            try:
                # Find all iframes
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")

                for iframe in iframes:
                    try:
                        # Switch to iframe
                        self.driver.switch_to.frame(iframe)

                        # Try to find element in iframe
                        try:
                            iframe_element = self.driver.find_element(By.XPATH, selector)
                            if iframe_element.is_displayed():
                                logger.info(f"Element found in iframe: {selector}")
                                return iframe_element
                        except:
                            pass

                        # Switch back to parent context
                        self.driver.switch_to.parent_frame()

                    except Exception as e:
                        logger.debug(f"Error checking iframe: {str(e)}")
                        # Make sure we're back in the right context
                        try:
                            self.driver.switch_to.window(original_window)
                        except:
                            pass

                # Switch back to main content if not found
                self.driver.switch_to.default_content()

            except Exception as e:
                logger.warning(f"Error during iframe healing: {str(e)}")
                # Ensure we're back in main context
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass

            # If we reach here, element wasn't found in any iframe
            raise NoSuchElementException(f"Element not found in main context or iframes: {selector}")

    def _heal_obscured_locator(self, locator, selector: str):
        """Heal obscured locators for Playwright with comprehensive strategies."""
        try:
            # Try to click and see if it's intercepted
            locator.click(timeout=5000)
            return locator
        except Exception as e:
            logger.info(f"Locator obscured, attempting Playwright healing: {selector}")

            # Strategy 1: Force click (bypasses visibility checks)
            try:
                locator.click(force=True, timeout=5000)
                logger.info("Force click successful")
                return locator
            except:
                pass

            # Strategy 2: Wait for obscuring elements to disappear
            try:
                # Common overlay selectors for Playwright
                overlay_selectors = [
                    "[data-testid*='modal']",
                    "[data-testid*='popup']",
                    "[data-testid*='overlay']",
                    ".modal-backdrop",
                    ".overlay",
                    "[role='dialog']"
                ]

                for overlay_selector in overlay_selectors:
                    try:
                        overlay = self.page.locator(overlay_selector)
                        if overlay.is_visible(timeout=1000):
                            logger.info(f"Waiting for overlay to disappear: {overlay_selector}")
                            overlay.wait_for(state="hidden", timeout=5000)
                            # Try click again
                            locator.click(timeout=5000)
                            return locator
                    except:
                        continue
            except:
                pass

            # Strategy 3: Scroll into view and retry
            try:
                locator.scroll_into_view_if_needed()
                self.page.wait_for_timeout(500)
                locator.click(timeout=5000)
                return locator
            except:
                pass

            raise Exception(f"Could not heal obscured Playwright locator: {selector}")

    def _heal_dynamic_wait_locator(self, locator, selector: str):
        """Dynamic wait healing for Playwright locators with enhanced waiting."""
        # Playwright has built-in waiting, but we can enhance it
        try:
            # Try with different wait strategies
            strategies = [
                ("visible", 10000),
                ("attached", 5000),
                ("enabled", 3000)
            ]

            for state, timeout in strategies:
                try:
                    locator.wait_for(state=state, timeout=timeout)
                    return locator
                except:
                    continue

            # If all strategies fail, return original locator
            return locator

        except Exception as e:
            logger.debug(f"Dynamic wait healing failed: {str(e)}")
            return locator

    def _heal_iframe_context_locator(self, locator, selector: str):
        """Iframe healing for Playwright locators with frame traversal."""
        # If locator is not found, try iframes
        try:
            # Check if locator is already accessible
            locator.wait_for(state="attached", timeout=2000)
            return locator
        except:
            logger.info(f"Locator not found in main context, checking iframes: {selector}")

            # Get all frames
            frames = self.page.frames

            for frame in frames:
                if frame != self.page:  # Skip main frame
                    try:
                        # Try to find locator in this frame
                        frame_locator = frame.locator(selector)
                        frame_locator.wait_for(state="attached", timeout=2000)

                        if frame_locator.is_visible():
                            logger.info(f"Locator found in iframe: {selector}")
                            return frame_locator
                    except:
                        continue

            # If not found in any iframe, return original locator
            logger.warning(f"Locator not found in main context or iframes: {selector}")
            return locator

    # ============================================================================
    # CLICK HEALING IMPLEMENTATIONS
    # ============================================================================

    def _click_element_with_healing(self, element, selector: str = None) -> bool:
        """Click Selenium element with healing."""
        for attempt in range(self.max_retries):
            try:
                # Apply healing to element first
                if self.healing_enabled:
                    element = self._apply_element_healing(element, selector or "unknown")

                element.click()
                return True

            except StaleElementReferenceException:
                if attempt < self.max_retries - 1:
                    logger.info(f"Stale element on click attempt {attempt + 1}, re-locating")
                    element = self._find_element_basic(By.XPATH, selector, 5)
                else:
                    raise

            except ElementClickInterceptedException:
                if attempt < self.max_retries - 1:
                    logger.info(f"Element obscured on click attempt {attempt + 1}, trying healing")
                    element = self._heal_obscured_element(element, selector)
                else:
                    raise

        return False

    def _click_locator_with_healing(self, locator, selector: str = None) -> bool:
        """Click Playwright locator with comprehensive healing."""
        for attempt in range(self.max_retries):
            try:
                # Apply healing to locator first
                if self.healing_enabled:
                    locator = self._apply_locator_healing(locator, selector or "unknown")

                # Try regular click first
                locator.click(timeout=10000)
                return True

            except Exception as e:
                logger.warning(f"Playwright click attempt {attempt + 1} failed: {str(e)}")

                if attempt < self.max_retries - 1:
                    # Try alternative click strategies
                    try:
                        # Strategy 1: Force click
                        locator.click(force=True, timeout=5000)
                        logger.info("Force click successful")
                        return True
                    except:
                        pass

                    try:
                        # Strategy 2: Click with different position
                        locator.click(position={'x': 5, 'y': 5}, timeout=5000)
                        logger.info("Position click successful")
                        return True
                    except:
                        pass

                    try:
                        # Strategy 3: Scroll and click
                        locator.scroll_into_view_if_needed()
                        self.page.wait_for_timeout(500)
                        locator.click(timeout=5000)
                        logger.info("Scroll and click successful")
                        return True
                    except:
                        pass

                    # Wait before next attempt with exponential backoff
                    time.sleep(0.5 * (2 ** attempt))
                else:
                    raise

        return False

    # ============================================================================
    # TYPE HEALING IMPLEMENTATIONS
    # ============================================================================

    def _type_element_with_healing(self, element, text: str, selector: str = None) -> bool:
        """Type into Selenium element with healing."""
        for attempt in range(self.max_retries):
            try:
                # Apply healing to element first
                if self.healing_enabled:
                    element = self._apply_element_healing(element, selector or "unknown")

                element.clear()
                element.send_keys(text)
                return True

            except StaleElementReferenceException:
                if attempt < self.max_retries - 1:
                    logger.info(f"Stale element on type attempt {attempt + 1}, re-locating")
                    element = self._find_element_basic(By.XPATH, selector, 5)
                else:
                    raise

        return False

    def _type_locator_with_healing(self, locator, text: str, selector: str = None) -> bool:
        """Type into Playwright locator with comprehensive healing."""
        for attempt in range(self.max_retries):
            try:
                # Apply healing to locator first
                if self.healing_enabled:
                    locator = self._apply_locator_healing(locator, selector or "unknown")

                # Try fill method first (clears and types)
                locator.fill(text)
                return True

            except Exception as e:
                logger.warning(f"Playwright type attempt {attempt + 1} failed: {str(e)}")

                if attempt < self.max_retries - 1:
                    # Try alternative typing strategies
                    try:
                        # Strategy 1: Clear and type manually
                        locator.clear(timeout=3000)
                        self.page.wait_for_timeout(200)
                        locator.type(text, delay=50, timeout=10000)
                        logger.info("Manual type successful")
                        return True
                    except:
                        pass

                    try:
                        # Strategy 2: Focus and keyboard type
                        locator.focus()
                        self.page.wait_for_timeout(200)
                        locator.clear()
                        self.page.wait_for_timeout(200)
                        self.page.keyboard.type(text, delay=50)
                        logger.info("Keyboard type successful")
                        return True
                    except:
                        pass

                    try:
                        # Strategy 3: JavaScript value setting
                        locator.evaluate(f"element => element.value = '{text}'")
                        # Trigger events to ensure reactivity
                        locator.evaluate("""
                            element => {
                                element.dispatchEvent(new Event('input', { bubbles: true }));
                                element.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        """)
                        logger.info("JavaScript type successful")
                        return True
                    except:
                        pass

                    # Wait before next attempt with exponential backoff
                    time.sleep(0.5 * (2 ** attempt))
                else:
                    raise

        return False

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    def _verify_page_load(self) -> bool:
        """Verify that the page has loaded successfully."""
        try:
            if self.framework == 'selenium':
                # Check document ready state
                ready_state = self.driver.execute_script("return document.readyState")
                return ready_state == "complete"
            else:  # playwright
                # Playwright handles this automatically in goto
                return True
        except:
            return False

    def get_selector_fallbacks(self, primary_selector: str) -> list:
        """
        Generate fallback selectors for a primary selector.
        This implements the Selector Fallback Healer.
        """
        fallbacks = []

        # If it's an ID selector, try name, class, etc.
        if primary_selector.startswith("//*[@id='"):
            element_id = primary_selector.split("'")[1]
            fallbacks.extend([
                f"//*[@name='{element_id}']",
                f"//*[contains(@class, '{element_id}')]",
                f"//*[contains(text(), '{element_id}')]"
            ])

        # If it's a class selector, try other variations
        elif "contains(@class," in primary_selector:
            # Extract class name
            class_match = re.search(r"contains\(@class,\s*'([^']+)'\)", primary_selector)
            if class_match:
                class_name = class_match.group(1)
                fallbacks.extend([
                    f"//*[@id='{class_name}']",
                    f"//*[@name='{class_name}']",
                    f"//*[contains(text(), '{class_name}')]"
                ])

        # If it's a text selector, try other attributes
        elif "text()" in primary_selector:
            text_match = re.search(r"text\(\)\s*=\s*'([^']+)'", primary_selector)
            if text_match:
                text_content = text_match.group(1)
                fallbacks.extend([
                    f"//*[@id='{text_content}']",
                    f"//*[@name='{text_content}']",
                    f"//*[contains(@class, '{text_content}')]"
                ])

        return fallbacks

    def heal_with_fallback_selectors(self, primary_selector: str, timeout: int = 10):
        """
        Try to find element using primary selector, then fallbacks.
        This implements the Selector Fallback Healer.
        """
        # Try primary selector
        try:
            return self.find_element_with_healing(By.XPATH, primary_selector, timeout)
        except:
            pass

        # Try fallback selectors
        fallbacks = self.get_selector_fallbacks(primary_selector)
        for fallback in fallbacks:
            try:
                logger.info(f"Trying fallback selector: {fallback}")
                return self.find_element_with_healing(By.XPATH, fallback, timeout)
            except:
                continue

        raise NoSuchElementException(f"Element not found with primary selector or fallbacks: {primary_selector}")


# ============================================================================
# DECORATOR FOR EASY INTEGRATION
# ============================================================================

def with_healing(healer_instance: WebHealer):
    """
    Decorator to add healing to any function that interacts with web elements.

    Usage:
        @with_healing(healer)
        def my_click_function(driver, xpath):
            element = driver.find_element(By.XPATH, xpath)
            element.click()
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not healer_instance.healing_enabled:
                return func(*args, **kwargs)

            last_exception = None
            for attempt in range(healer_instance.max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Healing attempt {attempt + 1} failed in {func.__name__}: {str(e)}")

                    if attempt < healer_instance.max_retries - 1:
                        time.sleep(0.5 * (2 ** attempt))

            raise last_exception
        return wrapper
    return decorator


# ============================================================================
# SELENIUM-SPECIFIC WRAPPER FUNCTIONS
# ============================================================================

class SeleniumHealer(WebHealer):
    """Selenium-specific healer with additional Selenium utilities."""

    def __init__(self, driver, max_retries=3, healing_enabled=True):
        super().__init__(driver=driver, framework='selenium',
                        max_retries=max_retries, healing_enabled=healing_enabled)

    def find_element_healed(self, by, selector, timeout=10):
        """Convenience method for Selenium element finding with healing."""
        return self.find_element_with_healing(by, selector, timeout)

    def click_healed(self, by, selector, timeout=10):
        """Convenience method for Selenium clicking with healing."""
        return self.click_with_healing(selector=selector, timeout=timeout)

    def type_healed(self, by, selector, text, timeout=10):
        """Convenience method for Selenium typing with healing."""
        return self.type_with_healing(text, selector=selector, timeout=timeout)


# ============================================================================
# PLAYWRIGHT-SPECIFIC WRAPPER FUNCTIONS
# ============================================================================

class PlaywrightHealer(WebHealer):
    """Playwright-specific healer with additional Playwright utilities."""

    def __init__(self, page, max_retries=3, healing_enabled=True):
        super().__init__(page=page, framework='playwright',
                        max_retries=max_retries, healing_enabled=healing_enabled)

    def find_locator_healed(self, selector, timeout=10):
        """Convenience method for Playwright locator finding with healing."""
        return self.find_locator_with_healing(selector, timeout)

    def click_healed(self, selector, timeout=10):
        """Convenience method for Playwright clicking with healing."""
        return self.click_with_healing(selector=selector, timeout=timeout)

    def type_healed(self, selector, text, timeout=10):
        """Convenience method for Playwright typing with healing."""
        return self.type_with_healing(text, selector=selector, timeout=timeout)


# ============================================================================
# BACKWARD COMPATIBILITY IMPORTS
# ============================================================================

# For easy importing
__all__ = [
    'WebHealer',
    'SeleniumHealer',
    'PlaywrightHealer',
    'with_healing'
]

if __name__ == "__main__":
    # Example usage
    print("Web Automation Healer Module")
    print("Import this module to add healing capabilities to your Selenium/Playwright tests")
    print("\nExample:")
    print("  from healer import SeleniumHealer")
    print("  healer = SeleniumHealer(driver)")
    print("  element = healer.find_element_healed(By.XPATH, '//button')")
    print("  healer.click_healed(By.XPATH, '//button')")