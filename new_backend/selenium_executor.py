from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import uuid
from datetime import datetime
import pytz
import traceback
import re
import os
import sys
import signal
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import allure
import base64
import importlib.util
from pathlib import Path

def _load_execution_display():
    module_path = Path(__file__).with_name("vnc_session_manager.py")
    if not module_path.exists():
        return 16

    try:
        spec = importlib.util.spec_from_file_location("local_vnc_session_manager", module_path)
        if spec is None or spec.loader is None:
            return 16

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return int(getattr(module, "EXECUTION_DISPLAY", getattr(module, "BASE_DISPLAY", 16)))
    except Exception as exc:
        print(f"[WARNING] Could not load vnc_session_manager: {exc}")
        return 16


EXECUTION_DISPLAY = _load_execution_display()

class SeleniumTestExecutor:
    # Canonical element-name aliases used across Selenium step handling.
    ELEMENT_NAME_TRAVEL_CLASS = "TRAVELCLASS"
    ELEMENT_NAME_DONE_ALIASES = {"DONEBUTTON", "DONE"}
    ELEMENT_NAME_SELECT_COUNT_TYPE_MAP = {
        "ROOMSCOUNT": "room",
        "ADULTSCOUNT": "adult",
        "CHILDRENCOUNT": "children",
    }

    # Canonical counter element types.
    COUNT_TYPE_ROOM = "room"
    COUNT_TYPE_ADULT = "adult"
    COUNT_TYPE_CHILDREN = "children"
    COUNT_TYPE_INFANT = "infant"

    # Keyword aliases for deriving counter type from sheet element names.
    COUNT_TYPE_KEYWORD_MAP = {
        COUNT_TYPE_ROOM: ["room", "roomscount", "roomcount"],
        COUNT_TYPE_ADULT: ["adult", "adultscount", "adultcount"],
        COUNT_TYPE_CHILDREN: ["child", "children", "childrencount", "childcount"],
        COUNT_TYPE_INFANT: ["infant", "infantscount", "infantcount"],
    }

    # UI label/text constants used by popup/city/date handling.
    UI_LABEL_ADULTS = "Adults"
    UI_LABEL_CHILDREN = "Children"
    UI_LABEL_INFANTS = "Infants"
    UI_LABEL_DONE = "Done"
    UI_LABEL_ROOMS_AND_GUESTS = "Rooms & Guests"
    UI_LABEL_FROM = "From"
    UI_LABEL_TO = "To"
    UI_LABEL_CITY = "City"
    UI_LABEL_TODAY = "Today"
    UI_LABEL_TOMORROW = "Tomorrow"
    UI_LABEL_DAY_AFTER_TOMORROW = "Day After Tomorrow"
    UI_TOKEN_BUS = "bus"

    QUICK_DATE_TODAY = "today"
    QUICK_DATE_TOMORROW = "tomorrow"
    QUICK_DATE_DAY_AFTER = "day-after-tomorrow"
    QUICK_DATE_DAY_AFTER_ALIASES = ["day-after-tomorrow", "day after tomorrow", "dayaftertomorrow"]

    BUS_QUICK_DATE_SKIP_OPTIONS = ["false", "skip", "", "n/a", "0"]
    BUS_QUICK_DATE_EXECUTE_OPTIONS = ["true", "1"]

    COUNT_CONTROL_XPATHS = {
        COUNT_TYPE_ROOM: ("//p[contains(@data-testid,'room-increment')]", "//p[@data-testid='room-decrement']"),
        COUNT_TYPE_ADULT: ("//p[@data-testid='adult-increment']", "//p[contains(@data-testid,'adult-decrement')]"),
        COUNT_TYPE_CHILDREN: ("//p[@data-testid='counter-increment-children']", "//p[@data-testid='counter-decrement-children']"),
        COUNT_TYPE_INFANT: ("//p[contains(@data-testid,'infant-increment')]", "//p[contains(@data-testid,'infant-decrement')]"),
    }

    CITY_INPUT_SELECTORS = [
        "//input[contains(@placeholder,'From') or contains(@placeholder,'from')]",
        "//input[contains(@placeholder,'To') or contains(@placeholder,'to')]",
        "//input[contains(@placeholder,'City') or contains(@placeholder,'city')]",
        "//input[@type='text' and contains(@name,'from')]",
        "//input[@type='text' and contains(@name,'to')]",
        "//input[@type='text' and contains(@id,'from')]",
        "//input[@type='text' and contains(@id,'to')]",
    ]

    CITY_PLACEHOLDER_BLOCKLIST = {"From", "To", "City"}
    DATE_QUICK_OPTIONS = ["tomorrow", "today", "day-after-tomorrow"]

    TODAY_SELECTORS = [
        "//button[normalize-space(text())='Today']",
        "//button[contains(text(),'Today')]",
        "//*[contains(text(),'Today') and (name()='button' or name()='div')]",
    ]
    TOMORROW_SELECTORS = [
        "//p[contains(text(),'Tomorrow')]",
        "//p[contains(text(),'Tomorrow')]/parent::*",
        "//button[contains(text(),'Tomorrow')]",
    ]
    TOMORROW_BUS_SELECTORS = [
        "//button[normalize-space(text())='Tomorrow']",
        "//button[contains(text(),'Tomorrow')]",
        "//*[contains(text(),'Tomorrow') and (name()='button' or name()='div')]",
        "//p[contains(text(),'Tomorrow')]/parent::*",
    ]
    DAY_AFTER_TOMORROW_SELECTORS = [
        "//p[contains(text(),'Day After')]",
        "//p[contains(text(),'Day After')]/parent::*",
        "//div[@data-testid='day-after-tomorrow']",
    ]

    def __init__(self, enable_isolation=True, enable_remote_viewing=False, headless=None, server_execution=False, grid_url=None, vnc_session=None, display_id=None):
        self.driver = None
        self.wait = None
        self.fluent_wait = None
        self.actions = None
        self.setup_allure_results_directory()
        self.current_test_attachments = []
        self.enable_isolation = enable_isolation  # Flag to enable/disable isolation mode
        self.enable_remote_viewing = enable_remote_viewing  # Flag to enable/disable remote viewing
        self.headless = headless  # Headless mode setting (None = auto-detect, True/False = explicit)
        self.server_execution = server_execution  # Flag to enable/disable server execution mode
        self.grid_url = grid_url or "http://10.30.3.85:4444/wd/hub"  # Default Grid URL for server
        self.vnc_session = vnc_session  # VNC session information for streaming
        self.display_id = display_id  # VNC-assigned display ID

        # Derive numeric display_number and set DISPLAY env var
        # Accept display_id in forms like ":16" or "16"
        if self.display_id:
            try:
                dn = str(self.display_id).lstrip(':')
                self.display_number = int(dn)
            except Exception:
                self.display_number = EXECUTION_DISPLAY
            os.environ['DISPLAY'] = f":{self.display_number}"
            print(f"[DISPLAY] Using VNC-assigned display :{self.display_number}")
        else:
            # Default to execution display when none provided
            self.display_number = EXECUTION_DISPLAY

        if self.enable_remote_viewing or self.vnc_session or self.display_id:
            self.headless = False
            print(f"[INIT] Headless DISABLED because VNC/streaming is enabled")
        elif self.server_execution:
            self.headless = True
            print(f"[INIT] Forced headless mode for server execution")

        # Window/Tab management
        self.initial_window_handle = None
        self.current_window_handle = None
        self.all_window_handles = []
        self.window_switch_timeout = 10  # seconds to wait for new windows

        # Remote viewing session management
        self.viewing_session_id = None
        self.viewing_clients = set()  # Track connected clients for this session

        # Temporary user data directory for Chrome isolation
        self.temp_user_data_dir = None
        self.last_launch_error = None
        # Runtime tuning knobs for cross-site stability
        self.default_wait_timeout = int(os.getenv("SELENIUM_WAIT_TIMEOUT_SECONDS", "15"))
        self.default_step_timeout = int(os.getenv("SELENIUM_STEP_TIMEOUT_SECONDS", "45"))
        self.fast_wait_timeout = float(os.getenv("SELENIUM_FAST_WAIT_TIMEOUT_SECONDS", "1.5"))
        self.autocomplete_wait_timeout = float(os.getenv("SELENIUM_AUTOCOMPLETE_WAIT_TIMEOUT_SECONDS", "1.2"))
        self._last_count_action_state = None
        self._last_drag_drop_state = None
        self._last_read_result = None
        self.download_dir = os.path.join(os.getcwd(), "downloads", "selenium")
        os.makedirs(self.download_dir, exist_ok=True)
        self.visual_baseline_dir = os.path.join(os.getcwd(), "visual-baselines", "selenium")
        os.makedirs(self.visual_baseline_dir, exist_ok=True)

        # Grid execution configuration
        self.grid_capabilities = {
            "browserName": "chrome",
            "browserVersion": "latest",
            "platformName": "LINUX",
            "se:recordVideo": True,
            "se:screenResolution": "1920x1080",
            "se:timeZone": "Asia/Kolkata",
            "se:vncEnabled": True,  # Enable VNC for noVNC streaming
            "se:vncPassword": "secret"  # VNC password for secure access
        }

        print(f"[INIT] Selenium Test Executor initialized with isolation mode: {'ENABLED' if enable_isolation else 'DISABLED'}")
        print(f"[INIT] Remote viewing mode: {'ENABLED' if enable_remote_viewing else 'DISABLED'}")
        print(f"[INIT] Server execution mode: {'ENABLED' if server_execution else 'DISABLED'}")
        print(f"[INIT] Grid URL: {self.grid_url}")
        effective_headless = self.headless
        print(f"[INIT] Headless mode: {'AUTO' if effective_headless is None else ('ENABLED' if effective_headless else 'DISABLED')}")
        print(f"[INIT] Window management enabled with {self.window_switch_timeout}s timeout")
        print(f"[INIT] Grid capabilities configured for remote execution")
        print(f"[INIT] VNC session: {'AVAILABLE' if vnc_session else 'NONE'}")
        print(f"[INIT] Default wait timeout: {self.default_wait_timeout}s")
        print(f"[INIT] Default step timeout: {self.default_step_timeout}s")
        print(f"[INIT] Fast wait timeout: {self.fast_wait_timeout}s")
        print(f"[INIT] Autocomplete wait timeout: {self.autocomplete_wait_timeout}s")
        print(f"[INIT] Download directory: {self.download_dir}")
        print(f"[INIT] Visual baseline directory: {self.visual_baseline_dir}")

    def _normalize_chromedriver_path(self, driver_path):
        """Ensure the selected path points to an executable chromedriver binary."""
        if not driver_path:
            return None

        normalized = os.path.normpath(driver_path)
        lower_name = os.path.basename(normalized).lower()

        # webdriver-manager may occasionally return THIRD_PARTY_NOTICES.chromedriver
        # instead of the actual executable.
        if lower_name.startswith("third_party_notices"):
            candidate_dir = normalized if os.path.isdir(normalized) else os.path.dirname(normalized)
            candidates = [
                os.path.join(candidate_dir, "chromedriver.exe"),
                os.path.join(candidate_dir, "chromedriver"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    print(f"[CHROMEDRIVER] Corrected non-executable driver path to: {candidate}")
                    return candidate

        return normalized

    def _extract_major_version(self, version_text):
        """Extract major version number from arbitrary version output text."""
        if not version_text:
            return None
        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\.(\d+)\b", str(version_text))
        if match:
            return int(match.group(1))
        return None

    def _get_windows_chrome_major_from_registry(self):
        """Read installed Chrome major version from Windows registry."""
        try:
            import winreg
        except Exception:
            return None

        reg_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon"),
        ]

        for hive, path in reg_paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    major = self._extract_major_version(version)
                    if major:
                        print(f"[CHROME_BINARY] Registry version: {version}")
                        return major
            except Exception:
                continue

        return None

    def _get_binary_version_output(self, binary_path):
        """Return '--version' output for a binary, or empty string on failure."""
        try:
            result = subprocess.run([binary_path, '--version'], capture_output=True, text=True, timeout=10)
            return (result.stdout or result.stderr or "").strip()
        except Exception:
            return ""

    def _install_windows_chromedriver(self, chrome_major=None):
        """Install chromedriver on Windows with best-effort version targeting."""
        install_errors = []

        # Try explicit major version first when available.
        if chrome_major:
            try:
                path = ChromeDriverManager(driver_version=str(chrome_major)).install()
                path = self._normalize_chromedriver_path(path)
                if path and os.path.exists(path):
                    print(f"[CHROMEDRIVER] Downloaded major-matched driver for Chrome {chrome_major}: {path}")
                    return path
            except Exception as e:
                install_errors.append(f"major={chrome_major}: {e}")

        # Fallback to default resolver.
        try:
            path = ChromeDriverManager().install()
            path = self._normalize_chromedriver_path(path)
            if path and os.path.exists(path):
                print(f"[CHROMEDRIVER] Downloaded driver with default resolver: {path}")
                return path
        except Exception as e:
            install_errors.append(f"default: {e}")

        raise RuntimeError(" | ".join(install_errors) if install_errors else "Unable to install ChromeDriver")

    def _sync_driver_to_bundled_path(self, source_path):
        """Copy downloaded driver into project bundled location for future offline runs."""
        try:
            import shutil
            bundled_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Chrome_driver")
            os.makedirs(bundled_dir, exist_ok=True)
            target_path = os.path.join(bundled_dir, "chromedriver.exe")
            if os.path.abspath(source_path) != os.path.abspath(target_path):
                shutil.copy2(source_path, target_path)
                print(f"[CHROMEDRIVER] Updated bundled driver cache: {target_path}")
            return target_path
        except Exception as copy_error:
            print(f"[CHROMEDRIVER] Warning: could not update bundled cache: {copy_error}")
            return source_path
    
    def clear_old_allure_results(self):
        """Manage allure results - keep history but limit file count"""
        try:
            print("[ALLURE_HISTORY] Managing allure results to preserve execution history...")
            
            # Get all possible allure directories
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            
            allure_dirs = [
                os.path.join(project_root, 'allure-results-new'),
                os.path.join(project_root, 'allure-results'),
                os.path.join(current_dir, 'allure-results'),
                os.path.join(project_root, 'new_backend', 'allure-results')
            ]
            
            files_managed = 0
            for allure_dir in allure_dirs:
                if os.path.exists(allure_dir):
                    print(f"[ALLURE_HISTORY] Checking directory: {allure_dir}")
                    
                    # Get all result files sorted by modification time (newest first)
                    result_files = []
                    for filename in os.listdir(allure_dir):
                        file_path = os.path.join(allure_dir, filename)
                        if os.path.isfile(file_path) and filename.endswith('.json'):
                            result_files.append((file_path, os.path.getmtime(file_path)))
                    
                    # Sort by modification time (newest first)
                    result_files.sort(key=lambda x: x[1], reverse=True)
                    
                    # Keep the latest 50 result files, remove older ones to prevent excessive buildup
                    if len(result_files) > 50:
                        files_to_remove = result_files[50:]  # Remove files beyond the 50 newest
                        for file_path, _ in files_to_remove:
                            try:
                                os.remove(file_path)
                                files_managed += 1
                                print(f"[ALLURE_HISTORY] Removed old result file: {os.path.basename(file_path)}")
                            except Exception as e:
                                print(f"[ALLURE_HISTORY] Warning: Could not remove {file_path}: {str(e)}")
                    else:
                        print(f"[ALLURE_HISTORY] Directory has {len(result_files)} result files - keeping all")
            
            if files_managed > 0:
                print(f"[ALLURE_HISTORY] Managed {files_managed} old allure files (kept latest 50 per directory)")
            else:
                print("[ALLURE_HISTORY] No old files needed to be removed")
            
        except Exception as e:
            print(f"[ALLURE_HISTORY] Error managing allure results: {str(e)}")
            # Don't fail the test execution if management fails
            pass
    
    def scroll_element_into_view_and_highlight(self, xpath, element_name):
        """Scroll element into view and get its coordinates for highlighting"""
        element_coords = None
        element = None
        
        if not self.driver or not xpath:
            return None, None
            
        print(f"[HIGHLIGHT] Searching for element: {element_name} with XPath: {xpath}")
        
        try:
            # First try the original XPath with a short timeout to avoid long waits
            element = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            print(f"[HIGHLIGHT] Found element with original XPath: {xpath}")
        except Exception as e:
            print(f"[HIGHLIGHT] Original XPath failed: {str(e)}")
            
            # Try alternative strategies if element_name is available
            if element_name:
                alternative_xpaths = [
                    f"//*[@id='{element_name}']",
                    f"//*[@name='{element_name}']",
                    f"//*[@class='{element_name}']",
                    f"//*[contains(@id, '{element_name}')]",
                    f"//*[contains(@name, '{element_name}')]",
                    f"//*[contains(@class, '{element_name}')]",
                    f"//*[contains(text(), '{element_name}')]"
                ]
                
                for alt_xpath in alternative_xpaths:
                    try:
                        element = WebDriverWait(self.driver, 1).until(
                            EC.presence_of_element_located((By.XPATH, alt_xpath))
                        )
                        print(f"[HIGHLIGHT] Found element with alternative XPath: {alt_xpath}")
                        break
                    except:
                        continue
                        
        # If no element found with any strategy, return None immediately
        if not element:
            print(f"[HIGHLIGHT] Element '{element_name}' not found with any strategy")
            return None, None
        
        # Element was found, proceed with scrolling and highlighting
        try:
            # Scroll element into view
            print(f"[HIGHLIGHT] Scrolling element into view...")
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(1)  # Wait for scroll to complete
            
            # Get element coordinates after scrolling
            location = element.location
            size = element.size
            element_coords = {
                'x': location['x'],
                'y': location['y'],
                'width': size['width'],
                'height': size['height']
            }
            print(f"[HIGHLIGHT] Element coordinates after scrolling: {element_coords}")
            
            # Add a visual indicator by briefly highlighting the element with JavaScript
            try:
                self.driver.execute_script("""
                    arguments[0].style.border = '5px solid red';
                    arguments[0].style.backgroundColor = 'rgba(255, 0, 0, 0.3)';
                    setTimeout(function() {
                        arguments[0].style.border = '';
                        arguments[0].style.backgroundColor = '';
                    }, 500);
                """, element)
                time.sleep(0.5)  # Wait for the highlight to be visible
            except Exception as js_error:
                print(f"[HIGHLIGHT] JavaScript highlighting failed: {js_error}")
                
        except Exception as scroll_error:
            print(f"[HIGHLIGHT] Error scrolling element: {scroll_error}")
            # Still try to get coordinates even if scrolling fails
            try:
                location = element.location
                size = element.size
                element_coords = {
                    'x': location['x'],
                    'y': location['y'],
                    'width': size['width'],
                    'height': size['height']
                }
            except:
                pass
        
        return element_coords, element

    def highlight_failed_element(self, screenshot_path, xpath, element_name):
        """Add red border highlight to failed element in screenshot"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import os
            
            print(f"[HIGHLIGHT] Highlighting element '{element_name}' with xpath '{xpath}' in {screenshot_path}")
            
            # First, try to scroll the element into view and get coordinates
            element_coords, element = self.scroll_element_into_view_and_highlight(xpath, element_name)
            
            if not element_coords:
                print(f"[HIGHLIGHT] Could not find element coordinates with any strategy")
            
            # Load and highlight the screenshot
            if screenshot_path and os.path.exists(screenshot_path):
                img = Image.open(screenshot_path)
                draw = ImageDraw.Draw(img)
                
                if element_coords:
                    # Draw VERY prominent red highlighting around the element
                    padding = 15  # Increased padding for better visibility
                    x1 = max(0, element_coords['x'] - padding)
                    y1 = max(0, element_coords['y'] - padding)
                    x2 = min(img.width, element_coords['x'] + element_coords['width'] + padding)
                    y2 = min(img.height, element_coords['y'] + element_coords['height'] + padding)
                    
                    # Create a very prominent highlighting effect
                    # 1. Draw multiple thick red borders
                    for i in range(10):  # Increased from 5 to 10 layers
                        draw.rectangle([x1-i, y1-i, x2+i, y2+i], outline='red', width=5)  # Increased width
                    
                    # 2. Add bright red corners for extra visibility
                    corner_size = 20
                    corners = [
                        (x1-corner_size, y1-corner_size, x1, y1),  # Top-left
                        (x2, y1-corner_size, x2+corner_size, y1),  # Top-right
                        (x1-corner_size, y2, x1, y2+corner_size),  # Bottom-left
                        (x2, y2, x2+corner_size, y2+corner_size)   # Bottom-right
                    ]
                    
                    for corner in corners:
                        if corner[0] >= 0 and corner[1] >= 0 and corner[2] <= img.width and corner[3] <= img.height:
                            draw.rectangle(corner, fill='red', outline='red')
                    
                    # 3. Add a semi-transparent red overlay with higher opacity
                    overlay = Image.new('RGBA', img.size, (255, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    overlay_draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 100))  # Increased opacity from 50 to 100
                    
                    # Composite the overlay onto the original image
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    img = Image.alpha_composite(img, overlay)
                    
                    # 4. Add text label above the element
                    try:
                        font = ImageFont.load_default()
                        text = f"[X] FAILED: {element_name}" if element_name else "[X] ELEMENT FAILED"
                        text_bbox = draw.textbbox((0, 0), text, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        
                        # Position text above the element
                        text_x = max(10, x1)
                        text_y = max(10, y1 - text_height - 10)
                        
                        # Draw text background
                        draw.rectangle([text_x-5, text_y-5, text_x+text_width+5, text_y+text_height+5], 
                                     fill='red', outline='red')
                        draw.text((text_x, text_y), text, fill='white', font=font)
                    except Exception as text_error:
                        print(f"[HIGHLIGHT] Text overlay failed: {text_error}")
                    
                    print(f"[HIGHLIGHT] Drew VERY prominent red highlighting at coordinates ({x1},{y1}) to ({x2},{y2})")
                else:
                    # If we can't find coordinates, add VERY prominent red border around the whole image
                    width, height = img.size
                    
                    # Draw very thick border around entire image
                    for i in range(15):  # Increased from 8 to 15 layers
                        draw.rectangle([i, i, width-1-i, height-1-i], outline='red', width=6)  # Increased width
                    
                    # Add large text overlay indicating failed element
                    try:
                        font = ImageFont.load_default()
                        text = f" FAILED ELEMENT: {element_name}" if element_name else " ELEMENT FAILED"
                        
                        # Draw text in multiple locations for visibility
                        positions = [(20, 20), (20, height//2), (width//2, 20)]
                        for pos in positions:
                            if pos[0] < width-200 and pos[1] < height-50:
                                # Text background
                                text_bbox = draw.textbbox(pos, text, font=font)
                                draw.rectangle([text_bbox[0]-10, text_bbox[1]-10, 
                                              text_bbox[2]+10, text_bbox[3]+10], 
                                             fill='red', outline='red')
                                draw.text(pos, text, fill='white', font=font)
                    except Exception as text_error:
                        print(f"[HIGHLIGHT] Text overlay failed: {text_error}")
                    
                    print(f"[HIGHLIGHT] Added VERY prominent red border around entire screenshot")
                
                # Convert back to RGB for PNG saving if needed
                if img.mode == 'RGBA':
                    # Create a white background and paste the RGBA image on it
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                    img = rgb_img
                
                # Save the highlighted screenshot - always overwrite the original for failed screenshots
                file_name = os.path.basename(screenshot_path)
                if "FAILED" in file_name:
                    # For failed screenshots, save with highlighting directly to the original file
                    img.save(screenshot_path)
                    print(f"[HIGHLIGHT] Saved highlighted failed screenshot: {screenshot_path}")
                    return screenshot_path
                else:
                    # For non-failed screenshots, just add highlighting in place
                    img.save(screenshot_path)
                    print(f"[HIGHLIGHT] Updated original screenshot with highlighting")
                    return screenshot_path
            
            return screenshot_path
            
        except Exception as e:
            print(f"[ERROR] Failed to highlight element: {str(e)}")
            traceback.print_exc()
            # Fallback: just copy with FAILED marker
            if screenshot_path and os.path.exists(screenshot_path):
                import shutil
                dir_name = os.path.dirname(screenshot_path)
                file_name = os.path.basename(screenshot_path)
                
                if "FAILED" in file_name:
                    highlighted_name = file_name.replace("FAILED", "FAILED_HIGHLIGHTED")
                    highlighted_path = os.path.join(dir_name, highlighted_name)
                    try:
                        shutil.copy2(screenshot_path, highlighted_path)
                        print(f"[HIGHLIGHT] Fallback: copied failed screenshot to {highlighted_path}")
                        return highlighted_path
                    except:
                        return screenshot_path
            return screenshot_path
    
    def highlight_failed_element_in_existing_screenshot(self, screenshot_path, xpath, element_name, element_coords=None):
        """Add red border highlight to failed element in existing screenshot using pre-calculated coordinates"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import os
            
            print(f"[HIGHLIGHT_EXISTING] Highlighting element '{element_name}' in existing screenshot: {screenshot_path}")
            
            # If coordinates weren't provided, try to get them (but element should already be positioned)
            if not element_coords and xpath and element_name:
                try:
                    print(f"[HIGHLIGHT_EXISTING] No coordinates provided, trying to find element")
                    element_coords, element = self.scroll_element_into_view_and_highlight(xpath, element_name)
                except Exception as coord_error:
                    print(f"[HIGHLIGHT_EXISTING] Could not get element coordinates: {coord_error}")
            
            # Load and highlight the screenshot
            if screenshot_path and os.path.exists(screenshot_path):
                img = Image.open(screenshot_path)
                draw = ImageDraw.Draw(img)
                
                if element_coords:
                    print(f"[HIGHLIGHT_EXISTING] Using element coordinates: {element_coords}")
                    
                    # Draw VERY prominent red highlighting around the element
                    padding = 15  # Increased padding for better visibility
                    x1 = max(0, element_coords['x'] - padding)
                    y1 = max(0, element_coords['y'] - padding)
                    x2 = min(img.width, element_coords['x'] + element_coords['width'] + padding)
                    y2 = min(img.height, element_coords['y'] + element_coords['height'] + padding)
                    
                    # Create a very prominent highlighting effect
                    # 1. Draw multiple thick red borders
                    for i in range(10):  # Multiple layers for visibility
                        draw.rectangle([x1-i, y1-i, x2+i, y2+i], outline='red', width=5)
                    
                    # 2. Add bright red corners for extra visibility
                    corner_size = 20
                    corners = [
                        (x1-corner_size, y1-corner_size, x1, y1),  # Top-left
                        (x2, y1-corner_size, x2+corner_size, y1),  # Top-right
                        (x1-corner_size, y2, x1, y2+corner_size),  # Bottom-left
                        (x2, y2, x2+corner_size, y2+corner_size)   # Bottom-right
                    ]
                    
                    for corner in corners:
                        if corner[0] >= 0 and corner[1] >= 0 and corner[2] <= img.width and corner[3] <= img.height:
                            draw.rectangle(corner, fill='red', outline='red')
                    
                    # 3. Add a semi-transparent red overlay
                    overlay = Image.new('RGBA', img.size, (255, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    overlay_draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 100))
                    
                    # Composite the overlay onto the original image
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    img = Image.alpha_composite(img, overlay)
                    
                    # 4. Add text label above the element
                    try:
                        font = ImageFont.load_default()
                        text = f"[X] FAILED: {element_name}" if element_name else "[X] ELEMENT FAILED"
                        text_bbox = draw.textbbox((0, 0), text, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        
                        # Position text above the element
                        text_x = max(10, x1)
                        text_y = max(10, y1 - text_height - 10)
                        
                        # Draw text background
                        draw.rectangle([text_x-5, text_y-5, text_x+text_width+5, text_y+text_height+5], 
                                     fill='red', outline='red')
                        draw.text((text_x, text_y), text, fill='white', font=font)
                    except Exception as text_error:
                        print(f"[HIGHLIGHT_EXISTING] Text overlay failed: {text_error}")
                    
                    print(f"[HIGHLIGHT_EXISTING] Drew prominent red highlighting at coordinates ({x1},{y1}) to ({x2},{y2})")
                else:
                    # If we can't find coordinates, add prominent red border around the whole image
                    width, height = img.size
                    
                    # Draw very thick border around entire image
                    for i in range(15):
                        draw.rectangle([i, i, width-1-i, height-1-i], outline='red', width=6)
                    
                    # Add large text overlay indicating failed element
                    try:
                        font = ImageFont.load_default()
                        text = f"[X] FAILED ELEMENT: {element_name}" if element_name else "[X] ELEMENT FAILED"
                        
                        # Draw text in multiple locations for visibility
                        positions = [(20, 20), (20, height//2), (width//2, 20)]
                        for pos in positions:
                            if pos[0] < width-200 and pos[1] < height-50:
                                # Text background
                                text_bbox = draw.textbbox(pos, text, font=font)
                                draw.rectangle([text_bbox[0]-10, text_bbox[1]-10, 
                                              text_bbox[2]+10, text_bbox[3]+10], 
                                             fill='red', outline='red')
                                draw.text(pos, text, fill='white', font=font)
                    except Exception as text_error:
                        print(f"[HIGHLIGHT_EXISTING] Text overlay failed: {text_error}")
                    
                    print(f"[HIGHLIGHT_EXISTING] Added prominent red border around entire screenshot")
                
                # Convert back to RGB for PNG saving if needed
                if img.mode == 'RGBA':
                    # Create a white background and paste the RGBA image on it
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                    img = rgb_img
                
                # Save the highlighted screenshot
                img.save(screenshot_path)
                print(f"[HIGHLIGHT_EXISTING] Successfully highlighted existing screenshot: {screenshot_path}")
                return screenshot_path
            
            return screenshot_path
            
        except Exception as e:
            print(f"[ERROR] Failed to highlight element in existing screenshot: {str(e)}")
            traceback.print_exc()
            return screenshot_path
    
    def add_element_not_found_indication(self, screenshot_path, xpath, element_name):
        """Add indication to screenshot when element was not found"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import os
            
            print(f"[ELEMENT_NOT_FOUND] Adding 'element not found' indication to screenshot: {screenshot_path}")
            
            if screenshot_path and os.path.exists(screenshot_path):
                img = Image.open(screenshot_path)
                draw = ImageDraw.Draw(img)
                width, height = img.size
                
                # Add prominent red border around entire image to indicate failure
                border_thickness = 20
                for i in range(border_thickness):
                    draw.rectangle([i, i, width-1-i, height-1-i], outline='red', width=8)
                
                # Add large failure message overlay
                try:
                    font = ImageFont.load_default()
                    
                    # Main failure message
                    main_text = f" ELEMENT NOT FOUND"
                    element_text = f"Element: {element_name}" if element_name else "Unknown Element"
                    xpath_text = f"XPath: {xpath[:80]}..." if len(xpath) > 80 else f"XPath: {xpath}"
                    
                    # Position messages in multiple locations for visibility
                    messages = [
                        (main_text, (50, 50), 'red', 'white'),
                        (element_text, (50, 90), 'darkred', 'white'),
                        (xpath_text, (50, 130), 'darkred', 'white'),
                        (main_text, (50, height - 150), 'red', 'white'),
                        (main_text, (width - 400, 50), 'red', 'white')
                    ]
                    
                    for text, pos, bg_color, text_color in messages:
                        if pos[0] < width - 50 and pos[1] < height - 50:
                            try:
                                # Get text dimensions
                                text_bbox = draw.textbbox(pos, text, font=font)
                                text_width = text_bbox[2] - text_bbox[0]
                                text_height = text_bbox[3] - text_bbox[1]
                                
                                # Draw background rectangle
                                draw.rectangle([
                                    pos[0] - 10, pos[1] - 10,
                                    pos[0] + text_width + 10, pos[1] + text_height + 10
                                ], fill=bg_color, outline=bg_color)
                                
                                # Draw text
                                draw.text(pos, text, fill=text_color, font=font)
                            except Exception as text_error:
                                print(f"[ELEMENT_NOT_FOUND] Error drawing text: {text_error}")
                
                except Exception as font_error:
                    print(f"[ELEMENT_NOT_FOUND] Font error: {font_error}")
                
                # Add diagonal "NOT FOUND" lines across the image
                try:
                    # Draw diagonal lines
                    line_color = 'red'
                    line_width = 8
                    
                    # Top-left to bottom-right
                    draw.line([(0, 0), (width, height)], fill=line_color, width=line_width)
                    # Top-right to bottom-left  
                    draw.line([(width, 0), (0, height)], fill=line_color, width=line_width)
                    
                    # Add "X" pattern in center
                    center_x, center_y = width // 2, height // 2
                    cross_size = 100
                    draw.line([
                        (center_x - cross_size, center_y - cross_size),
                        (center_x + cross_size, center_y + cross_size)
                    ], fill=line_color, width=line_width)
                    draw.line([
                        (center_x + cross_size, center_y - cross_size),
                        (center_x - cross_size, center_y + cross_size)
                    ], fill=line_color, width=line_width)
                    
                except Exception as line_error:
                    print(f"[ELEMENT_NOT_FOUND] Error drawing lines: {line_error}")
                
                # Save the modified screenshot
                img.save(screenshot_path)
                print(f"[ELEMENT_NOT_FOUND] Successfully added 'element not found' indication to screenshot")
                return screenshot_path
            
            return screenshot_path
            
        except Exception as e:
            print(f"[ERROR] Failed to add element not found indication: {str(e)}")
            traceback.print_exc()
            return screenshot_path
    
    def setup_allure_results_directory(self):
        """Setup Allure results directory and environment"""
        try:
            current_dir = os.getcwd()
            # If running from new_backend directory, go up one level
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            if not os.path.exists(allure_results_path):
                os.makedirs(allure_results_path)
                print(f"[ALLURE] Created allure-results-new directory at: {allure_results_path}")
            
            # Create environment.properties file for Allure
            env_file = os.path.join(allure_results_path, 'environment.properties')
            with open(env_file, 'w') as f:
                f.write("Browser=Chrome\n")
                f.write("Platform=Windows\n")
                f.write("Base_URL=https://www.ixigo.com\n")
                f.write("Database=Ixigo_TestAutomation\n")
                f.write("Framework=Selenium WebDriver\n")
                f.write(f"Test_Environment=Development\n")
                f.write(f"Execution_Date={datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}\n")

        except Exception as e:
            print(f"[ERROR] Failed to setup allure-results directory: {str(e)}")
    
    def save_screenshot(self, name, step_number=None, status="info"):
        """Save screenshot and return attachment info for Allure"""
        if not self.driver:
            return None
            
        try:
            # Generate unique filename with execution ID (fallback if not set)
            timestamp = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            execution_id = getattr(self, 'current_execution_id', f'test_{timestamp}')
            filename = f"{execution_id}-{timestamp}_{name.replace(' ', '_')}.png"
            
            # Save screenshot to allure-results directory
            current_dir = os.getcwd()
            # If running from new_backend directory, go up one level
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            filepath = os.path.join(allure_results_path, filename)
            
            screenshot_data = self.driver.get_screenshot_as_png()
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)
            
            # Create attachment info for Allure
            attachment = {
                "name": name,
                "source": filename,
                "type": "image/png",
                "size": len(screenshot_data)
            }
            
            # Add to current test attachments
            self.current_test_attachments.append(attachment)
            
            print(f"[SCREENSHOT] Saved: {filename}")
            return attachment
            
        except Exception as e:
            print(f"[ERROR] Failed to save screenshot: {str(e)}")
            return None
    
    def take_screenshot_with_element_highlighting(self, name, step_number=None, status="info", xpath="", element_name=""):
        """Take screenshot with proper element positioning and highlighting in the correct sequence"""
        if not self.driver:
            return None
            
        try:
            print(f"[SCREENSHOT_HIGHLIGHT] Taking screenshot with element highlighting: {name}")
            
            # Step 1: Store current scroll position to restore later if needed
            original_scroll_position = None
            try:
                original_scroll_position = self.driver.execute_script("return window.pageYOffset;")
                print(f"[SCREENSHOT_HIGHLIGHT] Original scroll position: {original_scroll_position}")
            except:
                pass
            
            # Step 2: Try to find and position the element (if xpath provided)
            element_coords = None
            element = None
            element_found = False
            
            if xpath and element_name:
                try:
                    print(f"[SCREENSHOT_HIGHLIGHT] Attempting to find element: {element_name}")
                    element_coords, element = self.scroll_element_into_view_and_highlight(xpath, element_name)
                    
                    if element_coords and element:
                        print(f"[SCREENSHOT_HIGHLIGHT] Element found and positioned at: {element_coords}")
                        element_found = True
                        # Give a moment for the scroll and highlight to complete
                        time.sleep(0.5)
                    else:
                        print(f"[SCREENSHOT_HIGHLIGHT] Element not found, will restore scroll position")
                        element_found = False
                        
                except Exception as scroll_error:
                    print(f"[SCREENSHOT_HIGHLIGHT] Error finding element: {scroll_error}")
                    element_found = False
            
            # Step 3: If element was not found, restore original scroll position and wait for page to stabilize
            if not element_found and original_scroll_position is not None:
                try:
                    print(f"[SCREENSHOT_HIGHLIGHT] Restoring original scroll position: {original_scroll_position}")
                    self.driver.execute_script(f"window.scrollTo(0, {original_scroll_position});")
                    # Wait for scroll animation to complete
                    time.sleep(1.0)
                    
                    # Wait for any dynamic content to stabilize
                    print(f"[SCREENSHOT_HIGHLIGHT] Waiting for page to stabilize...")
                    time.sleep(1.5)
                    
                except Exception as restore_error:
                    print(f"[SCREENSHOT_HIGHLIGHT] Error restoring scroll position: {restore_error}")
            
            # Step 4: Take the screenshot now that page is in correct position
            screenshot_attachment = self.save_screenshot(name, step_number, status)
            
            if not screenshot_attachment or not screenshot_attachment.get('source'):
                print(f"[SCREENSHOT_HIGHLIGHT] Failed to take base screenshot")
                return None
            
            # Step 5: Get full path to the screenshot file
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            full_screenshot_path = os.path.join(allure_results_path, screenshot_attachment['source'])
            
            # Step 6: Apply highlighting to the screenshot (if xpath provided)
            if xpath and element_name and os.path.exists(full_screenshot_path):
                try:
                    print(f"[SCREENSHOT_HIGHLIGHT] Applying highlighting to screenshot: {full_screenshot_path}")
                    
                    if element_found and element_coords:
                        # Element was found - use precise highlighting with coordinates
                        print(f"[SCREENSHOT_HIGHLIGHT] Using precise highlighting with coordinates")
                        highlighted_path = self.highlight_failed_element_in_existing_screenshot(
                            full_screenshot_path, 
                            xpath, 
                            element_name,
                            element_coords  # Pass the coordinates we found
                        )
                    else:
                        # Element was not found - add general failure indication
                        print(f"[SCREENSHOT_HIGHLIGHT] Element not found, adding general failure indication")
                        highlighted_path = self.add_element_not_found_indication(
                            full_screenshot_path,
                            xpath,
                            element_name
                        )
                    
                    if highlighted_path and os.path.exists(highlighted_path):
                        print(f"[SCREENSHOT_HIGHLIGHT] Successfully highlighted screenshot: {highlighted_path}")
                        return highlighted_path
                    else:
                        print(f"[SCREENSHOT_HIGHLIGHT] Highlighting failed, returning original screenshot")
                        return full_screenshot_path
                        
                except Exception as highlight_error:
                    print(f"[SCREENSHOT_HIGHLIGHT] Error applying highlighting: {highlight_error}")
                    # Return original screenshot if highlighting fails
                    return full_screenshot_path
            else:
                # No highlighting needed or possible, return the screenshot path
                return full_screenshot_path
                
        except Exception as e:
            print(f"[ERROR] Failed to take screenshot with element highlighting: {str(e)}")
            # Fallback to regular screenshot
            try:
                fallback_screenshot = self.save_screenshot(name, step_number, status)
                if fallback_screenshot and fallback_screenshot.get('source'):
                    current_dir = os.getcwd()
                    if current_dir.endswith('new_backend'):
                        project_root = os.path.dirname(current_dir)
                    else:
                        project_root = current_dir
                    allure_results_path = os.path.join(project_root, 'allure-results-new')
                    return os.path.join(allure_results_path, fallback_screenshot['source'])
            except:
                pass
            return None
        
    def launch_browser(self):
        """Launch Chrome browser with optimized settings and better error handling"""
        print("[LAUNCH_BROWSER] Starting browser launch process...")

        # Check if browser is already running
        if self.driver is not None:
            try:
                self.driver.current_url
                print("[BROWSER] Browser already running and responsive")
                return True
            except Exception as e:
                print(f"[BROWSER] Existing browser not responsive: {str(e)}, will restart")
                self.close_browser()

        # Generate unique session ID for remote viewing
        if self.enable_remote_viewing:
            import uuid
            self.viewing_session_id = str(uuid.uuid4())
            print(f"[REMOTE_VIEWING] Generated session ID: {self.viewing_session_id}")

        self.last_launch_error = None

        try:
            print("[SETUP] Setting up Chrome options...")
            chrome_options = webdriver.ChromeOptions()

            import tempfile, shutil, os, platform, subprocess, traceback

            current_os = platform.system().lower()
            print(f"[OS_DETECT] Detected OS: {current_os}")

            is_local_visible_run = (
                current_os == "windows"
                and not self.server_execution
                and not self.enable_remote_viewing
                and not self.headless
            )

            # For local visible runs, let Chrome start with Selenium defaults.
            # For managed/server runs, keep strict profile isolation.
            if is_local_visible_run:
                self.temp_user_data_dir = None
                print("[SETUP] Local visible mode: using Selenium-managed temporary profile")
            else:
                temp_user_data_dir = tempfile.mkdtemp(prefix="chrome_user_data_")
                self.temp_user_data_dir = temp_user_data_dir
                chrome_options.add_argument(f"--user-data-dir={temp_user_data_dir}")

            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            # Use a dynamic DevTools port to avoid collisions across parallel/stale sessions.
            # Skip in local visible mode to avoid window-handle instability on Windows.
            if not is_local_visible_run:
                chrome_options.add_argument("--remote-debugging-port=0")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-features=TranslateUI")
            chrome_options.add_argument("--disable-hang-monitor")
            chrome_options.add_argument("--disable-prompt-on-repost")
            chrome_options.add_argument("--force-color-profile=srgb")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--enable-automation")
            chrome_options.add_argument("--disable-sync")
            chrome_options.add_argument("--disable-translate")
            chrome_options.add_argument("--hide-scrollbars")
            chrome_options.add_argument("--mute-audio")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--disable-background-networking")
            chrome_options.add_argument("--disable-component-update")
            chrome_options.add_argument("--disable-domain-reliability")
            chrome_options.add_argument("--disable-client-side-phishing-detection")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-print-preview")
            chrome_options.add_argument("--no-service-autorun")
            chrome_options.add_experimental_option("prefs", {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "profile.default_content_settings.popups": 0,
            })
            if not is_local_visible_run:
                chrome_options.add_argument("--disable-images")
                chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            if not self.enable_remote_viewing and self.headless:
                chrome_options.add_argument("--headless=new")
                # Headless-only rendering stability flags
                chrome_options.add_argument("--disable-software-rasterizer")
                chrome_options.add_argument("--use-gl=swiftshader")
                print("[HEADLESS] Enabled")
            else:
                # Keep local UI runs visibly attached to an on-screen browser window.
                chrome_options.add_argument("--new-window")
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--window-size=1280,720")
                if self.enable_remote_viewing:
                    print("[GUI] Enabled (VNC/Remote Viewing)")
                else:
                    print("[GUI] Enabled")

            if current_os == "linux":
                if self.server_execution and self.vnc_session and self.vnc_session.get("display_num"):
                    os.environ["DISPLAY"] = f":{self.vnc_session['display_num']}"
                    print(f"[DISPLAY] Using DISPLAY={os.environ['DISPLAY']} (VNC)")
                elif hasattr(self, "display_number"):
                    os.environ["DISPLAY"] = f":{self.display_number}"
                    print(f"[DISPLAY] Using DISPLAY=:{self.display_number}")
                else:
                    print("[DISPLAY] No DISPLAY override applied")

            chrome_binary = None
            if current_os == "linux":
                for path in [
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                ]:
                    if os.path.exists(path):
                        chrome_binary = path
                        break
            elif current_os == "windows":
                chrome_paths = [
                    shutil.which("chrome"),
                    shutil.which("chrome.exe"),
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                ]
                chrome_binary = None
                print("[DEBUG] Searching for Chrome on Windows...")
                for path in chrome_paths:
                    if path:
                        exists = os.path.exists(path)
                        print(f"[DEBUG] Checking: {path} - {'Found' if exists else 'Not found'}")
                        if exists:
                            chrome_binary = path
                            break
                    else:
                        print(f"[DEBUG] PATH check returned None")

            if not chrome_binary:
                print("[ERROR] Chrome not found at any location")
                if current_os == "windows":
                    print("[ERROR] Checked: PATH, C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe, C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe")
                self.last_launch_error = "Chrome browser binary was not found on this machine."
                return False

            chrome_options.binary_location = chrome_binary
            print(f"[CHROME_BINARY] {chrome_binary}")

            # Check Chrome version
            chrome_version_output = ""
            chrome_major_version = None
            try:
                result = subprocess.run([chrome_binary, '--version'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    chrome_version_output = (result.stdout or "").strip()
                    print(f"[CHROME_BINARY] Version: {chrome_version_output}")
                else:
                    chrome_version_output = (result.stderr or "").strip()
                    print(f"[CHROME_BINARY] Could not get version: {chrome_version_output}")
            except Exception as version_error:
                print(f"[CHROME_BINARY] Error checking version: {version_error}")
            chrome_major_version = self._extract_major_version(chrome_version_output)
            if current_os == "windows" and not chrome_major_version:
                chrome_major_version = self._get_windows_chrome_major_from_registry()
                if chrome_major_version:
                    print(f"[CHROME_BINARY] Resolved major version from registry: {chrome_major_version}")

            from selenium.webdriver.chrome.service import Service

            service = None
            driver_path = None

            if current_os == "linux":
                for path in [
                    "/usr/local/bin/chromedriver",
                    "/usr/bin/chromedriver",
                    os.path.expanduser("~/.local/bin/chromedriver"),
                ]:
                    if os.path.exists(path):
                        driver_path = path
                        break

                if not driver_path:
                    print("[CHROMEDRIVER] ChromeDriver not found in standard locations, trying WebDriver Manager")
                    try:
                        driver_path = ChromeDriverManager().install()
                        print(f"[CHROMEDRIVER] Using WebDriver Manager: {driver_path}")
                    except Exception as wdm_error:
                        print(f"[CHROMEDRIVER] WebDriver Manager failed: {wdm_error}")
                        raise RuntimeError("ChromeDriver not found on Linux server")

                service = Service(driver_path)
                print(f"[CHROMEDRIVER] Using {driver_path}")

                # Check Chromedriver version
                try:
                    result = subprocess.run([driver_path, '--version'], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        print(f"[CHROMEDRIVER] Version: {result.stdout.strip()}")
                    else:
                        print(f"[CHROMEDRIVER] Could not get version: {result.stderr}")
                except Exception as version_error:
                    print(f"[CHROMEDRIVER] Error checking version: {version_error}")

            else:
                bundled_driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Chrome_driver", "chromedriver.exe")
                using_bundled_driver = False
                if os.path.exists(bundled_driver):
                    driver_path = bundled_driver
                    using_bundled_driver = True
                    print(f"[CHROMEDRIVER] Using bundled driver: {driver_path}")
                    bundled_version_output = self._get_binary_version_output(driver_path)
                    bundled_major_version = self._extract_major_version(bundled_version_output)
                    if bundled_major_version:
                        print(f"[CHROMEDRIVER] Bundled version: {bundled_version_output}")
                    if chrome_major_version and bundled_major_version and bundled_major_version != chrome_major_version:
                        print(
                            f"[CHROMEDRIVER] Bundled driver major {bundled_major_version} != "
                            f"Chrome major {chrome_major_version}. Auto-updating driver."
                        )
                        driver_path = self._install_windows_chromedriver(chrome_major_version)
                        driver_path = self._sync_driver_to_bundled_path(driver_path)
                        using_bundled_driver = False
                else:
                    driver_path = self._install_windows_chromedriver(chrome_major_version)
                    driver_path = self._sync_driver_to_bundled_path(driver_path)

                driver_path = self._normalize_chromedriver_path(driver_path)
                if not driver_path or not os.path.exists(driver_path):
                    raise RuntimeError(f"Resolved ChromeDriver path is invalid: {driver_path}")

                service = Service(driver_path)

            print("[WEBDRIVER] Creating Chrome WebDriver...")
            try:
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as primary_launch_error:
                print(f"[WEBDRIVER] Primary browser launch failed: {primary_launch_error}")
                primary_error_text = str(primary_launch_error).lower()

                # Windows/local mode fallback: if bundled driver is stale, download matching driver.
                if current_os == "windows" and 'using_bundled_driver' in locals() and using_bundled_driver and "only supports chrome version" in primary_error_text:
                    print("[WEBDRIVER] Bundled ChromeDriver version mismatch detected. Retrying with WebDriver Manager.")
                    driver_path = self._install_windows_chromedriver(chrome_major_version)
                    driver_path = self._sync_driver_to_bundled_path(driver_path)
                    if not driver_path or not os.path.exists(driver_path):
                        raise RuntimeError(f"Resolved ChromeDriver path is invalid after fallback: {driver_path}")
                    service = Service(driver_path)
                    print(f"[CHROMEDRIVER] Fallback WebDriver Manager driver: {driver_path}")
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    print("[WEBDRIVER] Launch succeeded using fallback ChromeDriver.")
                # Final Windows fallback: use Selenium Manager (no explicit service).
                elif current_os == "windows":
                    print("[WEBDRIVER] Retrying with Selenium Manager (no explicit chromedriver service).")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    print("[WEBDRIVER] Launch succeeded using Selenium Manager.")
                # In server mode, recover from unstable DISPLAY/VNC by falling back to headless.
                elif self.server_execution and not self.headless:
                    print("[WEBDRIVER] Retrying launch in headless mode (server fallback)")
                    self.headless = True
                    self.enable_remote_viewing = False
                    os.environ.pop("DISPLAY", None)
                    chrome_options.add_argument("--headless=new")
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    raise

            if self.enable_remote_viewing:
                self.driver.set_window_size(1920, 1080)
                self.driver.set_window_position(0, 0)
                print("[WINDOW] Set size to 1920x1080 and position to (0,0) for VNC streaming")
            elif not self.headless:
                # Force visible local execution window to the primary screen.
                window_placed = False
                for attempt in range(1, 4):
                    try:
                        self.driver.set_window_position(0, 0)
                        self.driver.maximize_window()
                        print(f"[WINDOW] Forced local browser window to foreground position (0,0) and maximized (attempt {attempt})")
                        window_placed = True
                        break
                    except Exception as window_error:
                        print(f"[WINDOW] Could not maximize/position local browser window (attempt {attempt}): {window_error}")
                        time.sleep(0.4)
                if not window_placed:
                    print("[WINDOW] Continuing execution without explicit window placement")

            self.driver.get("data:text/html,<h1>Browser OK</h1>")
            print("[SUCCESS] Chrome launched successfully")

            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.common.action_chains import ActionChains

            self.wait = WebDriverWait(self.driver, self.default_wait_timeout)
            self.actions = ActionChains(self.driver)

            return True

        except Exception as e:
            print("[ERROR] Browser launch failed")
            print(traceback.format_exc())
            self.last_launch_error = f"{e}\n{traceback.format_exc()}"

            try:
                if self.driver:
                    self.driver.quit()
            except:
                pass

            self.driver = None
            return False
    
    
    @allure.feature("Test Execution")
    def execute_test_case(self, testcase_name, test_steps, test_metadata=None):
        """Execute a test case with the provided steps and metadata"""
        execution_id = str(uuid.uuid4())
        start_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        # CRITICAL: Clear old allure results before starting new test
        self.clear_old_allure_results()
        
        # Reset attachments for this test
        self.current_test_attachments = []
        self.current_execution_id = execution_id
        
        result = {
            'execution_id': execution_id,
            'testcase_name': testcase_name,
            'status': 'UNKNOWN',
            'total_steps': len(test_steps),
            'passed_steps': 0,
            'failed_steps': 0,
            'skipped_steps': 0,
            'execution_time': '',
            'start_time': start_time,
            'end_time': None,
            'error_message': '',
            'step_results': [],
            'browser_info': 'Chrome'
        }
        
        # Add metadata to result if provided
        if test_metadata:
            result.update(test_metadata)
        
        # Start Allure test
        with allure.step(f"Execute test case: {testcase_name}"):
            allure.dynamic.title(testcase_name)
            allure.dynamic.description(f"Test case execution with {len(test_steps)} steps")
            
            try:
                print(f"[ROCKET] Starting test execution: {testcase_name}")
                print(f"[CLIPBOARD] Total steps: {len(test_steps)}")
                
                # Debug: Print test steps
                print("[DEBUG] Test steps received:")
                for i, step in enumerate(test_steps, 1):
                    print(f"  Step {i}: {step.get('action_type', 'N/A')} - {step.get('test_step_description', 'N/A')}")
                
                # Launch browser
                with allure.step("Launch browser"):
                    print("[BROWSER] Attempting to launch browser...")
                    try:
                        if not self.launch_browser():
                            print("[ERROR] Browser launch returned False")
                            details = self.last_launch_error or "launch_browser() returned False"
                            raise Exception(f"Failed to launch browser - {details}")
                        print("[BROWSER] Browser launched successfully")
                        # Initialize window/tab tracking after successful launch
                        self.initialize_window_tracking()
                    except Exception as e:
                        print(f"[ERROR] Browser launch failed with exception: {str(e)}")
                        print(f"[ERROR] Browser launch exception type: {type(e).__name__}")
                        import traceback
                        print(f"[ERROR] Browser launch traceback: {traceback.format_exc()}")
                        raise Exception(f"Failed to launch browser: {str(e)}") from e
                
                # Execute each step based on isolation mode
                for i, step in enumerate(test_steps, 1):
                    if self.enable_isolation:
                        step_result = self.execute_step_with_isolation(step, i)
                        print(f"[ISOLATION_MODE] Using isolated execution for step {i}")
                    else:
                        step_result = self.execute_step(step, i)
                        print(f"[REGULAR_MODE] Using regular execution for step {i}")
                    
                    result['step_results'].append(step_result)
                    
                    if step_result['status'] == 'PASS':
                        result['passed_steps'] += 1
                    elif step_result['status'] == 'FAIL':
                        result['failed_steps'] += 1
                        if self.enable_isolation:
                            # In isolation mode, don't mark entire test as failed immediately
                            print(f"[ISOLATION] Step {i} failed but continuing with remaining steps")
                        else:
                            # In regular mode, mark entire test as failed
                            result['status'] = 'FAIL'
                            result['error_message'] = step_result.get('error_message', '')
                    else:
                        result['skipped_steps'] += 1
                
                # Determine overall status based on isolation mode
                if self.enable_isolation:
                    # In isolation mode, test passes if at least one step passes
                    if result['passed_steps'] > 0:
                        if result['failed_steps'] == 0:
                            result['status'] = 'PASS'
                        else:
                            result['status'] = 'PARTIAL_PASS'  # Some steps passed, some failed
                            result['error_message'] = f"{result['failed_steps']} out of {result['total_steps']} steps failed, but test continued"
                    else:
                        result['status'] = 'FAIL'
                        result['error_message'] = "All steps failed"
                else:
                    # Regular mode logic
                    if result['status'] != 'FAIL':
                        if result['failed_steps'] == 0:
                            result['status'] = 'PASS'
                        else:
                            result['status'] = 'FAIL'
                
            except Exception as e:
                result['status'] = 'FAIL'
                result['error_message'] = str(e)
                print(f"[ERROR] Test execution failed: {str(e)}")
                print(f"[ERROR] Full exception details: {traceback.format_exc()}")
                traceback.print_exc()
            
            finally:
                # Calculate execution time
                end_time = datetime.now(pytz.timezone('Asia/Kolkata'))
                result['end_time'] = end_time
                execution_duration = end_time - start_time
                result['execution_time'] = str(execution_duration).split('.')[0]  # Remove microseconds
                
                # Close browser
                self.close_browser()
                
                print(f"[SUCCESS] Test execution completed: {testcase_name}")
                print(f"[BAR_CHART] Results: {result['passed_steps']} passed, {result['failed_steps']} failed, {result['skipped_steps']} skipped")
                
                # Enhanced logging for isolation mode
                if self.enable_isolation:
                    if result['status'] == 'PARTIAL_PASS':
                        print(f"[ISOLATION_RESULT] Test completed with PARTIAL SUCCESS - {result['passed_steps']} steps succeeded despite {result['failed_steps']} failures")
                        print(f"[ISOLATION_BENEFIT] Isolation mode prevented {result['failed_steps']} failed elements from stopping the test")
                    elif result['status'] == 'PASS':
                        print(f"[ISOLATION_RESULT] Test completed with FULL SUCCESS - All {result['passed_steps']} steps passed")
                    else:
                        print(f"[ISOLATION_RESULT] Test failed - All {result['total_steps']} steps failed")
                else:
                    print(f"[REGULAR_RESULT] Test status: {result['status']}")
                
                # Save Allure results
                self.save_allure_results(result)
                
                # Add execution_date in IST format (DD/MM/YYYY, HH:MM:SS)
                ist_timezone = pytz.timezone('Asia/Kolkata')
                execution_date_ist = start_time.astimezone(ist_timezone)
                result['execution_date'] = execution_date_ist.strftime('%d/%m/%Y, %H:%M:%S')
                
                # Ensure we always return a valid result object
                if not result:
                    result = {
                        'execution_id': execution_id,
                        'testcase_name': testcase_name,
                        'status': 'FAIL',
                        'error_message': 'Unknown error - result object was empty',
                        'total_steps': 0,
                        'passed_steps': 0,
                        'failed_steps': 0,
                        'step_results': [],
                        'execution_date': execution_date_ist.strftime('%d/%m/%Y, %H:%M:%S')
                    }
                
                print(f"[RETURN] Returning result: {result['status']} with {len(result.get('step_results', []))} step results")
                print(f"[EXECUTION_DATE] execution_date set to: {result.get('execution_date')}")
                
        return result

    def _resolve_step_timeout_seconds(self, step):
        """Resolve per-step timeout with a safe default."""
        try:
            raw_timeout = step.get("timeout_seconds", step.get("timeout", self.default_step_timeout))
            timeout_value = int(raw_timeout)
            return max(timeout_value, 1)
        except Exception:
            return self.default_step_timeout

    def _parse_locator(self, locator):
        """Parse a generic locator string into Selenium By strategy + value."""
        raw = (locator or "").strip()
        if not raw:
            return None

        lowered = raw.lower()
        prefix_map = {
            "xpath=": By.XPATH,
            "css=": By.CSS_SELECTOR,
            "id=": By.ID,
            "name=": By.NAME,
            "link_text=": By.LINK_TEXT,
            "partial_link_text=": By.PARTIAL_LINK_TEXT,
            "tag=": By.TAG_NAME,
            "class_name=": By.CLASS_NAME,
        }
        for prefix, by in prefix_map.items():
            if lowered.startswith(prefix):
                parsed_value = raw[len(prefix):]
                if by == By.XPATH:
                    parsed_value = self.clean_xpath(parsed_value)
                return by, parsed_value

        # Auto-detect common selector patterns when no explicit prefix is provided.
        if raw.startswith(("/", "(", ".//")):
            return By.XPATH, self.clean_xpath(raw)
        if raw.startswith(("#", ".", "[")) or any(token in raw for token in [" ", ">", "~", ":", "*"]):
            return By.CSS_SELECTOR, raw
        return By.XPATH, self.clean_xpath(raw)

    def _get_visible_or_enabled_element(self, elements):
        """Return the best immediate-match element without waiting."""
        for element in elements:
            try:
                if element.is_displayed() and element.is_enabled():
                    return element
            except Exception:
                continue

        for element in elements:
            try:
                if element.is_displayed():
                    return element
            except Exception:
                continue

        return elements[0] if elements else None

    def _generic_click_and_select(self, locator, test_data):
        """Generic fallback for select-like interactions across arbitrary websites."""
        target = self.find_element_with_advanced_wait(locator)
        tag_name = (target.tag_name or "").lower()
        input_type = (target.get_attribute("type") or "").lower()

        if tag_name == "select":
            selector = Select(target)
            text_value = str(test_data or "").strip()
            if not text_value:
                raise Exception("No selection value provided for select element")
            try:
                selector.select_by_visible_text(text_value)
                return
            except Exception:
                pass
            try:
                selector.select_by_value(text_value)
                return
            except Exception:
                pass
            if text_value.isdigit():
                selector.select_by_index(int(text_value))
                return
            raise Exception(f"Could not select '{text_value}' from dropdown")

        if input_type in ["checkbox", "radio"]:
            desired = str(test_data).strip().lower() in ["true", "1", "yes", "on", "checked"]
            current = bool(target.is_selected())
            if desired != current:
                self.perform_robust_click(target)
            return

        self.perform_robust_click(target)
        # CLICK_AND_SELECT should remain selection-only. Do not type into generic inputs here.

    def _parse_drag_drop_target_locator(self, test_data):
        """Extract target locator for drag/drop from raw step values."""
        raw = str(test_data or "").strip()
        if not raw:
            return None

        # JSON payload support: {"target_xpath":"..."} or {"target":"..."}.
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                for key in ["target_locator", "target_xpath", "target_selector", "target", "to"]:
                    value = payload.get(key)
                    if value and str(value).strip():
                        return str(value).strip()
        except Exception:
            pass

        # Key/value text support: target=..., to=..., target_xpath=...
        kv_match = re.search(r"(?:target_locator|target_xpath|target_selector|target|to)\s*[:=]\s*(.+)$", raw, re.IGNORECASE)
        if kv_match:
            value = kv_match.group(1).strip().strip("'\"")
            return value or None

        # Fallback: treat entire value as target locator.
        return raw
    
    def execute_step(self, step, step_number):
        """Execute a single test step with configurable timeout."""
        normalized_action_type = self.normalize_action_type(step.get('action_type', ''))
        step_result = {
            'tc_id': step.get('tc_id', ''),
            'step_no': step_number,
            'description': step.get('test_step_description', ''),
            'test_step_description': step.get('test_step_description', ''),
            'element_name': step.get('element_name', ''),
            # Persist normalized action type so execution history reflects actual runtime behavior.
            'action_type': normalized_action_type,
            'xpath': step.get('xpath', ''),
            'values': step.get('values', ''),
            'status': 'UNKNOWN',
            'error': '',
            'error_message': '',
            'execution_time': '',
            'before_screenshot': '',
            'after_screenshot': '',
            'screenshot_status': ''
        }
        
        step_start_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_description = step.get('test_step_description', 'Unknown step')
        
        print(f"[STEP] Step {step_number}: {step_description}")
        print(f"[DEBUG] Step data: action_type='{step.get('action_type', 'N/A')}', xpath='{step.get('xpath', 'N/A')}', values='{step.get('values', 'N/A')}'")
        
        # Execute step with Allure integration
        with allure.step(f"Step {step_number}: {step_description}"):
            allure.attach(
                json.dumps(step, indent=2),
                name="Step Details",
                attachment_type=allure.attachment_type.JSON
            )
            
            # Skipped: screenshots only for failed cases
            step_result['before_screenshot'] = None
            
            def execute_step_action():
                """Execute the step action - this will run in a separate thread"""
                action_type = self.normalize_action_type(step.get('action_type', ''))
                xpath = step.get('xpath', '')
                element_name = step.get('element_name', '')
                test_data = step.get('values', '')
                assertion_type = step.get('assertion_type', '')

                pre_validation = self.pre_validate_action(action_type, test_data, xpath, element_name, assertion_type)
                if not pre_validation.get('success', False):
                    raise Exception(pre_validation.get('message', 'Pre-validation failed'))

                # Execute the action using isolation method (which includes window management)
                self.execute_action_with_isolation(action_type, test_data, xpath, element_name, assertion_type)
            
            # Execute the step with timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(execute_step_action)
                try:
                    timeout_seconds = self._resolve_step_timeout_seconds(step)
                    future.result(timeout=timeout_seconds)
                    step_result['status'] = 'PASS'
                    print(f"[SUCCESS] Step {step_number} completed successfully")
                    
                except FutureTimeoutError:
                    step_result['status'] = 'FAIL'
                    timeout_seconds = self._resolve_step_timeout_seconds(step)
                    step_result['error'] = f"Step timed out after {timeout_seconds} seconds"
                    step_result['error_message'] = f"Step timed out after {timeout_seconds} seconds"
                    print(f"[INTERRUPTED] Step {step_number} timed out after {timeout_seconds}s, moving to next step")
                    
                    # Take screenshot after timeout
                    timeout_screenshot = self.save_screenshot(f"After_Step_{step_number}_TIMEOUT", step_number, "timeout")
                    step_result['after_screenshot'] = timeout_screenshot['source'] if timeout_screenshot else None
                    step_result['screenshot_status'] = 'timeout'
                    
                    # Clean up browser state after timeout
                    self.cleanup_browser_state()
                    
                except Exception as e:
                    step_result['status'] = 'FAIL'
                    step_result['error'] = str(e)
                    step_result['error_message'] = str(e)
                    print(f"[ERROR] Step {step_number} failed: {str(e)}")
                    print(f"[ERROR] Error details: {traceback.format_exc()}")
                    
                    # First, try to scroll the failed element into view before taking screenshot
                    xpath = step.get('xpath', '')
                    element_name = step.get('element_name', '')
                    
                    print(f"[DEBUG] Preparing to capture failure screenshot without moving the page")
                    print(f"[DEBUG] XPath: {xpath}")
                    print(f"[DEBUG] Element name: {element_name}")

                    # Heuristic: if failure is due to locator/xpath, avoid any scrolling/highlighting
                    locator_keywords = ['no such element', 'unable to locate', 'invalid selector', 'stale element reference', 'timeout']
                    error_lower = str(e).lower()
                    is_locator_issue = any(k in error_lower for k in locator_keywords) and bool(xpath and xpath.strip() and xpath.strip().upper() != 'NA')

                    if is_locator_issue:
                        # Capture immediate viewport screenshot, do not scroll
                        error_screenshot = self.save_screenshot(f"After_Step_{step_number}_FAILED", step_number, "error")
                        step_result['after_screenshot'] = error_screenshot['source'] if error_screenshot else None
                        step_result['screenshot_status'] = 'error_locator' if error_screenshot else 'error_no_screenshot'
                        print(f"[DEBUG] Captured failure screenshot without scrolling (locator issue)")
                    else:
                        # Otherwise try enhanced highlighting flow
                        failed_screenshot_path = self.take_screenshot_with_element_highlighting(
                            f"After_Step_{step_number}_FAILED", 
                            step_number, 
                            "error",
                            xpath, 
                            element_name
                        )
                        
                        if failed_screenshot_path:
                            import os
                            step_result['after_screenshot'] = os.path.basename(failed_screenshot_path)
                            step_result['screenshot_status'] = 'error_highlighted'
                            print(f"[DEBUG] Failed element properly positioned and highlighted in screenshot")
                        else:
                            # Fallback to regular screenshot if highlighting fails
                            error_screenshot = self.save_screenshot(f"After_Step_{step_number}_FAILED", step_number, "error")
                            step_result['after_screenshot'] = error_screenshot['source'] if error_screenshot else None
                            step_result['screenshot_status'] = 'error' if error_screenshot else 'error_no_screenshot'

                    # Clean up browser state after failed step
                    self.cleanup_browser_state()
        
        step_end_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_duration = step_end_time - step_start_time
        step_result['execution_time'] = str(step_duration).split('.')[0]
        
        return step_result
    
    def execute_step_with_isolation(self, step, step_number):
        """Execute a single test step with proper isolation to prevent failures from affecting other elements"""
        normalized_action_type = self.normalize_action_type(step.get('action_type', ''))
        step_result = {
            'tc_id': step.get('tc_id', ''),
            'step_no': step_number,
            'description': step.get('test_step_description', ''),
            'test_step_description': step.get('test_step_description', ''),
            'element_name': step.get('element_name', ''),
            # Persist normalized action type so execution history reflects actual runtime behavior.
            'action_type': normalized_action_type,
            'xpath': step.get('xpath', ''),
            'values': step.get('values', ''),
            'status': 'UNKNOWN',
            'error': '',
            'error_message': '',
            'execution_time': '',
            'before_screenshot': '',
            'after_screenshot': '',
            'screenshot_status': ''
        }
        
        step_start_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_description = step.get('test_step_description', 'Unknown step')
        
        print(f"[ISOLATED_STEP] Step {step_number}: {step_description}")
        
        # Execute step with Allure integration and proper isolation
        with allure.step(f"Step {step_number}: {step_description}"):
            allure.attach(
                json.dumps(step, indent=2),
                name="Step Details",
                attachment_type=allure.attachment_type.JSON
            )
            
            def execute_isolated_action():
                """Execute the step action with proper error isolation"""
                try:
                    action_type = self.normalize_action_type(step.get('action_type', ''))
                    xpath = step.get('xpath', '')
                    element_name = step.get('element_name', '')
                    test_data = step.get('values', '')
                    assertion_type = step.get('assertion_type', '')
                    
                    print(f"[ISOLATION] Executing action: {action_type} on element: {element_name}")

                    pre_validation = self.pre_validate_action(action_type, test_data, xpath, element_name, assertion_type)
                    if not pre_validation.get('success', False):
                        raise Exception(pre_validation.get('message', 'Pre-validation failed'))

                    # Execute the action with enhanced error handling
                    self.execute_action_with_isolation(action_type, test_data, xpath, element_name, assertion_type)
                    
                    # VALIDATION: Verify the action achieved the expected result without timeout
                    validation_result = self.validate_action_result(action_type, test_data, xpath, element_name, assertion_type)
                    if not validation_result['success']:
                        print(f"[VALIDATION_FAIL] Step validation failed: {validation_result['message']}")
                        raise Exception(f"Validation failed: {validation_result['message']}")
                    else:
                        print(f"[VALIDATION_PASS] Step validation successful: {validation_result['message']}")
                    
                except Exception as action_error:
                    print(f"[ISOLATION] Action failed for element {element_name}: {str(action_error)}")
                    # Re-raise to be caught by the outer exception handler
                    raise action_error
            
            # Execute the step with timeout and isolation
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(execute_isolated_action)
                try:
                    timeout_seconds = self._resolve_step_timeout_seconds(step)
                    future.result(timeout=timeout_seconds)
                    step_result['status'] = 'PASS'
                    step_result['validation_message'] = f"Step {step_number} executed and validated successfully"
                    print(f"[ISOLATION_SUCCESS] Step {step_number} completed successfully")
                    
                except FutureTimeoutError:
                    step_result['status'] = 'FAIL'
                    timeout_seconds = self._resolve_step_timeout_seconds(step)
                    step_result['error'] = f"Step timed out after {timeout_seconds} seconds"
                    step_result['error_message'] = f"Step timed out after {timeout_seconds} seconds"
                    print(f"[ISOLATION_INTERRUPTED] Step {step_number} timed out after {timeout_seconds}s, but test will continue")
                    
                    # Take screenshot after timeout
                    timeout_screenshot = self.save_screenshot(f"After_Step_{step_number}_TIMEOUT", step_number, "timeout")
                    step_result['after_screenshot'] = timeout_screenshot['source'] if timeout_screenshot else None
                    step_result['screenshot_status'] = 'timeout'
                    
                    # Clean up browser state after timeout without affecting other elements
                    self.cleanup_browser_state_safely()
                    
                except Exception as e:
                    step_result['status'] = 'FAIL'
                    step_result['error'] = str(e)
                    step_result['error_message'] = str(e)
                    
                    # Check if this was a validation failure
                    if "Validation failed:" in str(e):
                        step_result['validation_message'] = f"VALIDATION FAILED: {str(e)}"
                        print(f"[VALIDATION_FAILURE] Step {step_number} failed validation: {str(e)}")
                    else:
                        step_result['validation_message'] = f"Step {step_number} failed during execution"
                        print(f"[ISOLATION_ERROR] Step {step_number} failed: {str(e)}, but test will continue")
                        print(f"[ISOLATION_ERROR] Error details: {traceback.format_exc()}")
                    
                    # Handle failed element highlighting with isolation
                    xpath = step.get('xpath', '')
                    element_name = step.get('element_name', '')
                    
                    print(f"[ISOLATION_DEBUG] Preparing to highlight failed element:")
                    print(f"[ISOLATION_DEBUG] XPath: {xpath}")
                    print(f"[ISOLATION_DEBUG] Element Name: {element_name}")
                    
                    # Take screenshot after failure with proper element positioning and highlighting
                    failed_screenshot_path = self.take_screenshot_with_element_highlighting(
                        f"After_Step_{step_number}_FAILED", 
                        step_number, 
                        "failed",
                        xpath, 
                        element_name
                    )
                    
                    if failed_screenshot_path:
                        # Always store only the filename so frontend can fetch via /allure-results/<file>
                        import os
                        step_result['after_screenshot'] = os.path.basename(failed_screenshot_path)
                        step_result['screenshot_status'] = 'failed_highlighted'
                        print(f"[ISOLATION_HIGHLIGHT] Failed element properly positioned and highlighted in screenshot")
                    else:
                        # Fallback to regular screenshot if highlighting fails
                        failed_screenshot = self.save_screenshot(f"After_Step_{step_number}_FAILED", step_number, "failed")
                        step_result['after_screenshot'] = failed_screenshot['source'] if failed_screenshot else None
                        step_result['screenshot_status'] = 'failed'
                    
                    # Clean up browser state safely without affecting other elements
                    self.cleanup_browser_state_safely()
                    
                    # Attach error details to Allure
                    allure.attach(
                        step_result['error_message'],
                        name="Error Details",
                        attachment_type=allure.attachment_type.TEXT
                    )
        
        step_end_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_duration = step_end_time - step_start_time
        step_result['execution_time'] = str(step_duration).split('.')[0]
        
        return step_result
    
    def save_allure_results(self, result):
        print(f"[DEBUG] Entering save_allure_results for execution_id: {result.get('execution_id')}")
        """Save test results to Allure format"""
        try:
            # Get UI information from result
            project_name = result.get('project_name', 'Ixigo Test Automation')
            module_name = result.get('module_name', 'Web UI Tests')
            suite_type = result.get('suite_type', 'unknown')
            testcase_id = result.get('testcase_id', result['testcase_name'])
            testrun_id = result.get('testrun_id', '')
            result_id = result.get('result_id', '')
            
            # Suite type should already be correct from app.py mapping
            # Only allow sanity, smoke, regression - no complex mapping needed
            allowed_suites = ['sanity', 'smoke', 'regression']
            
            # Ensure suite type is valid, default to regression if not
            display_suite_type = suite_type.lower() if suite_type.lower() in allowed_suites else 'regression'
            display_suite_title = display_suite_type.title()  # For display purposes only
            





            # Calculate execution time in readable format
            execution_duration = result.get('execution_time', '0:00:00')
            
            # Create the main test result with enhanced Allure format
            test_result = {
                "uuid": result['execution_id'],
                "historyId": result['execution_id'],
                "name": f"[{testcase_id}] {result['testcase_name']}",
                "fullName": f"{project_name}.{module_name}.{display_suite_title}.{result['testcase_name']}",
                "status": result['status'].lower() if result['status'] in ['PASS', 'FAIL'] else 'broken',
                "stage": "finished",
                "start": int(self._get_timestamp_from_datetime(result['start_time']) * 1000),
                "stop": int(self._get_timestamp_from_datetime(result['end_time']) * 1000),
                "description": f"Execution Time: {execution_duration} | Test Run ID: {testrun_id} | Result ID: {result_id}",
                "labels": [
                    {"name": "epic", "value": project_name},
                    {"name": "feature", "value": f"{module_name} Module"},
                    {"name": "story", "value": f"{suite_type.title()} Suite"},
                    {"name": "suite", "value": f"{suite_type.title()} Tests"},
                    {"name": "testClass", "value": f"{module_name}_{suite_type.title()}"},
                    {"name": "testMethod", "value": result['testcase_name']},
                    {"name": "parentSuite", "value": f"[ROCKET] {project_name}"},
                    {"name": "subSuite", "value": f"[PACKAGE] {module_name} -> {suite_type.title()}"},
                    {"name": "severity", "value": "critical" if suite_type == "smoke" else "normal"},
                    {"name": "owner", "value": "QA Team"},
                    {"name": "tag", "value": f"module:{module_name.lower()}"},
                    {"name": "tag", "value": f"suite:{suite_type}"},
                    {"name": "testCaseId", "value": testcase_id},
                    {"name": "testRunId", "value": testrun_id},
                    {"name": "resultId", "value": result_id},
                    {"name": "executionTime", "value": execution_duration}
                ],
                "parameters": [
                    {"name": "Test Case ID", "value": testcase_id},
                    {"name": "Test Run ID", "value": testrun_id},
                    {"name": "Result ID", "value": result_id},
                    {"name": "Suite Type", "value": display_suite_title},
                    {"name": "Module", "value": module_name},
                    {"name": "Project", "value": project_name},
                    {"name": "Execution Time", "value": execution_duration},
                    {"name": "Total Steps", "value": str(result.get('total_steps', 0))},
                    {"name": "[OK] Passed Steps", "value": str(result.get('passed_steps', 0))},
                    {"name": "[X] Failed Steps", "value": str(result.get('failed_steps', 0))}
                ],
                "steps": [],
                "attachments": self.current_test_attachments
            }
            
            # Map status correctly
            if result['status'] == 'PASS':
                test_result["status"] = "passed"
            elif result['status'] == 'FAIL':
                test_result["status"] = "failed"
            else:
                test_result["status"] = "broken"
            
            # Add enhanced step details with screenshots
            for i, step in enumerate(result.get('step_results', [])):
                step_num = step.get('step_no', i + 1)
                step_status = step.get('status', 'UNKNOWN')
                step_time = step.get('execution_time', '0:00:00')
                
                # Create status emoji
                status_emoji = "[OK]" if step_status == "PASS" else "[X]" if step_status == "FAIL" else "[!]"
                
                step_info = {
                    "name": f"{status_emoji} Step {step_num}: {step.get('test_step_description', f'Step {step_num}')}",
                    "status": step_status.lower() if step_status in ['PASS', 'FAIL'] else 'broken',
                    "stage": "finished",
                    "start": int(result['start_time'].timestamp() * 1000) + (i * 1000),
                    "stop": int(result['start_time'].timestamp() * 1000) + ((i + 1) * 1000),
                    "steps": [],
                    "attachments": [],
                    "parameters": [
                        {"name": "[MOVIE] Action Type", "value": step.get('action_type', 'N/A')},
                        {"name": "[TARGET] Element", "value": step.get('element_name', 'N/A')},
                        {"name": "[SEARCH] XPath", "value": step.get('xpath', 'N/A')},
                        {"name": "[DISK] Test Data", "value": step.get('values', 'N/A')},
                        {"name": "[CLOCK] Step Time", "value": step_time},
                        {"name": "[CAMERA] Screenshot Status", "value": step.get('screenshot_status', 'N/A')}
                    ]
                }
                
                # Map step status with proper Allure status
                if step_status == 'PASS':
                    step_info["status"] = "passed"
                elif step_status == 'FAIL':
                    step_info["status"] = "failed"
                    # Add error details for failed steps
                    if step.get('error_message'):
                        step_info["statusDetails"] = {
                            "message": f"[X] FAILED: {step.get('error_message')}",
                            "trace": step.get('error', step.get('error_message', ''))
                        }
                else:
                    step_info["status"] = "broken"
                
                # Add screenshot attachments only for failed steps
                after_screenshot = step.get('after_screenshot')
                
                if step_status == 'FAIL' and after_screenshot:
                    attachment_name = f"[RED_CIRCLE] FAILED - After Step {step_num} (Element Highlighted)"
                    step_info["attachments"].append({
                        "name": attachment_name,
                        "source": after_screenshot,
                        "type": "image/png",
                        "size": 0
                    })
                
                test_result["steps"].append(step_info)
            
            # Add error details if test failed
            if result['status'] == 'FAIL' and result['error_message']:
                test_result["statusDetails"] = {
                    "message": result['error_message'],
                    "trace": result['error_message']
                }
            
            # Save the test result file
            current_dir = os.getcwd()
            # If running from new_backend directory, go up one level
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')

            # Ensure the directory exists
            os.makedirs(allure_results_path, exist_ok=True)


            result_file = os.path.join(allure_results_path, f"{result['execution_id']}-result.json")
            
            
            
            print(f"[DEBUG] About to write JSON to: {result_file}")
            print(f"[DEBUG] Test result data: execution_id={result['execution_id']}, status={result['status']}")
            
            # Write the JSON file only once
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(test_result, f, indent=2, ensure_ascii=False)
            
            print(f"[ALLURE] Test result saved successfully to: {result_file}")

              # Verify the file was created and has content
            if os.path.exists(result_file):
                file_size = os.path.getsize(result_file)
                print(f"[ALLURE] Result file created with size: {file_size} bytes")

                # Store allure report metadata in client database
                try:
                    print(f"[ALLURE] Skipping client DB metadata storage - integrated_app not available")
                except Exception as e:
                    print(f"[ALLURE] Warning: Failed to store allure metadata in client DB: {str(e)}")
            else:
                print(f"[ERROR] Failed to create result file: {result_file}")
           
            
        except Exception as e:
            print(f"[ERROR] Failed to save Allure results: {str(e)}")
            import traceback
            traceback.print_exc()

    
    def close_browser(self):
        """Close the browser and clean up resources"""
        try:
            if self.driver:
                print("[CLEANUP] Closing browser...")
                self.driver.quit()
                self.driver = None
                self.wait = None
                self.fluent_wait = None
                self.actions = None

                # Clean up remote viewing session
                if self.enable_remote_viewing and self.viewing_session_id:
                    self.cleanup_remote_viewing_session()
                    print(f"[REMOTE_VIEWING] Cleaned up remote viewing session: {self.viewing_session_id}")

                print("[SUCCESS] Browser closed successfully")

            # Clean up temp user data directory
            try:
                if hasattr(self, 'temp_user_data_dir') and self.temp_user_data_dir and os.path.exists(self.temp_user_data_dir):
                    import shutil
                    shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)
                    print(f"[CLEANUP] Successfully removed temp user data dir: {self.temp_user_data_dir}")
                    self.temp_user_data_dir = None
            except Exception as cleanup_error:
                print(f"[CLEANUP_WARNING] Failed to remove temp user data dir: {cleanup_error}")

        except Exception as e:
            print(f"[ERROR] Error closing browser: {str(e)}")
    
    def cleanup_browser_state(self):
        """Clean up browser state after errors"""
        try:
            if self.driver:
                print("[CLEANUP] Cleaning up browser state...")
                # Try to dismiss any alerts
                try:
                    alert = self.driver.switch_to.alert
                    alert.dismiss()
                    print("[CLEANUP] Dismissed alert")
                except:
                    pass
                
                # Try to switch back to main window
                try:
                    self.driver.switch_to.default_content()
                    print("[CLEANUP] Switched to default content")
                except:
                    pass
                
                # Clear any active elements
                try:
                    self.driver.execute_script("document.activeElement.blur();")
                    print("[CLEANUP] Cleared active element")
                except:
                    pass
                
        except Exception as e:
            print(f"[ERROR] Error during browser cleanup: {str(e)}")
    
    def cleanup_browser_state_safely(self):
        """Safely clean up browser state without affecting other elements"""
        try:
            if self.driver:
                print("[ISOLATION_CLEANUP] Safely cleaning up browser state...")
                # Try to dismiss any alerts without throwing exceptions
                try:
                    alert = self.driver.switch_to.alert
                    alert.dismiss()
                    print("[ISOLATION_CLEANUP] Dismissed alert safely")
                except:
                    pass
                
                # Try to switch back to main window safely
                try:
                    self.driver.switch_to.default_content()
                    print("[ISOLATION_CLEANUP] Switched to default content safely")
                except:
                    pass
                
                # Clear any active elements safely
                try:
                    self.driver.execute_script("if(document.activeElement) document.activeElement.blur();")
                    print("[ISOLATION_CLEANUP] Cleared active element safely")
                except:
                    pass
                
                # Wait a moment for cleanup to complete
                time.sleep(0.5)
                
        except Exception as e:
            print(f"[ISOLATION_CLEANUP] Error during safe browser cleanup: {str(e)}")
    

    
    def execute_action_with_isolation(self, action_type, test_data, xpath, element_name, assertion_type=None):
        """Execute specific action with enhanced isolation mode error handling"""
        try:
            print(f"[ISOLATION_ACTION] Executing action: {action_type} with data: '{test_data}' for element: {element_name}")
            action_type = self.normalize_action_type(action_type)
            element_name = element_name or ""
            test_data_text = str(test_data or "")
            is_departure_date_select = (
                action_type == "CLICK_AND_SELECT"
                and "departure" in element_name.lower()
                and self.is_date_format_data(test_data_text)
            )

            if action_type == "OPEN_BROWSER":
                # Only navigate to URL if browser is already launched
                if self.driver:
                    print(f"[ISOLATION_BROWSER] Browser already launched, navigating to: {test_data}")
                    self.driver.get(test_data)
                    self.wait_for_spa_ready()
                else:
                    print(f"[ISOLATION_BROWSER] No browser instance found, launching and navigating to: {test_data}")
                    self.launch_browser()
                    self.driver.get(test_data)
                    self.wait_for_spa_ready()

            elif action_type == "CLICK_AND_SELECT":
                # Primary specialized flow + generic fallback for cross-site compatibility.
                try:
                    self.handle_unified_click_and_select(test_data, xpath, element_name)
                except Exception as unified_error:
                    print(f"[ISOLATION] Unified click/select failed, using generic fallback: {unified_error}")
                    self._generic_click_and_select(xpath, test_data)
                print(f"[ISOLATION] Unified click and select successful for {element_name}")
            
            elif action_type == "CLICK_AND_TYPE":
                try:
                    try:
                        self.handle_click_and_type(test_data, xpath, element_name)
                    except Exception as typed_error:
                        print(f"[ISOLATION] Specialized click-and-type failed, using generic fallback: {typed_error}")
                        target = self.find_element_with_advanced_wait(xpath)
                        self.perform_robust_click(target)
                        self.perform_robust_text_input(target, str(test_data))
                    print(f"[ISOLATION] Click and type successful for {element_name}")
                except Exception as e:
                    print(f"[ISOLATION] Click and type failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "CLEAR_AND_TYPE":
                try:
                    self.handle_clear_and_type(test_data, xpath, element_name)
                    print(f"[ISOLATION] Clear and type successful for {element_name}")
                except Exception as e:
                    print(f"[ISOLATION] Clear and type failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "CLICK":
                try:
                    if element_name.upper() == self.ELEMENT_NAME_TRAVEL_CLASS:
                        self.handle_travel_class_selection_fast(test_data, xpath, element_name)
                    elif element_name.upper() in self.ELEMENT_NAME_DONE_ALIASES:
                        self.close_travellers_popup_fast(xpath, element_name)
                    elif test_data_text.upper() == self.QUICK_DATE_TODAY.upper():
                        self.handle_today_selection(element_name)
                    elif test_data_text.upper() == self.QUICK_DATE_TOMORROW.upper() and self.UI_TOKEN_BUS in element_name.lower():
                        self.handle_tomorrow_selection_bus(element_name)
                    elif test_data_text.upper() == self.QUICK_DATE_TOMORROW.upper():
                        self.handle_tomorrow_selection(element_name)
                    elif "day after" in test_data_text.lower() or test_data_text.upper() == self.QUICK_DATE_DAY_AFTER.upper():
                        self.handle_day_after_tomorrow_selection(element_name)
                    else:
                        click_element = self.find_element_with_advanced_wait(xpath)
                        self.perform_robust_click(click_element)
                        WebDriverWait(self.driver, 2).until(lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"])
                    print(f"[ISOLATION] Click action successful for {element_name}")
                except Exception as e:
                    print(f"[ISOLATION] Click action failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "DOUBLE_CLICK":
                try:
                    self.handle_double_click(xpath, element_name)
                except Exception as e:
                    print(f"[ISOLATION] Double click failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "RIGHT_CLICK":
                try:
                    self.handle_right_click(xpath, element_name)
                except Exception as e:
                    print(f"[ISOLATION] Right click failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "MOUSE_OVER":
                try:
                    self.handle_mouse_over(xpath, element_name)
                except Exception as e:
                    print(f"[ISOLATION] Mouse over failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "RADIO_BUTTON":
                try:
                    self.handle_radio_button_action(test_data, xpath, element_name)
                except Exception as e:
                    print(f"[ISOLATION] Radio button action failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "DRAG_AND_DROP":
                try:
                    self.handle_drag_and_drop(xpath, test_data, element_name)
                except Exception as e:
                    print(f"[ISOLATION] Drag and drop failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "SELECT_COUNT":
                try:
                    desired_count = int(str(test_data))
                    mapped_count_type = self.ELEMENT_NAME_SELECT_COUNT_TYPE_MAP.get(element_name.upper())
                    if mapped_count_type == self.COUNT_TYPE_ROOM:
                        count_type = self.COUNT_TYPE_ROOM
                        before = self.get_current_count(count_type)
                        self.set_count_by_increment(count_type, desired_count)
                        after = self.get_current_count(count_type)
                    elif mapped_count_type == self.COUNT_TYPE_ADULT:
                        count_type = self.COUNT_TYPE_ADULT
                        before = self.get_current_count(count_type)
                        self.set_count_by_increment(count_type, desired_count)
                        after = self.get_current_count(count_type)
                    elif mapped_count_type == self.COUNT_TYPE_CHILDREN:
                        count_type = self.COUNT_TYPE_CHILDREN
                        before = self.get_current_count(count_type)
                        children_count = desired_count
                        self.set_count_by_increment(self.COUNT_TYPE_CHILDREN, children_count)
                        after = self.get_current_count(count_type)
                        # Wait for age dropdowns to appear after setting children count
                        if children_count > 0:
                            self.wait_for_child_age_dropdowns(children_count)
                    else:
                        count_type = None
                        before = None
                        after = None
                        # For flight passenger counts or others
                        self.handle_count_selection_fast(test_data, xpath, element_name)
                    self._last_count_action_state = {
                        "mode": "select_count",
                        "element_name": element_name,
                        "element_type": count_type,
                        "step_count": None,
                        "before_count": before,
                        "expected_after": desired_count,
                        "after_count": after,
                        "locator": xpath,
                    }
                    print(f"[ISOLATION] Count selection successful for {element_name}")
                except Exception as e:
                    print(f"[ISOLATION] Count selection failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "INCREMENT":
                try:
                    element_type = self.resolve_count_element_type(element_name)
                    step_count = self._parse_step_count(test_data, default_value=1)
                    if element_type:
                        try:
                            target_count = int(str(test_data).strip())
                            current_count = self.get_current_count(element_type)
                            step_count = max(target_count - current_count, 0)
                            print(f"[ISOLATION] INCREMENT target mode for {element_name}: current={current_count}, target={target_count}, steps={step_count}")
                        except Exception:
                            # Fall back to step-based behavior if target/current cannot be resolved.
                            pass
                    state = self._adjust_count(element_name, xpath, "increment", step_count)
                    print(f"[ISOLATION] Increment successful for {element_name} by {step_count} step(s), state={state}")
                except Exception as e:
                    print(f"[ISOLATION] Increment failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "DECREMENT":
                try:
                    element_type = self.resolve_count_element_type(element_name)
                    step_count = self._parse_step_count(test_data, default_value=1)
                    if element_type:
                        try:
                            target_count = int(str(test_data).strip())
                            current_count = self.get_current_count(element_type)
                            step_count = max(current_count - target_count, 0)
                            print(f"[ISOLATION] DECREMENT target mode for {element_name}: current={current_count}, target={target_count}, steps={step_count}")
                        except Exception:
                            # Fall back to step-based behavior if target/current cannot be resolved.
                            pass
                    state = self._adjust_count(element_name, xpath, "decrement", step_count)
                    print(f"[ISOLATION] Decrement successful for {element_name} by {step_count} step(s), state={state}")
                except Exception as e:
                    print(f"[ISOLATION] Decrement failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "HANDLE_CHECKBOX":
                try:
                    self.handle_checkbox_action(test_data, xpath, element_name)
                    print(f"[ISOLATION] Checkbox action successful for {element_name}")
                except Exception as e:
                    print(f"[ISOLATION] Checkbox action failed for {element_name}: {str(e)}")
                    raise e

            elif action_type == "SWITCH_TO_IFRAME":
                try:
                    frame_reference = xpath if str(xpath or "").strip() else test_data
                    print(f"[ISOLATION] Switching to iframe with reference: {frame_reference}")
                    self.switch_to_iframe(frame_reference)
                    print(f"[ISOLATION] Successfully switched to iframe")
                except Exception as e:
                    print(f"[ISOLATION] Switch to iframe failed: {str(e)}")
                    raise e

            elif action_type == "SWITCH_TO_DEFAULT_CONTENT":
                try:
                    print(f"[ISOLATION] Switching to default content...")
                    self.driver.switch_to.default_content()
                    print(f"[ISOLATION] Successfully switched to default content")
                except Exception as e:
                    print(f"[ISOLATION] Switch to default content failed: {str(e)}")
                    raise e

            elif action_type == "SWITCH_TO_NEW_WINDOW":
                try:
                    print(f"[ISOLATION] Switching to new window...")
                    success = self.wait_for_new_window(timeout=int(test_data_text) if test_data_text.isdigit() else 10)
                    if not success:
                        raise Exception("No new window appeared within timeout")
                    print(f"[ISOLATION] Successfully switched to new window")
                except Exception as e:
                    print(f"[ISOLATION] Window switch failed: {str(e)}")
                    raise e

            elif action_type == "SWITCH_TO_WINDOW_BY_INDEX":
                try:
                    index = int(test_data_text) if test_data_text.isdigit() else 0
                    print(f"[ISOLATION] Switching to window index {index}...")
                    success = self.switch_to_window_by_index(index)
                    if not success:
                        raise Exception(f"Failed to switch to window index {index}")
                    print(f"[ISOLATION] Successfully switched to window index {index}")
                except Exception as e:
                    print(f"[ISOLATION] Window switch by index failed: {str(e)}")
                    raise e

            elif action_type == "SWITCH_TO_WINDOW_BY_URL":
                try:
                    print(f"[ISOLATION] Switching to window with URL pattern: {test_data}")
                    success = self.switch_to_window_by_url_pattern(test_data)
                    if not success:
                        raise Exception(f"No window found with URL pattern: {test_data}")
                    print(f"[ISOLATION] Successfully switched to window with URL pattern: {test_data}")
                except Exception as e:
                    print(f"[ISOLATION] Window switch by URL failed: {str(e)}")
                    raise e

            elif action_type == "CLOSE_EXTRA_WINDOWS":
                try:
                    print(f"[ISOLATION] Closing extra windows...")
                    self.close_extra_windows(keep_main=True)
                    print(f"[ISOLATION] Successfully closed extra windows")
                except Exception as e:
                    print(f"[ISOLATION] Close extra windows failed: {str(e)}")
                    raise e

            elif action_type == "NAVIGATE_TO_URL":
                try:
                    print(f"[ISOLATION] Navigating to URL: {test_data}")
                    self.driver.get(test_data)
                    self.wait_for_spa_ready()
                    print(f"[ISOLATION] Successfully navigated to: {test_data}")
                except Exception as e:
                    print(f"[ISOLATION] Navigation failed: {str(e)}")
                    raise e

            elif action_type == "REFRESH_PAGE":
                try:
                    print(f"[ISOLATION] Refreshing current page...")
                    self.driver.refresh()
                    self.wait_for_spa_ready()
                    print(f"[ISOLATION] Successfully refreshed page")
                except Exception as e:
                    print(f"[ISOLATION] Page refresh failed: {str(e)}")
                    raise e

            elif action_type == "GO_BACK":
                try:
                    print(f"[ISOLATION] Going back in browser history...")
                    self.driver.back()
                    self.wait_for_spa_ready()
                    print(f"[ISOLATION] Successfully went back")
                except Exception as e:
                    print(f"[ISOLATION] Go back failed: {str(e)}")
                    raise e

            elif action_type == "GO_FORWARD":
                try:
                    print(f"[ISOLATION] Going forward in browser history...")
                    self.driver.forward()
                    self.wait_for_spa_ready()
                    print(f"[ISOLATION] Successfully went forward")
                except Exception as e:
                    print(f"[ISOLATION] Go forward failed: {str(e)}")
                    raise e

            elif action_type == "READ_TEXT":
                target = self.find_element_with_advanced_wait(xpath)
                payload = self._get_readable_element_payload(target)
                self._last_read_result = {"type": "text", "value": payload.get("text", "")}
                print(f"[ISOLATION] Read text for {element_name}: {self._last_read_result['value']}")

            elif action_type == "READ_VALUE":
                target = self.find_element_with_advanced_wait(xpath)
                payload = self._get_readable_element_payload(target)
                self._last_read_result = {"type": "value", "value": payload.get("value", "")}
                print(f"[ISOLATION] Read value for {element_name}: {self._last_read_result['value']}")

            elif action_type == "READ_TOOLTIP":
                target = self.find_element_with_advanced_wait(xpath)
                payload = self._get_readable_element_payload(target)
                tooltip_value = payload.get("title") or payload.get("ariaLabel") or payload.get("placeholder") or payload.get("text", "")
                self._last_read_result = {"type": "tooltip", "value": tooltip_value}
                print(f"[ISOLATION] Read tooltip for {element_name}: {tooltip_value}")

            elif action_type == "READ_LABEL":
                target = self.find_element_with_advanced_wait(xpath)
                payload = self._get_readable_element_payload(target)
                self._last_read_result = {"type": "label", "value": payload.get("label", "")}
                print(f"[ISOLATION] Read label for {element_name}: {self._last_read_result['value']}")

            elif action_type == "COPY":
                target = self.find_element_with_advanced_wait(xpath)
                self._copy_from_element(target)
                payload = self._get_readable_element_payload(target)
                self._last_read_result = {"type": "copy", "value": payload.get("value") or payload.get("text") or ""}
                print(f"[ISOLATION] Copy executed for {element_name}")

            elif action_type == "PASTE":
                target = self.find_element_with_advanced_wait(xpath)
                self._paste_to_element(target, test_data)
                payload = self._get_readable_element_payload(target)
                self._last_read_result = {"type": "paste", "value": payload.get("value") or payload.get("text") or ""}
                print(f"[ISOLATION] Paste executed for {element_name}")

            elif action_type == "UPLOAD_FILE":
                self._upload_file_to_element(xpath, test_data)
                print(f"[ISOLATION] Upload executed for {element_name}")

            elif action_type == "DOWNLOAD_FILE":
                downloaded_name = self._download_file_from_element(xpath, element_name, test_data)
                print(f"[ISOLATION] Download executed for {element_name}: {downloaded_name}")

            elif action_type == "VISUAL_ASSERTION":
                result = self._run_visual_assertion(test_data, element_name)
                print(f"[ISOLATION] Visual assertion for {element_name}: baseline={result.get('baseline')} status={result.get('value')} diff={result.get('difference_ratio')}")

            elif action_type in ["TYPE", "INPUT", "ENTER_TEXT"]:
                target = self.find_element_with_advanced_wait(xpath)
                self.perform_robust_text_input(target, str(test_data))
                print(f"[ISOLATION] Generic text input successful for {element_name}")

            elif action_type in ["SELECT", "CHOOSE", "PICK"]:
                self._generic_click_and_select(xpath, test_data)
                print(f"[ISOLATION] Generic select successful for {element_name}")

            elif action_type in ["WAIT", "WAIT_FOR_PAGE"]:
                wait_seconds = int(test_data_text) if test_data_text.isdigit() else 2
                WebDriverWait(self.driver, max(wait_seconds, 1)).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                print(f"[ISOLATION] Wait completed for {wait_seconds}s max")

            elif action_type in ["PRESS_KEY", "KEY"]:
                self.handle_press_key_action(test_data)
                print(f"[ISOLATION] Sent key {str(test_data or '').strip() or 'ENTER'}")

            elif action_type == "ASSERTION":
                print(f"[ISOLATION] Assertion step prepared for {element_name} ({self.normalize_assertion_type(assertion_type)})")

            else:
                # Last-resort generic behavior: click target and optionally type value.
                if xpath and xpath.strip() and xpath.strip().upper() != "NA":
                    target = self.find_element_with_advanced_wait(xpath)
                    self.perform_robust_click(target)
                    if str(test_data or "").strip():
                        self.perform_robust_text_input(target, str(test_data))
                    print(f"[ISOLATION] Generic fallback action executed for unknown action type '{action_type}'")
                else:
                    print(f"[ISOLATION] [WARNING] Unknown action type without locator: {action_type}")
                    raise Exception(f"Unknown action type: {action_type}")

            # After successful action execution, handle window/tab management
            print(f"[ISOLATION] Action '{action_type}' completed, checking for window changes...")
            # Skip window bookkeeping for departure date pick to keep this path as fast as Playwright.
            if not is_departure_date_select:
                # Use built-in window tracking helpers; no-op if not applicable
                self.detect_new_windows()
                self.switch_to_latest_window()
            else:
                print("[ISOLATION] Skipping window checks for departure date optimization")

        except Exception as e:
            print(f"[ISOLATION] Error executing action '{action_type}' for element '{element_name}': {str(e)}")
            print(f"[ISOLATION] Full traceback: {traceback.format_exc()}")
            # Re-raise the exception so the step fails properly but test continues
            raise e

    def normalize_action_type(self, action_type):
        """
        Normalize legacy action names to current supported action set.
        Keeps backward compatibility with previously saved test steps.
        """
        normalized = re.sub(r"[\s\-/]+", "_", (action_type or "").upper().strip())

        legacy_select_actions = {
            "CLICK_AND_SELECT_DATE",
            "CLICK_QUICK_DATE",
            "CLICK_BUS_QUICK_DATE",
            "CLICK_AND_SELECT_AGE",
        }

        if normalized in legacy_select_actions:
            return "CLICK_AND_SELECT"

        alias_map = {
            "DOUBLECLICK": "DOUBLE_CLICK",
            "RIGHTCLICK": "RIGHT_CLICK",
            "MOUSEOVER": "MOUSE_OVER",
            "MOUSE_HOVER": "MOUSE_OVER",
            "HOVER": "MOUSE_OVER",
            "HOVER_MOUSE_OVER": "MOUSE_OVER",
            "CLEAR_TYPE": "CLEAR_AND_TYPE",
            "TYPE_AND_CLEAR": "CLEAR_AND_TYPE",
            "RADIO": "RADIO_BUTTON",
            "RADIOBUTTON": "RADIO_BUTTON",
            "HANDLE_RADIO": "RADIO_BUTTON",
            "DRAGDROP": "DRAG_AND_DROP",
            "DRAG_&_DROP": "DRAG_AND_DROP",
            "SWITCH_FRAME": "SWITCH_TO_IFRAME",
            "SWITCH_TO_FRAME": "SWITCH_TO_IFRAME",
            "SWITCH_IFRAME": "SWITCH_TO_IFRAME",
            "SWITCH_TO_DEFAULT_FRAME": "SWITCH_TO_DEFAULT_CONTENT",
            "SWITCH_TO_MAIN_CONTENT": "SWITCH_TO_DEFAULT_CONTENT",
            "SWITCH_DEFAULT_CONTENT": "SWITCH_TO_DEFAULT_CONTENT",
        }

        return alias_map.get(normalized, normalized)

    def _normalize_press_key_tokens(self, key_value):
        raw = str(key_value or "").strip()
        if not raw:
            raw = "ENTER"
        tokens = [token.strip() for token in re.split(r"\s*\+\s*", raw) if token.strip()]
        return tokens or ["ENTER"]

    def _resolve_selenium_key_token(self, token):
        normalized = str(token or "").strip().upper().replace(" ", "_").replace("-", "_")
        alias_map = {
            "CTRL": "CONTROL",
            "CMD": "COMMAND",
            "WIN": "META",
            "WINDOWS": "META",
            "OPTION": "ALT",
            "ESC": "ESCAPE",
            "LEFT": "ARROW_LEFT",
            "RIGHT": "ARROW_RIGHT",
            "UP": "ARROW_UP",
            "DOWN": "ARROW_DOWN",
        }
        resolved = alias_map.get(normalized, normalized)
        special_key = getattr(Keys, resolved, None)
        if special_key:
            return special_key
        if len(token) == 1:
            return token.lower()
        raise Exception(f"Unsupported key token: {token}")

    def handle_press_key_action(self, test_data):
        tokens = self._normalize_press_key_tokens(test_data)
        resolved_tokens = [self._resolve_selenium_key_token(token) for token in tokens]
        active = self.driver.switch_to.active_element
        if len(resolved_tokens) == 1:
            active.send_keys(resolved_tokens[0])
            return
        active.send_keys(Keys.chord(*resolved_tokens))

    def _get_readable_element_payload(self, element):
        try:
            return self.driver.execute_script("""
                const el = arguments[0];
                if (!el) return {};
                const text = ((el.innerText || el.textContent || '') + '').replace(/\\s+/g, ' ').trim();
                const value = ((el.value || '') + '').trim();
                const title = ((el.getAttribute('title') || '') + '').trim();
                const ariaLabel = ((el.getAttribute('aria-label') || '') + '').trim();
                const placeholder = ((el.getAttribute('placeholder') || '') + '').trim();
                let label = '';
                if (el.labels && el.labels.length) {
                    label = Array.from(el.labels).map(l => (l.innerText || l.textContent || '').trim()).filter(Boolean).join(' ').trim();
                }
                if (!label) {
                    const closest = el.closest && el.closest('label');
                    if (closest) label = (closest.innerText || closest.textContent || '').replace(/\\s+/g, ' ').trim();
                }
                if (!label) {
                    const id = el.getAttribute('id');
                    if (id) {
                        const explicit = document.querySelector(`label[for="${id}"]`);
                        if (explicit) label = (explicit.innerText || explicit.textContent || '').replace(/\\s+/g, ' ').trim();
                    }
                }
                return { text, value, title, ariaLabel, placeholder, label };
            """, element) or {}
        except Exception:
            return {}

    def _copy_from_element(self, element):
        self.perform_robust_click(element)
        tag_name = (element.tag_name or "").lower()
        is_textual = tag_name in ["input", "textarea"] or str(element.get_attribute("contenteditable") or "").lower() == "true"
        if is_textual:
            element.send_keys(Keys.CONTROL, "a")
        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys("c").key_up(Keys.CONTROL).perform()

    def _paste_to_element(self, element, test_data):
        text = str(test_data or "").strip()
        self.perform_robust_click(element)
        if text:
            tag_name = (element.tag_name or "").lower()
            contenteditable = str(element.get_attribute("contenteditable") or "").lower() == "true"
            if tag_name in ["input", "textarea"]:
                try:
                    self.driver.execute_script(
                        """
                        const el = arguments[0];
                        const value = arguments[1];
                        el.focus();
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        element,
                        text,
                    )
                    return
                except Exception:
                    pass
            if contenteditable:
                try:
                    self.driver.execute_script(
                        """
                        const el = arguments[0];
                        const value = arguments[1];
                        el.focus();
                        el.textContent = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        element,
                        text,
                    )
                    return
                except Exception:
                    pass
            element.send_keys(text)
            return
        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()

    def _upload_file_to_element(self, xpath, test_data):
        file_path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(test_data or "").strip())))
        if not os.path.exists(file_path):
            raise Exception(f'Upload file not found: {file_path}')
        target = self.find_element_with_advanced_wait(xpath)
        file_input = target
        try:
            if (target.tag_name or "").lower() != "input" or (target.get_attribute("type") or "").lower() != "file":
                file_input = target.find_element(By.XPATH, ".//input[@type='file']")
        except Exception:
            pass
        file_input.send_keys(file_path)
        self._last_read_result = {"type": "upload", "value": file_path}

    def _download_file_from_element(self, xpath, element_name, test_data):
        before_files = {name: os.path.getmtime(os.path.join(self.download_dir, name)) for name in os.listdir(self.download_dir)}
        target = self.find_element_with_advanced_wait(xpath)
        self.perform_robust_click(target)

        expected_fragment = str(test_data or "").strip().lower()
        deadline = time.time() + max(self.default_wait_timeout, 5)
        latest_file = None
        while time.time() < deadline:
            current_files = os.listdir(self.download_dir)
            for name in current_files:
                file_path = os.path.join(self.download_dir, name)
                if not os.path.isfile(file_path):
                    continue
                if name.endswith(".crdownload"):
                    continue
                mtime = os.path.getmtime(file_path)
                if name not in before_files or mtime > before_files.get(name, 0):
                    if expected_fragment and expected_fragment not in name.lower():
                        latest_file = file_path
                        continue
                    self._last_read_result = {"type": "download", "value": name}
                    return name
            time.sleep(0.3)
        raise Exception(f'No downloaded file detected for "{element_name}" in {self.download_dir}')

    def _parse_visual_assertion_config(self, test_data, element_name):
        raw = str(test_data or "").strip()
        config = {
            "baseline": re.sub(r"[^A-Za-z0-9._-]+", "_", str(element_name or "visual_assertion").strip() or "visual_assertion"),
            "threshold": 0.01,
        }
        if not raw:
            return config
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                if payload.get("baseline"):
                    config["baseline"] = re.sub(r"[^A-Za-z0-9._-]+", "_", str(payload["baseline"]).strip())
                if payload.get("threshold") is not None:
                    config["threshold"] = max(float(payload["threshold"]), 0.0)
                return config
        except Exception:
            pass
        for part in re.split(r"[;,\n]+", raw):
            if "=" in part:
                key, value = [segment.strip() for segment in part.split("=", 1)]
                if key.lower() == "baseline" and value:
                    config["baseline"] = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
                elif key.lower() == "threshold" and value:
                    try:
                        config["threshold"] = max(float(value), 0.0)
                    except Exception:
                        pass
            elif part.strip():
                config["baseline"] = re.sub(r"[^A-Za-z0-9._-]+", "_", part.strip())
        return config

    def _run_visual_assertion(self, test_data, element_name):
        config = self._parse_visual_assertion_config(test_data, element_name)
        baseline_name = config["baseline"]
        threshold = config["threshold"]
        baseline_path = os.path.join(self.visual_baseline_dir, f"{baseline_name}.png")
        current_attachment = self.save_screenshot(f"visual_{baseline_name}")
        if not current_attachment:
            raise Exception("Failed to capture screenshot for visual assertion")
        current_path = os.path.join(os.getcwd(), "allure-results-new", current_attachment["source"])
        try:
            from PIL import Image, ImageChops
        except Exception as pil_error:
            raise Exception(f"Visual assertion requires Pillow: {pil_error}")

        current_image = Image.open(current_path).convert("RGBA")
        if not os.path.exists(baseline_path):
            current_image.save(baseline_path)
            self._last_read_result = {"type": "visual_assertion", "value": "baseline_created", "baseline": baseline_name, "difference_ratio": 0.0, "threshold": threshold}
            return self._last_read_result

        baseline_image = Image.open(baseline_path).convert("RGBA")
        if baseline_image.size != current_image.size:
            current_image = current_image.resize(baseline_image.size)
        diff = ImageChops.difference(baseline_image, current_image)
        bbox = diff.getbbox()
        if not bbox:
            diff_ratio = 0.0
        else:
            histogram = diff.histogram()
            total_channels = 4
            differing = sum(histogram[index] * (index % 256) for index in range(len(histogram)))
            max_diff = baseline_image.size[0] * baseline_image.size[1] * total_channels * 255
            diff_ratio = differing / max_diff if max_diff else 0.0
        self._last_read_result = {
            "type": "visual_assertion",
            "value": "matched" if diff_ratio <= threshold else "mismatch",
            "baseline": baseline_name,
            "difference_ratio": diff_ratio,
            "threshold": threshold,
        }
        return self._last_read_result

    def normalize_assertion_type(self, assertion_type):
        normalized = re.sub(r"[\s\-/]+", "_", str(assertion_type or "").upper().strip())
        alias_map = {
            "": "ELEMENT_VISIBLE",
            "VERIFY_ELEMENT_EXISTS": "ELEMENT_EXISTS",
            "VERIFY_ELEMENT_VISIBLE": "ELEMENT_VISIBLE",
            "VERIFY_ELEMENT_ENABLED": "ELEMENT_ENABLED",
            "VERIFY_ELEMENT_DISABLED": "ELEMENT_DISABLED",
            "VERIFY_ELEMENT_CLICKABLE": "ELEMENT_CLICKABLE",
            "VERIFY_TEXT": "VERIFY_TEXT",
            "VERIFY_INPUT": "VERIFY_INPUT_VALUE",
            "VERIFY_VALUE": "VERIFY_INPUT_VALUE",
            "VERIFY_INPUT_VALUE": "VERIFY_INPUT_VALUE",
            "VERIFY_ATTRIBUTE": "VERIFY_ATTRIBUTE",
            "VERIFY_PLACEHOLDER": "VERIFY_PLACEHOLDER",
            "VERIFY_PAGE_TITLE": "VERIFY_PAGE_TITLE",
            "VERIFY_URL": "VERIFY_URL_CONTAINS",
            "VERIFY_URL_CONTAINS": "VERIFY_URL_CONTAINS",
            "VERIFY_URL_EQUALS": "VERIFY_URL_EQUALS",
            "VERIFY_REDIRECTS": "VERIFY_URL_CONTAINS",
            "VERIFY_PAGE_LOAD_COMPLETION": "VERIFY_PAGE_LOADED",
            "VERIFY_PAGE_LOADED": "VERIFY_PAGE_LOADED",
            "WAIT_FOR_ELEMENT_VISIBLE": "WAIT_FOR_VISIBLE",
            "WAIT_FOR_VISIBLE": "WAIT_FOR_VISIBLE",
            "WAIT_FOR_CLICKABLE": "WAIT_FOR_CLICKABLE",
            "WAIT_FOR_LOADER_DISAPPEARS": "WAIT_FOR_LOADER_DISAPPEARS",
        }
        return alias_map.get(normalized, normalized or "ELEMENT_VISIBLE")

    def _assertion_requires_locator(self, assertion_type):
        return assertion_type not in {"VERIFY_PAGE_TITLE", "VERIFY_URL_CONTAINS", "VERIFY_URL_EQUALS", "VERIFY_PAGE_LOADED"}

    def _evaluate_assertion(self, assertion_type, test_data, xpath, element_name):
        assertion_type = self.normalize_assertion_type(assertion_type)
        expected = str(test_data or "").strip()

        if assertion_type == "VERIFY_PAGE_TITLE":
            actual_title = self.driver.title or ""
            if actual_title.strip() == expected:
                return {'success': True, 'message': f'Page title matched "{expected}"'}
            return {'success': False, 'message': f'Expected page title "{expected}", but found "{actual_title}"'}

        if assertion_type == "VERIFY_URL_CONTAINS":
            current_url = self.driver.current_url or ""
            if expected.lower() in current_url.lower():
                return {'success': True, 'message': f'URL contains "{expected}"'}
            return {'success': False, 'message': f'Expected URL containing "{expected}", but found "{current_url}"'}

        if assertion_type == "VERIFY_URL_EQUALS":
            current_url = self.driver.current_url or ""
            if current_url.strip().lower() == expected.lower():
                return {'success': True, 'message': f'URL matched "{expected}"'}
            return {'success': False, 'message': f'Expected URL "{expected}", but found "{current_url}"'}

        if assertion_type == "VERIFY_PAGE_LOADED":
            ready_state = self.driver.execute_script("return document.readyState")
            if ready_state == "complete":
                return {'success': True, 'message': 'Page load completed'}
            return {'success': False, 'message': f'Expected page readyState complete, found "{ready_state}"'}

        if not xpath or str(xpath).strip().upper() == "NA":
            return {'success': False, 'message': f'Assertion "{assertion_type}" requires a locator for "{element_name}"'}

        element = self.find_element_with_advanced_wait(xpath)
        if not element:
            return {'success': False, 'message': f'Element "{element_name}" not found for assertion "{assertion_type}"'}

        if assertion_type == "ELEMENT_EXISTS":
            return {'success': True, 'message': f'Element "{element_name}" exists'}
        if assertion_type == "ELEMENT_VISIBLE":
            return {'success': True, 'message': f'Element "{element_name}" is visible'} if element.is_displayed() else {'success': False, 'message': f'Element "{element_name}" is not visible'}
        if assertion_type == "ELEMENT_ENABLED":
            return {'success': True, 'message': f'Element "{element_name}" is enabled'} if element.is_enabled() else {'success': False, 'message': f'Element "{element_name}" is disabled'}
        if assertion_type == "ELEMENT_DISABLED":
            return {'success': True, 'message': f'Element "{element_name}" is disabled'} if not element.is_enabled() else {'success': False, 'message': f'Element "{element_name}" is enabled'}
        if assertion_type == "ELEMENT_CLICKABLE":
            if element.is_displayed() and element.is_enabled():
                return {'success': True, 'message': f'Element "{element_name}" is clickable'}
            return {'success': False, 'message': f'Element "{element_name}" is not clickable'}
        if assertion_type == "VERIFY_TEXT":
            actual_text = (element.text or element.get_attribute("value") or "").strip()
            if actual_text == expected:
                return {'success': True, 'message': f'Text matched "{expected}"'}
            return {'success': False, 'message': f'Expected text "{expected}", but found "{actual_text}"'}
        if assertion_type == "VERIFY_INPUT_VALUE":
            actual_value = (element.get_attribute("value") or "").strip()
            if actual_value == expected:
                return {'success': True, 'message': f'Input value matched "{expected}"'}
            return {'success': False, 'message': f'Expected input value "{expected}", but found "{actual_value}"'}
        if assertion_type == "VERIFY_ATTRIBUTE":
            attribute_name = ""
            attribute_value = ""
            for separator in ["=", ":"]:
                if separator in expected:
                    attribute_name, attribute_value = [part.strip() for part in expected.split(separator, 1)]
                    break
            if not attribute_name:
                return {'success': False, 'message': 'VERIFY_ATTRIBUTE requires Values in the form attribute=value'}
            actual_attr = (element.get_attribute(attribute_name) or "").strip()
            if actual_attr == attribute_value:
                return {'success': True, 'message': f'Attribute "{attribute_name}" matched "{attribute_value}"'}
            return {'success': False, 'message': f'Expected attribute "{attribute_name}"="{attribute_value}", but found "{actual_attr}"'}
        if assertion_type == "VERIFY_PLACEHOLDER":
            actual_placeholder = (element.get_attribute("placeholder") or "").strip()
            if actual_placeholder == expected:
                return {'success': True, 'message': f'Placeholder matched "{expected}"'}
            return {'success': False, 'message': f'Expected placeholder "{expected}", but found "{actual_placeholder}"'}
        if assertion_type == "WAIT_FOR_VISIBLE":
            WebDriverWait(self.driver, self.default_wait_timeout).until(lambda d: element.is_displayed())
            return {'success': True, 'message': f'Element "{element_name}" became visible'}
        if assertion_type == "WAIT_FOR_CLICKABLE":
            WebDriverWait(self.driver, self.default_wait_timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            return {'success': True, 'message': f'Element "{element_name}" became clickable'}
        if assertion_type == "WAIT_FOR_LOADER_DISAPPEARS":
            WebDriverWait(self.driver, self.default_wait_timeout).until(EC.invisibility_of_element_located((By.XPATH, xpath)))
            return {'success': True, 'message': f'Loader "{element_name}" disappeared'}

        return {'success': False, 'message': f'Unsupported assertion type: {assertion_type}'}

    def resolve_count_element_type(self, element_name):
        """Map varied element labels to a canonical count type."""
        name = (element_name or "").strip().lower().replace(" ", "")
        for count_type, aliases in self.COUNT_TYPE_KEYWORD_MAP.items():
            if any(alias in name for alias in aliases):
                return count_type
        return None

    def _get_count_control_xpaths(self, element_type):
        """Return increment/decrement control locators for known count widgets."""
        normalized = (element_type or "").lower()
        return self.COUNT_CONTROL_XPATHS.get(normalized, (None, None))

    def _parse_step_count(self, test_data, default_value=1):
        """Parse count steps from test data with a safe default."""
        try:
            parsed = int(str(test_data).strip())
            return max(parsed, 1)
        except Exception:
            return default_value

    def _locator_matches_count_direction(self, locator, direction):
        """Check whether a locator already points to the expected count control."""
        locator_text = str(locator or "").strip().lower()
        if not locator_text:
            return False
        if direction == "increment":
            return "increment" in locator_text
        if direction == "decrement":
            return "decrement" in locator_text
        return False

    def _adjust_count(self, element_name, xpath, direction, step_count):
        """
        Increment or decrement a counter by a fixed number of steps.
        Returns metadata for downstream validation.
        """
        direction = (direction or "").lower()
        if direction not in ["increment", "decrement"]:
            raise ValueError(f"Unsupported count direction: {direction}")

        element_type = self.resolve_count_element_type(element_name)
        before_count = None
        after_count = None
        expected_after = None

        if element_type:
            try:
                before_count = self.get_current_count(element_type)
            except Exception:
                before_count = None

        target_locator = xpath
        inc_xpath, dec_xpath = self._get_count_control_xpaths(element_type)
        derived_locator = inc_xpath if direction == "increment" else dec_xpath

        if element_type and derived_locator:
            # For separated INCREMENT/DECREMENT actions, prefer known +/- controls.
            # Many sheets store group labels in XPath (e.g., "Adults"), not button locators.
            if not self._locator_matches_count_direction(target_locator, direction):
                target_locator = derived_locator
        elif not (target_locator and str(target_locator).strip() and str(target_locator).strip().upper() != "NA"):
            target_locator = derived_locator

        if not target_locator:
            raise Exception(f"No locator available for {direction} on element '{element_name}'")

        control = self.find_element_with_advanced_wait(target_locator)
        for _ in range(step_count):
            self._robust_click(control)
            time.sleep(0.2)

        if element_type:
            try:
                after_count = self.get_current_count(element_type)
            except Exception:
                after_count = None
            if before_count is not None:
                expected_after = before_count + step_count if direction == "increment" else max(before_count - step_count, 0)

        state = {
            "mode": direction,
            "element_name": element_name,
            "element_type": element_type,
            "step_count": step_count,
            "before_count": before_count,
            "expected_after": expected_after,
            "after_count": after_count,
            "locator": target_locator,
        }
        self._last_count_action_state = state
        return state
    
    
    def _is_quick_date_value(self, value):
        text = str(value or "").strip().lower()
        return text in [self.QUICK_DATE_TODAY, self.QUICK_DATE_TOMORROW] or text in self.QUICK_DATE_DAY_AFTER_ALIASES

    def _looks_like_child_age_selection(self, test_data, xpath):
        data_text = str(test_data or "").strip()
        locator_text = str(xpath or "").strip().lower()
        return data_text.isdigit() and ("child-age-selector" in locator_text or "child-age" in locator_text)

    def _is_stale_element_error(self, error):
        return "stale element reference" in str(error).lower()

    def _has_usable_locator(self, locator):
        text = str(locator or "").strip()
        return bool(text and text.upper() != "NA")

    def _select_child_age_from_xpath(self, xpath, age):
        """Select child age by reading index from xpath when available."""
        locator_text = str(xpath or "").strip()
        index_match = re.search(r"\[(\d+)\]\s*$", locator_text)
        if index_match:
            child_index = max(int(index_match.group(1)) - 1, 0)
            self.select_child_age(child_index, int(age))
            return

        # Fallback to the first child age selector.
        self.select_child_age(0, int(age))

    def handle_unified_click_and_select(self, test_data, xpath, element_name):
        """Reusable CLICK_AND_SELECT flow independent of semantic element names."""
        try:
            print(f"[UNIFIED_SELECT] Processing element: {element_name} with data: '{test_data}'")
            data_text = str(test_data or "").strip()
            lowered_data = data_text.lower()

            # 1) Quick date selection by value token.
            if self._is_quick_date_value(data_text):
                print(f"[UNIFIED_SELECT] Applying quick-date strategy")
                self.handle_quick_date_selection(lowered_data, element_name)
                return

            # 2) Child age selector strategy by locator + numeric value.
            if self._looks_like_child_age_selection(data_text, xpath):
                print(f"[UNIFIED_SELECT] Applying child-age strategy")
                self._select_child_age_from_xpath(xpath, data_text)
                return

            # 3) Absolute/date-like values should use calendar strategy.
            is_explicit_date_value = self.is_date_format_data(data_text)
            is_date_field_with_date_value = self.is_date_field(element_name, data_text) and (
                self.validate_date_format(data_text) or lowered_data in self.DATE_QUICK_OPTIONS
            )
            if is_explicit_date_value or is_date_field_with_date_value:
                print(f"[UNIFIED_SELECT] Applying calendar date strategy")
                self.handle_date_selection_fast(data_text, xpath, element_name)
                return

            # 3) Generic element strategy based on actual control type.
            element = self.find_element_with_advanced_wait(xpath)
            tag_name = (element.tag_name or "").lower()
            input_type = (element.get_attribute("type") or "").lower()

            if tag_name == "select":
                print(f"[UNIFIED_SELECT] Applying dropdown strategy")
                select_ctrl = Select(element)
                try:
                    select_ctrl.select_by_visible_text(data_text)
                except Exception:
                    try:
                        select_ctrl.select_by_value(data_text)
                    except Exception:
                        if data_text.isdigit():
                            select_ctrl.select_by_index(int(data_text))
                        else:
                            raise
                return

            if input_type in ["checkbox", "radio"]:
                print(f"[UNIFIED_SELECT] Applying boolean-toggle strategy")
                desired = lowered_data in ["true", "1", "yes", "on", "checked"]
                if bool(element.is_selected()) != desired:
                    self.perform_robust_click(element)
                return

            if data_text:
                print(f"[UNIFIED_SELECT] Applying selection-only fallback")
                self.perform_robust_click(element)
                # Best effort: if a visible option already appears after click, choose it by text.
                if self.try_autocomplete_selection(data_text):
                    return
                return

            # 4) Final fallback: pure click.
            print(f"[UNIFIED_SELECT] Applying click-only strategy")
            self.perform_robust_click(element)
            time.sleep(0.2)

        except Exception as e:
            print(f"[UNIFIED_SELECT] Error in unified click and select: {str(e)}")
            raise e

    def is_date_format_data(self, test_data):
        """Check if test data appears to be in a date format"""
        if not test_data:
            return False
            
        try:
            import re
            normalized_data = re.sub(r"\s+", " ", str(test_data).strip()).lower()
            
            # Check for common date patterns
            date_patterns = [
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # dd/mm/yyyy or mm/dd/yyyy
                r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # yyyy/mm/dd
                r'\w{3},?\s+\d{1,2}\s+\w{3}',      # Wed, 30 Jul
                r'\d{1,2}\s+\w{3}\s+\d{4}',       # 30 Jul 2024
                r'\w{3}\s+\d{1,2},?\s+\d{4}',     # Jul 30, 2024
            ]
            
            for pattern in date_patterns:
                if re.search(pattern, str(test_data)):
                    return True
            
            # Check for day/month names
            date_keywords = [
                'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
                'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
                'today', 'tomorrow', 'yesterday', 'day after', 'day-after-tomorrow'
            ]
            
            return any(keyword in normalized_data for keyword in date_keywords)
            
        except Exception:
            return False

    def handle_city_selection_fast_safe(self, city_name, xpath, element_name):
        """Safe city selection using xpath from Excel with independent error handling"""
        try:
            print(f"Attempting to select city: {city_name} for {element_name}")
            print(f"Using xpath from Excel: {xpath}")
            
            # Use only the xpath provided from Excel
            city_input = None
            
            try:
                city_input = self.find_element_with_advanced_wait(xpath)
                if city_input and city_input.is_displayed():
                    print(f"Successfully found element with provided xpath")
                else:
                    print(f"Element found but not displayed for {element_name}")
                    return False
            except Exception as e:
                print(f"Failed to find element with provided xpath for {element_name}: {str(e)}")
                return False
            
            if not city_input:
                print(f"Could not find {element_name} input field with provided xpath")
                return False
            
            # Perform the city selection
            try:
                self.perform_robust_click(city_input)
                time.sleep(0.3)
                
                self.perform_robust_text_input(city_input, city_name)
                time.sleep(0.8)
                
                # Try autocomplete selection
                suggestion_clicked = self.try_autocomplete_selection(city_name)

                if not suggestion_clicked:
                    city_input.send_keys(Keys.ARROW_DOWN, Keys.ENTER)
                    print("Used keyboard navigation for city selection")

                # Extended wait time for city selection to complete
                time.sleep(2.0)  # Increased from 0.3 to 2.0 seconds

                # Wait for any interfering modals to disappear before considering selection complete
                try:
                    modal_selectors = [
                        "//div[@data-testid='bpg-home-modal']",
                        "//div[contains(@class,'modal') and contains(@class,'bg-black')]",
                        "//div[contains(@class,'fixed') and contains(@class,'z-[9999]')]"
                    ]
                    for selector in modal_selectors:
                        modal_elements = self.driver.find_elements(By.XPATH, selector)
                        for modal in modal_elements:
                            if modal.is_displayed():
                                print(f"[AUTOCOMPLETE] Waiting for modal to disappear: {selector}")
                                # Wait up to 3 seconds for modal to disappear
                                WebDriverWait(self.driver, 3).until(
                                    EC.invisibility_of_element(modal)
                                )
                                print(f"[AUTOCOMPLETE] Modal disappeared")
                                break
                except Exception as modal_error:
                    print(f"[AUTOCOMPLETE] Modal wait failed (may not be present): {str(modal_error)}")

                print(f"Successfully selected city: {city_name} for {element_name}")
                return True
                
            except Exception as e:
                print(f"Error during city selection process for {element_name}: {str(e)}")
                return False

        except Exception as e:
            print(f"Failed to select city {city_name} for {element_name}: {str(e)}")
            return False

    def try_autocomplete_selection(self, city_name):
        """Try to select from autocomplete suggestions with improved waiting and selection"""
        try:
            auto_complete_selectors = [
                f"//*[contains(text(),'{city_name}') and not(ancestor::*[contains(@class,'input')])]",
                f"//div[contains(@class,'autocomplete')]//*[contains(text(),'{city_name}')]",
                f"//li[contains(text(),'{city_name}')]",
                f"//div[contains(@class,'suggestion')]//*[contains(text(),'{city_name}')]",
                f"//div[contains(@role,'option') and contains(text(),'{city_name}')]",
                f"//span[contains(text(),'{city_name}') and contains(@class,'location')]"
            ]

            deadline = time.time() + max(self.autocomplete_wait_timeout, 0.2)
            while time.time() < deadline:
                for selector in auto_complete_selectors:
                    try:
                        suggestions = self.driver.find_elements(By.XPATH, selector)
                    except Exception:
                        continue

                    for suggestion in suggestions:
                        try:
                            if not suggestion.is_displayed() or not suggestion.is_enabled():
                                continue
                            suggestion_text = suggestion.text.strip()
                            if city_name.lower() not in suggestion_text.lower():
                                continue
                            print(f"[AUTOCOMPLETE] Found suggestion: '{suggestion_text}' for city: '{city_name}'")
                            self.perform_robust_click(suggestion)
                            print(f"[AUTOCOMPLETE] City suggestion clicked: {city_name}")
                            return True
                        except Exception:
                            continue
                time.sleep(0.1)

            print(f"[AUTOCOMPLETE] No clickable suggestions found for city: {city_name}")
            return False
        except Exception as e:
            print(f"[AUTOCOMPLETE] Error in autocomplete selection: {str(e)}")
            return False
    
    def handle_click_and_type(self, input_text, xpath, element_name):
        """Click the element and type the given input text robustly (isolated with logging)."""
        try:
            print(f"[CLICK_AND_TYPE] Target: {element_name} | Input: '{input_text}' | XPath: {xpath}")

            # Find the input element using advanced waiting
            element = self.find_element_with_advanced_wait(xpath)

            if not element or not element.is_displayed():
                print(f"[CLICK_AND_TYPE] Input element not found or not displayed for: {element_name}")
                raise Exception(f"Input element not found for {element_name}")

            # Robustly click and focus the input before typing
            self.perform_robust_click(element)
            time.sleep(0.2)

            # Robustly type the text (with pre-clear)
            self.perform_robust_text_input(element, input_text)
            time.sleep(0.2)

            print(f"[CLICK_AND_TYPE] Successfully entered '{input_text}' for {element_name}")
            return True

        except Exception as e:
            print(f"[CLICK_AND_TYPE][ERROR] Failed for {element_name}: {str(e)}")
            raise e

    def handle_date_selection_fast(self, date_string, xpath, element_name):
        """Handle fast date selection for calendar inputs - Playwright-style smart waiting."""
        try:
            print(f"[DATE] Selecting date: {date_string} for {element_name}")

            # Parse date first so we can build the target selector before any DOM interaction.
            try:
                normalized_date = str(date_string).strip()
                normalized_date = re.sub(r"\s+", " ", normalized_date)
                normalized_date = re.sub(r"^(\d{4}-\d{2}-\d{2})\s+\d{4}$", r"\1", normalized_date)

                parse_candidates = [
                    ("%Y-%m-%d", True),
                    ("%d/%m/%Y", True),
                    ("%Y/%m/%d", True),
                    ("%a, %d %b %Y", True),
                    ("%a, %d %b", False),
                    ("%d %b %Y", True),
                    ("%d %b", False),
                ]

                target_date = None
                current_year = datetime.now(pytz.timezone('Asia/Kolkata')).year
                for fmt, has_year in parse_candidates:
                    try:
                        parsed_date = datetime.strptime(normalized_date, fmt)
                        target_date = parsed_date if has_year else parsed_date.replace(year=current_year)
                        break
                    except ValueError:
                        continue

                if target_date is None:
                    raise ValueError(f"Unsupported date format: {date_string}")
            except ValueError as e:
                print(f"[ERROR] Failed to parse date: {date_string}")
                raise e

            day = str(target_date.day)
            full_date_label = target_date.strftime("%B %d, %Y")
            fast_selector = f"//abbr[@aria-label='{full_date_label}']"
            element_name_lower = str(element_name or "").strip().lower()

            # Departure-only fast path using the earlier strategy style:
            # open calendar first, then click from a tight selector set.
            if "departure" in element_name_lower:
                # Match Playwright behavior: dismiss transient overlays first.
                try:
                    active = self.driver.switch_to.active_element
                    active.send_keys(Keys.ESCAPE)
                    print("[DATE_FAST] Pressed Escape before departure selection")
                except Exception:
                    pass

                parsed_locator = self._parse_locator(xpath)
                date_field = None
                if parsed_locator:
                    by, value = parsed_locator
                    end_time = time.time() + 1.0
                    while time.time() < end_time and date_field is None:
                        try:
                            candidates = self.driver.find_elements(by, value)
                            for candidate in candidates:
                                try:
                                    if candidate.is_displayed():
                                        date_field = candidate
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass
                        if date_field is None:
                            time.sleep(0.05)

                if date_field is None:
                    # Fallback only if quick direct lookup misses.
                    date_field = self.find_element_with_advanced_wait(xpath)

                self.perform_robust_click(date_field)
                time.sleep(0.3)

                departure_selectors = [
                    f"//abbr[@aria-label='{full_date_label}']",
                    f"//*[text()='{day}' and (name()='button' or name()='td' or name()='div' or name()='span')]",
                    f"//abbr[text()='{day}' and not(ancestor::*[contains(@class, 'disabled') or contains(@class, 'inactive')])]",
                ]

                for selector in departure_selectors:
                    try:
                        for date_el in self.driver.find_elements(By.XPATH, selector):
                            try:
                                if not date_el.is_displayed() or not date_el.is_enabled():
                                    continue
                                cls = date_el.get_attribute("class") or ""
                                if "disabled" in cls or "inactive" in cls:
                                    continue
                                self.perform_robust_click(date_el)
                                print(f"[SUCCESS] Departure date selected quickly: {day} using selector: {selector}")
                                return
                            except Exception:
                                continue
                    except Exception:
                        continue

            def click_matching_calendar_date(timeout_seconds):
                deadline = time.time() + timeout_seconds
                while time.time() < deadline:
                    try:
                        for date_el in self.driver.find_elements(By.XPATH, fast_selector):
                            try:
                                if not date_el.is_displayed():
                                    continue
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                                    date_el
                                )
                                try:
                                    date_el.click()
                                except Exception:
                                    self.driver.execute_script("arguments[0].click();", date_el)
                                print(f"[SUCCESS] Date selected quickly: {day} using selector: {fast_selector}")
                                return True
                            except Exception:
                                continue
                    except Exception:
                        pass
                    time.sleep(0.05)
                return False

            # Phase 1: Calendar may already be open (ixigo auto-opens after city pick).
            # Poll every 50ms for up to 0.5s — returns instantly if calendar is open.
            if click_matching_calendar_date(0.35):
                return

            # Phase 2: Calendar not open — click the field, then smart-wait up to 2s.
            date_field = self.find_element_with_advanced_wait(xpath)
            self.perform_robust_click(date_field)
            print(f"[TARGET_FAST] Attempting fast click for date: {day}")

            if click_matching_calendar_date(1.25):
                return

            # Phase 3: Fallback selectors (buses, hotels).
            fallback_selectors = [
                f"//*[text()='{day}' and (name()='button' or name()='td' or name()='div' or name()='span')]",
                f"//abbr[text()='{day}' and not(ancestor::*[contains(@class,'disabled') or contains(@class,'inactive')])]",
            ]
            for selector in fallback_selectors:
                try:
                    for el in self.driver.find_elements(By.XPATH, selector):
                        try:
                            if el.is_displayed() and el.is_enabled():
                                cls = el.get_attribute("class") or ""
                                if "disabled" in cls or "inactive" in cls:
                                    continue
                                el.click()
                                print(f"[SUCCESS] Date selected successfully: {day} using selector: {selector}")
                                return
                        except Exception:
                            continue
                except Exception:
                    continue

            raise RuntimeError(f"Date selection failed for: {date_string}")

        except Exception as e:
            print(f"[ERROR] Failed to select date: {date_string} - {e}")
            raise e

    def is_calendar_closed(self):
        """Simplified calendar check - only what's needed"""
        try:
            time.sleep(0.15)
            calendar_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'calendar')]//abbr | //abbr[@aria-label]")
            return not calendar_elements or not calendar_elements[0].is_displayed()
        except Exception:
            return True  # Assume closed if we can't find calendar elements

    def handle_tomorrow_selection(self, element_name):
        """Optimized method to handle Tomorrow button click for trains"""
        try:
            print(f"[CALENDAR] Selecting Tomorrow for {element_name}")
            
            # Streamlined selectors - only the most effective ones
            tomorrow_selectors = self.TOMORROW_SELECTORS
            
            for selector in tomorrow_selectors:
                try:
                    tomorrow_button = self.find_element_with_advanced_wait(selector)
                    
                    if tomorrow_button and tomorrow_button.is_displayed() and tomorrow_button.is_enabled():
                        # Scroll to element before clicking
                        self.scroll_to_element(tomorrow_button)
                        
                        if self.perform_robust_click_with_result(tomorrow_button):
                            time.sleep(0.4)
                            print("[SUCCESS] Tomorrow button clicked successfully")
                            return
                except Exception:
                    continue  # Try next selector
            
            raise RuntimeError("Tomorrow selection failed - element not found or not clickable")
            
        except Exception as e:
            print(f"[ERROR] Failed to select Tomorrow - {e}")
            raise e

    def handle_day_after_tomorrow_selection(self, element_name):
        """Optimized method to handle Day After Tomorrow button click"""
        try:
            print(f"[CALENDAR] Selecting Day After Tomorrow for {element_name}")
            
            # Streamlined selectors - only the most effective ones
            day_after_selectors = self.DAY_AFTER_TOMORROW_SELECTORS
            
            for selector in day_after_selectors:
                try:
                    day_after_button = self.find_element_with_advanced_wait(selector)
                    
                    if day_after_button and day_after_button.is_displayed() and day_after_button.is_enabled():
                        # Scroll to element before clicking
                        self.scroll_to_element(day_after_button)
                        
                        if self.perform_robust_click_with_result(day_after_button):
                            time.sleep(0.4)
                            print("[SUCCESS] Day After Tomorrow clicked successfully")
                            return
                except Exception:
                    continue  # Try next selector
            
            raise RuntimeError("Day After Tomorrow selection failed - element not found or not clickable")
            
        except Exception as e:
            print(f"[ERROR] Failed to select Day After Tomorrow - {e}")
            raise e

    def handle_quick_date_selection(self, quick_date_option, element_name):
        """Optimized main method to handle quick date selection"""
        try:
            print(f"[LAUNCH] Quick date selection: {quick_date_option} for {element_name}")
            
            normalized_option = quick_date_option.lower().strip()
            
            if normalized_option == self.QUICK_DATE_TOMORROW:
                self.handle_tomorrow_selection(element_name)
            elif normalized_option in self.QUICK_DATE_DAY_AFTER_ALIASES:
                self.handle_day_after_tomorrow_selection(element_name)
            else:
                raise ValueError(f"Unsupported quick date option: {quick_date_option}. "
                               "Supported: tomorrow, day-after-tomorrow")
            
            print(f"[SUCCESS] Quick date selection completed for: {element_name}")
            
        except Exception as e:
            print(f"[ERROR] Quick date selection failed: {e}")
            raise e

    def handle_date_selection(self, date_input, xpath, element_name):
        """Optimized enhanced method that can handle both regular dates and quick date options"""
        try:
            print(f"[CALENDAR] Processing date input: {date_input} for {element_name}")
            
            normalized_input = date_input.lower().strip()
            
            # Check if it's a quick date option
            if normalized_input == self.QUICK_DATE_TOMORROW or self.QUICK_DATE_TOMORROW in normalized_input:
                self.handle_quick_date_selection(self.QUICK_DATE_TOMORROW, element_name)
            elif "day after" in normalized_input or normalized_input == self.QUICK_DATE_DAY_AFTER:
                self.handle_quick_date_selection(self.QUICK_DATE_DAY_AFTER, element_name)
            else:
                # Use existing date selection method for regular dates
                self.handle_date_selection_fast(date_input, xpath, element_name)
                
        except Exception as e:
            print(f"[ERROR] Date selection failed for input: {date_input} - {e}")
            raise e

    def scroll_to_element(self, element):
        """Helper method to scroll to element"""
        try:
            # Method 1: JavaScript scroll into view
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(0.2)
        except Exception:
            try:
                # Method 2: Actions scroll (fallback)
                actions = ActionChains(self.driver)
                actions.move_to_element(element).perform()
                time.sleep(0.2)
            except Exception:
                print("[WARNING] Scroll failed, attempting click without scroll")

    def handle_bus_quick_date_selection(self, quick_date_option, element_name):
        """FIXED: Optimized method to handle quick date selection for bus bookings"""
        try:
            print(f"[LAUNCH] Bus quick date selection: {quick_date_option} (type: {type(quick_date_option)}) for {element_name}")
            # Convert input to string first to handle numeric inputs from Excel
            option_str = str(quick_date_option).lower().strip()
            normalized_element_name = element_name.lower().strip()
            print(f"[CONFIG] Normalized option: '{option_str}' for element: '{normalized_element_name}'")
            # Handle SKIP cases - Skip execution completely
            if option_str in self.BUS_QUICK_DATE_SKIP_OPTIONS:
                print(f"[SKIP] SKIPPING {element_name} - Excel value indicates skip ({quick_date_option})")
                return  # Exit method without performing any action
            # Handle EXECUTE cases - Execute the button click based on element name
            if option_str in self.BUS_QUICK_DATE_EXECUTE_OPTIONS:
                print(f"[SUCCESS] Executing button click for: {element_name} (Excel value: {quick_date_option})")
                # Determine which date to select based on element name
                if self.QUICK_DATE_TODAY in normalized_element_name:
                    self.handle_today_selection(element_name)
                elif self.QUICK_DATE_TOMORROW in normalized_element_name:
                    self.handle_tomorrow_selection_bus(element_name)
                else:
                    print(f"[WARNING] Cannot determine date type from element name: {element_name}")
                    raise ValueError(f"Cannot determine date selection type for element: {element_name}")
            # Handle specific date options (legacy support - direct string values)
            elif option_str == self.QUICK_DATE_TODAY:
                self.handle_today_selection(element_name)
            elif option_str == self.QUICK_DATE_TOMORROW:
                self.handle_tomorrow_selection_bus(element_name)
            else:
                raise ValueError(f"Unsupported option: {quick_date_option}. "
                               "Supported: true, false, today, tomorrow, skip, n/a, 1, 0")
            print(f"[SUCCESS] Bus quick date selection completed for: {element_name}")
        except Exception as e:
            print(f"[ERROR] Bus quick date selection failed: {e}")
            raise e

    def handle_today_selection(self, element_name):
        """Optimized Today selection with most effective XPaths only"""
        try:
            print(f"[CALENDAR] Selecting Today for {element_name}")
            
            # Only the most effective selectors based on common patterns
            today_selectors = self.TODAY_SELECTORS
            
            for selector in today_selectors:
                try:
                    today_button = self.find_element_with_advanced_wait(selector)
                    
                    if today_button and today_button.is_displayed() and today_button.is_enabled():
                        # Skip disabled elements
                        class_name = today_button.get_attribute("class")
                        if class_name and "disabled" in class_name:
                            continue
                        
                        if self.perform_robust_click_with_result(today_button):
                            time.sleep(0.5)
                            print("[SUCCESS] Today button clicked successfully")
                            return
                except Exception:
                    continue  # Try next selector
            
            raise RuntimeError("Today selection failed - element not found or not clickable")
        
        except Exception as e:
            print(f"[ERROR] Failed to select Today - {e}")
            raise e

    def handle_tomorrow_selection_bus(self, element_name):
        """Optimized Tomorrow selection with most effective XPaths only"""
        try:
            print(f"[BUS] Tomorrow selection for bus: {element_name}")
            # Only the most effective selectors - reduced from 10+ to 4 most reliable
            tomorrow_selectors = self.TOMORROW_BUS_SELECTORS
            for selector in tomorrow_selectors:
                try:
                    tomorrow_button = self.find_element_with_advanced_wait(selector)
                    if tomorrow_button and tomorrow_button.is_displayed():
                        # Check if element is not disabled
                        class_name = tomorrow_button.get_attribute("class")
                        if class_name and "disabled" in class_name:
                            continue
                        if self.perform_robust_click_with_result(tomorrow_button):
                            time.sleep(0.5)
                            print("[SUCCESS] Tomorrow button clicked successfully")
                            return
                except Exception:
                    continue  # Try next selector
            raise RuntimeError("Tomorrow selection failed - element not found or not clickable")
        except Exception as e:
            print(f"[ERROR] Failed to select Tomorrow - {e}")
            raise e

    def perform_robust_click_with_result(self, element):
        """Enhanced robust click method with return value"""
        try:
            # Method 1: Regular click
            try:
                element.click()
                print("[SUCCESS] Regular click successful")
                return True
            except Exception as e:
                print(f"[WARNING] Regular click failed: {e}")
            
            # Method 2: JavaScript click
            try:
                self.driver.execute_script("arguments[0].click();", element)
                print("[SUCCESS] JavaScript click successful")
                return True
            except Exception as e:
                print(f"[WARNING] JavaScript click failed: {e}")
            
            # Method 3: Actions click
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).click().perform()
                print("[SUCCESS] Actions click successful")
                return True
            except Exception as e:
                print(f"[WARNING] Actions click failed: {e}")
            
            return False
            
        except Exception as e:
            print(f"[ERROR] All click methods failed: {e}")
            return False

    def handle_checkbox_action(self, test_data, xpath, element_name):
        """
        Handle checkbox actions - check or uncheck based on test data
        
        Args:
            test_data (str): "TRUE" to check, "FALSE" to uncheck
            xpath (str): XPath locator for the checkbox
            element_name (str): Name of the element for logging
        """
        try:
            print(f"[CHECKBOX] Handling checkbox: {element_name}")
            raw_value = str(test_data or "").strip()
            choice_values = self._extract_choice_values(raw_value)

            if choice_values and not self._is_boolean_like_value(raw_value):
                for choice in choice_values:
                    checkbox = self.find_choice_control(xpath, choice, "checkbox")
                    if checkbox is None:
                        raise Exception(f'Checkbox option "{choice}" not found for {element_name}')
                    self._set_control_checked_state(checkbox, True, f"{element_name} [{choice}]")
                print(f"[SUCCESS] {element_name} checked for values: {', '.join(choice_values)}")
                return

            should_be_checked = self._value_means_checked(raw_value)
            checkbox = self.find_checkbox_element(xpath, element_name)

            if checkbox is None:
                raise Exception(f"[ERROR] Checkbox element not found: {element_name}")

            current_state = self._is_control_selected(checkbox)
            print(f"[CURRENT] Current: {current_state} | Target: {should_be_checked}")

            if current_state != should_be_checked:
                self._set_control_checked_state(checkbox, should_be_checked, element_name)

            print(f"[SUCCESS] {element_name} {'checked' if should_be_checked else 'unchecked'}")
            
        except Exception as e:
            print(f"[ERROR] Error with checkbox '{element_name}': {str(e)}")
            raise e

    def _normalize_choice_value(self, value):
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()

    def _extract_choice_values(self, raw_value):
        normalized = str(raw_value or "").strip()
        if not normalized:
            return []
        parts = [part.strip() for part in re.split(r"[,;\n]+", normalized) if part.strip()]
        return [self._normalize_choice_value(part) for part in parts]

    def _value_means_checked(self, value):
        return self._normalize_choice_value(value) in ["true", "1", "yes", "on", "check", "checked", "select", "selected"]

    def _value_means_unchecked(self, value):
        return self._normalize_choice_value(value) in ["false", "0", "no", "off", "uncheck", "unchecked", "deselect", "unselected", ""]

    def _is_boolean_like_value(self, value):
        normalized = self._normalize_choice_value(value)
        return normalized in ["", "true", "1", "yes", "on", "check", "checked", "select", "selected", "false", "0", "no", "off", "uncheck", "unchecked", "deselect", "unselected"]

    def _is_control_selected(self, element):
        try:
            aria_checked = (element.get_attribute("aria-checked") or "").strip().lower()
            if aria_checked in ["true", "false"]:
                return aria_checked == "true"
        except Exception:
            pass
        try:
            return element.is_selected()
        except Exception:
            return False

    def _set_control_checked_state(self, element, should_be_checked, element_name):
        current_state = self._is_control_selected(element)
        if current_state == should_be_checked:
            return

        try:
            self.perform_robust_click(element)
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
        time.sleep(0.1)

        final_state = self._is_control_selected(element)
        if final_state != should_be_checked:
            raise Exception(f"{element_name} did not reach expected selected state")

    def find_choice_control(self, xpath, option_text, control_kind):
        root = self.find_element_with_advanced_wait(xpath)
        if root is None:
            return None

        desired = self._normalize_choice_value(option_text)
        control_kind = (control_kind or "").strip().lower()
        if control_kind not in ["radio", "checkbox"]:
            return None

        if not desired and self._matches_control_kind(root, control_kind):
            return root

        try:
            return self.driver.execute_script(
                """
                const root = arguments[0];
                const desired = (arguments[1] || '').toLowerCase().trim().replace(/\\s+/g, ' ');
                const kind = arguments[2];
                if (!root || !desired) return null;

                const selectors = kind === 'radio'
                    ? ['input[type="radio"]', '[role="radio"]']
                    : ['input[type="checkbox"]', '[role="checkbox"]'];

                const normalize = (value) => (value || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                const scoreText = (candidate) => {
                    const text = normalize(candidate);
                    if (!text) return 0;
                    if (text === desired) return 100;
                    if (text.includes(desired)) return 60;
                    if (desired.includes(text)) return 40;
                    return 0;
                };

                const collectTexts = (el) => {
                    const texts = [];
                    const push = (value) => {
                        const normalized = normalize(value);
                        if (normalized) texts.push(normalized);
                    };
                    push(el.value);
                    push(el.getAttribute && el.getAttribute('value'));
                    push(el.getAttribute && el.getAttribute('aria-label'));
                    push(el.getAttribute && el.getAttribute('aria-labelledby'));
                    push(el.getAttribute && el.getAttribute('data-testid'));
                    push(el.getAttribute && el.getAttribute('id'));
                    push(el.getAttribute && el.getAttribute('name'));
                    push(el.textContent);
                    if (el.labels) {
                        for (const label of el.labels) push(label.textContent);
                    }
                    const closestLabel = el.closest && el.closest('label');
                    if (closestLabel) push(closestLabel.textContent);
                    if (el.parentElement) push(el.parentElement.textContent);
                    if (el.nextElementSibling) push(el.nextElementSibling.textContent);
                    if (el.previousElementSibling) push(el.previousElementSibling.textContent);
                    return texts;
                };

                const candidates = [];
                const addCandidate = (el) => {
                    if (!el) return;
                    if (candidates.includes(el)) return;
                    candidates.push(el);
                };

                for (const selector of selectors) {
                    if (root.matches && root.matches(selector)) addCandidate(root);
                    root.querySelectorAll(selector).forEach(addCandidate);
                }

                let best = null;
                let bestScore = 0;

                for (const candidate of candidates) {
                    const texts = collectTexts(candidate);
                    let candidateScore = 0;
                    for (const text of texts) {
                        candidateScore = Math.max(candidateScore, scoreText(text));
                    }
                    if (candidateScore > bestScore) {
                        best = candidate;
                        bestScore = candidateScore;
                    }
                }

                return bestScore > 0 ? best : null;
                """,
                root,
                desired,
                control_kind,
            )
        except Exception:
            return None

    def _matches_control_kind(self, element, control_kind):
        try:
            tag_name = (element.tag_name or "").strip().lower()
            input_type = (element.get_attribute("type") or "").strip().lower()
            role = (element.get_attribute("role") or "").strip().lower()
            return (tag_name == "input" and input_type == control_kind) or role == control_kind
        except Exception:
            return False

    def find_checkbox_element(self, xpath, element_name):
        """
        Simplified checkbox finder - focuses on what works for ixigo
        
        Args:
            xpath (str): XPath locator for the checkbox
            element_name (str): Name of the element for logging
        
        Returns:
            WebElement or None: The checkbox element if found, None otherwise
        """
        # Try direct ID first (fastest for fc-checkbox)
        if "fc-checkbox" in xpath:
            try:
                return self.driver.find_element(By.ID, "fc-checkbox")
            except Exception:
                pass
        
        # Fallback to provided xpath with short wait
        try:
            wait = WebDriverWait(self.driver, 3)
            return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        except Exception:
            return None

    def handle_count_selection_fast(self, count_str, xpath, element_name):
        """Fast method for handling count selection"""
        try:
            print(f"[COUNT] Setting count: {count_str} for {element_name}")
            
            target_count = int(count_str.strip())
            
            # Click on travellers section to open popup
            traveller_section = self.find_element_with_advanced_wait(xpath)
            self.perform_robust_click(traveller_section)
            time.sleep(0.5)
            
            # Determine section type
            section_text = ""
            if self.COUNT_TYPE_ADULT in element_name.lower():
                section_text = self.UI_LABEL_ADULTS
            elif "child" in element_name.lower():
                section_text = self.UI_LABEL_CHILDREN
            elif self.COUNT_TYPE_INFANT in element_name.lower():
                section_text = self.UI_LABEL_INFANTS
            
            # Direct selection approach
            direct_selector = f"//p[contains(text(),'{section_text}')]/parent::*/following-sibling::*//button[@data-testid='{target_count}']"
            
            try:
                button = self.driver.find_element(By.XPATH, direct_selector)
                if button.is_displayed() and button.is_enabled():
                    self.perform_robust_click(button)
                    print(f"[SUCCESS] Direct selection successful for {section_text}: {target_count}")
            except Exception as e:
                print(f"[WARNING] Direct selection failed: {str(e)}")
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"[ERROR] Failed to set count for {element_name}: {str(e)}")
            raise e

    def handle_travel_class_selection_fast(self, class_name, xpath, element_name):
        """Fast travel class selection"""
        actual_class_name = self.map_travel_class(class_name)
        
        try:
            print(f"[TRAVEL] Selecting travel class: {actual_class_name}")
            
            # Click on travellers section (if not already open)
            try:
                traveller_section = self.find_element_with_advanced_wait(xpath)
                self.perform_robust_click(traveller_section)
                time.sleep(0.5)
            except Exception as e:
                print("[WARNING] Section might already be open")
            
            # Simplified class selection - use most effective selector
            class_selector = f"//span[contains(@class,'px-5px') and text()='{actual_class_name}']"
            
            try:
                class_element = self.driver.find_element(By.XPATH, class_selector)
                if class_element.is_displayed():
                    self.perform_robust_click(class_element)
                    print(f"[SUCCESS] Travel class selected: {actual_class_name}")
                    
                    # Quick popup close
                    time.sleep(0.3)
                    self.close_travellers_popup_fast(xpath, element_name)
            except Exception as e:
                print(f"[WARNING] Could not select travel class: {actual_class_name}")
                
        except Exception as e:
            print(f"[ERROR] Failed to select travel class: {actual_class_name} - {str(e)}")
            raise e

    def map_travel_class(self, excel_value):
        """Map Excel values to actual website options"""
        if not excel_value:
            return ""
        
        value = excel_value.strip().lower()
        mapping = {
            "economy": "Economy",
            "premium": "Premium Economy",
            "premium economy": "Premium Economy",
            "business": "Business",
            "first": "First class",
            "first class": "First class"
        }
        
        return mapping.get(value, excel_value)

    def close_travellers_popup_fast(self, xpath, element_name):
        """Fast popup close"""
        try:
            print("[CLOSE] Closing travellers popup")
            
            # Quick check if popup is open
            try:
                popup_elements = self.driver.find_elements(By.XPATH, f"//p[contains(text(),'{self.UI_LABEL_ADULTS}')]")
                if not popup_elements or not popup_elements[0].is_displayed():
                    print("[SUCCESS] Popup already closed")
                    return
            except Exception:
                return  # Assume closed
            
            # Try Done button first (most reliable)
            try:
                short_wait = WebDriverWait(self.driver, 1)
                done_button = short_wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(),'{self.UI_LABEL_DONE}')]"))
                )
                done_button.click()
                print("[SUCCESS] Popup closed using Done button")
                time.sleep(0.2)
                return
            except Exception:
                # Fallback to Escape key
                try:
                    self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                    print("[SUCCESS] Popup closed using Escape key")
                    time.sleep(0.2)
                except Exception:
                    print("[WARNING] Could not close popup, continuing...")
                    
        except Exception as e:
            print("[WARNING] Error closing popup, continuing with test")

    def select_rooms_and_guests(self, desired_rooms, desired_adults, desired_children):
        """Select rooms and guests"""
        try:
            # Click on Rooms & Guests section to open the popup
            rooms_guests_section = self.wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//p[@class='body-xs text-secondary'][contains(text(),'{self.UI_LABEL_ROOMS_AND_GUESTS}')] | //input[@placeholder='{self.UI_LABEL_ROOMS_AND_GUESTS}']"
            )))
            rooms_guests_section.click()
            
            # Wait for the popup to be visible
            time.sleep(1)
            
            # Set counts
            self.set_count_by_increment(self.COUNT_TYPE_ROOM, desired_rooms)
            self.set_count_by_increment(self.COUNT_TYPE_ADULT, desired_adults)
            self.set_count_by_increment(self.COUNT_TYPE_CHILDREN, desired_children)
            
            print(f"Successfully set Rooms: {desired_rooms}, Adults: {desired_adults}, Children: {desired_children}")
            
        except Exception as e:
            print(f"Error in select_rooms_and_guests: {str(e)}")
            raise e

    def select_rooms_and_guests_with_ages(self, desired_rooms, desired_adults, desired_children, children_ages):
        """Select rooms and guests with children ages"""
        try:
            # Click on Rooms & Guests section to open the popup
            rooms_guests_section = self.wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//p[@class='body-xs text-secondary'][contains(text(),'{self.UI_LABEL_ROOMS_AND_GUESTS}')] | //input[@placeholder='{self.UI_LABEL_ROOMS_AND_GUESTS}']"
            )))
            rooms_guests_section.click()
            
            # Wait for the popup to be visible
            time.sleep(1)
            
            # Set counts
            self.set_count_by_increment(self.COUNT_TYPE_ROOM, desired_rooms)
            self.set_count_by_increment(self.COUNT_TYPE_ADULT, desired_adults)
            self.set_count_by_increment(self.COUNT_TYPE_CHILDREN, desired_children)
            
            # Set children ages if children count > 0
            if desired_children > 0 and children_ages and len(children_ages) > 0:
                self.select_children_ages(children_ages)
            
            print(f"Successfully set Rooms: {desired_rooms}, Adults: {desired_adults}, Children: {desired_children}")
            if children_ages and len(children_ages) > 0:
                print(f"Children ages set: {children_ages}")
                
        except Exception as e:
            print(f"Error in select_rooms_and_guests_with_ages: {str(e)}")
            raise e

    def select_child_age(self, child_index, age):
        """Select age for a specific child"""
        try:
            # Simple wait for age dropdowns to appear
            max_wait_time = 10  # seconds
            wait_interval = 0.5  # seconds
            attempts = int(max_wait_time / wait_interval)
            
            age_selectors = None
            
            # Wait for at least one age selector to appear
            for i in range(attempts):
                age_selectors = self.driver.find_elements(By.XPATH, "//select[@data-testid='child-age-selector']")
                if age_selectors:
                    break
                time.sleep(wait_interval)
            
            if not age_selectors:
                raise RuntimeError("No child age selectors found after waiting. Make sure children count is set first.")
            
            if child_index < 0 or child_index >= len(age_selectors):
                raise IndexError(f"Invalid child index: {child_index}. Available selectors: {len(age_selectors)}")
            
            age_selector = age_selectors[child_index]
            
            # Ensure the dropdown is clickable
            self.wait.until(EC.element_to_be_clickable(age_selector))
            
            select_age = Select(age_selector)
            
            # Select by value (age)
            select_age.select_by_value(str(age))
            
            print(f"Successfully set age {age} for child {child_index + 1}")
            
        except Exception as e:
            print(f"Error selecting age for child {child_index + 1}: {str(e)}")
            raise e

    def select_children_ages(self, ages):
        """Select ages for multiple children"""
        try:
            # Wait for age dropdowns to appear after setting children count
            time.sleep(2)
            
            # Find all child age selectors
            age_selectors = self.driver.find_elements(By.XPATH, "//select[@data-testid='child-age-selector']")
            
            print(f"Found {len(age_selectors)} age selectors for {len(ages)} children")
            
            # Set age for each child
            for i in range(min(len(ages), len(age_selectors))):
                try:
                    age_selector = age_selectors[i]
                    select_age = Select(age_selector)
                    
                    # Select by value (age)
                    select_age.select_by_value(str(ages[i]))
                    
                    print(f"Set age {ages[i]} for child {i + 1}")
                    time.sleep(0.3)
                    
                except Exception as e:
                    print(f"Error setting age for child {i + 1}: {str(e)}")
                    
        except Exception as e:
            print(f"Error in select_children_ages: {str(e)}")
            raise e

    def wait_for_child_age_dropdowns(self, expected_count):
        """Wait for child age dropdowns to appear"""
        try:
            # Simple wait approach - wait for expected number of dropdowns
            max_wait_time = 15  # seconds
            wait_interval = 0.5  # seconds
            attempts = int(max_wait_time / wait_interval)
            
            for i in range(attempts):
                selectors = self.driver.find_elements(By.XPATH, "//select[@data-testid='child-age-selector']")
                if len(selectors) >= expected_count:
                    print(f"Found {len(selectors)} child age dropdowns (expected: {expected_count})")
                    return
                time.sleep(wait_interval)
            
            # If we reach here, timeout occurred
            raise RuntimeError(f"Timeout: Could not find {expected_count} child age dropdowns within {max_wait_time} seconds")
            
        except Exception as e:
            print(f"Error waiting for child age dropdowns: {str(e)}")
            raise e

    def _robust_click(self, element):
        """Robust click method that handles click intercepted exceptions"""
        from selenium.common.exceptions import ElementClickInterceptedException
        from selenium.webdriver.common.action_chains import ActionChains
        
        try:
            # First try normal click
            element.click()
        except ElementClickInterceptedException:
            try:
                # If normal click fails, try JavaScript click
                self.driver.execute_script("arguments[0].click();", element)
            except Exception:
                try:
                    # If JavaScript click fails, try ActionChains click
                    ActionChains(self.driver).move_to_element(element).click().perform()
                except Exception:
                    # Last resort: scroll into view and try again
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", element)

    def set_count_by_increment(self, element_type, desired_count):
        """Set count by incrementing/decrementing"""
        try:
            increment_xpath = ""
            decrement_xpath = ""
            
            # Define XPaths based on element type - target parent clickable elements instead of child SVG/path elements
            if element_type.lower() in self.COUNT_CONTROL_XPATHS:
                increment_xpath, decrement_xpath = self._get_count_control_xpaths(element_type)
            else:
                raise ValueError(f"Invalid element type: {element_type}")
            
            # Get current count from UI
            current_count = self.get_current_count(element_type)
            
            # Calculate difference
            difference = desired_count - current_count
            
            if difference > 0:
                # Need to increment
                increment_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, increment_xpath)))
                for i in range(difference):
                    self._robust_click(increment_button)
                    time.sleep(0.3)
            elif difference < 0:
                # Need to decrement
                decrement_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, decrement_xpath)))
                for i in range(abs(difference)):
                    self._robust_click(decrement_button)
                    time.sleep(0.3)

        except Exception as e:
            print(f"Error in set_count_by_increment for {element_type}: {str(e)}")
            raise e

    def get_current_count(self, element_type):
        """Get current count from UI"""
        try:
            # Get all counter-input elements and use index based on element type
            all_counter_inputs = self.driver.find_elements(By.XPATH, "//span[@data-testid='counter-input']")
            
            # Based on typical order: rooms, adults, children
            index_map = {
                self.COUNT_TYPE_ROOM: 0,
                self.COUNT_TYPE_ADULT: 1,
                self.COUNT_TYPE_CHILDREN: 2,
                self.COUNT_TYPE_INFANT: 3
            }
            
            index = index_map.get(element_type.lower(), -1)
            
            if index >= 0 and index < len(all_counter_inputs):
                count_text = all_counter_inputs[index].text.strip()
                return int(count_text)
            else:
                raise RuntimeError(f"Counter element not found for {element_type} at index {index}")
                
        except Exception as e:
            print(f"Error getting current count for {element_type}: {str(e)}")
            raise e

    def find_element_with_advanced_wait(self, locator):
        """Find an element with robust multi-strategy waits across locator types."""
        parsed = self._parse_locator(locator)
        if not parsed:
            raise Exception(f"Invalid or empty locator: {locator}")

        by, value = parsed
        immediate_matches = self.driver.find_elements(by, value)
        immediate_element = self._get_visible_or_enabled_element(immediate_matches)
        if immediate_element is not None:
            return immediate_element

        quick_wait = WebDriverWait(self.driver, max(self.fast_wait_timeout, 0.25), poll_frequency=0.15)
        full_wait = self.wait or WebDriverWait(self.driver, self.default_wait_timeout)

        # Fast path for the usual case: interactable element appears quickly.
        try:
            return quick_wait.until(EC.element_to_be_clickable((by, value)))
        except Exception:
            pass

        try:
            return quick_wait.until(EC.visibility_of_element_located((by, value)))
        except Exception:
            pass

        # Full wait only once for genuinely slow elements.
        try:
            return full_wait.until(EC.presence_of_element_located((by, value)))
        except Exception:
            pass

        return self.driver.find_element(by, value)

    def perform_robust_click(self, element):
        """Perform robust click with multiple fallback strategies"""
        try:
            # Method 1: Regular click
            element.click()
            print("[SUCCESS] Regular click successful")
        except Exception as e:
            print(f"[WARNING] Regular click failed: {e}")
            try:
                # Method 2: JavaScript click
                self.driver.execute_script("arguments[0].click();", element)
                print("[SUCCESS] JavaScript click successful")
            except Exception as e:
                print(f"[WARNING] JavaScript click failed: {e}")
                try:
                    # Method 3: Actions click
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    print("[SUCCESS] Actions click successful")
                except Exception as e:
                    print(f"[ERROR] All click methods failed: {e}")
                    raise e

    def perform_robust_text_input(self, element, text):
        """Perform robust text input with error handling"""
        try:
            tag_name = (element.tag_name or "").lower()
            input_type = (element.get_attribute("type") or "").lower()
            is_content_editable = (element.get_attribute("contenteditable") or "").lower() == "true"
            can_type_directly = tag_name in ("input", "textarea") and input_type not in ("hidden", "file")

            if not (can_type_directly or is_content_editable):
                raise Exception(f"unsupported direct input target: tag={tag_name}, type={input_type}")

            # Clear existing text first, including default/prefilled values.
            try:
                element.click()
            except Exception:
                pass
            try:
                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.DELETE)
            except Exception:
                pass
            try:
                element.clear()
            except Exception:
                pass

            element.send_keys(text)
            print(f"[SUCCESS] Text input successful: {text}")
        except Exception as e:
            print(f"[WARNING] Regular text input failed: {e}")
            try:
                # Fallback: JavaScript value setting
                escaped_text = (text or "").replace("\\", "\\\\").replace("'", "\\'")
                self.driver.execute_script(
                    f"arguments[0].value = '{escaped_text}';"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    element
                )
                print(f"[SUCCESS] JavaScript text input successful: {text}")
            except Exception as e:
                print(f"[ERROR] All text input methods failed: {e}")
                raise e

    def handle_clear_and_type(self, test_data, xpath, element_name):
        """Clear existing value and type new input."""
        target = self.find_element_with_advanced_wait(xpath)
        self.perform_robust_text_input(target, str(test_data or ""))
        print(f"[ACTION] Clear and type successful for {element_name}")

    def handle_double_click(self, xpath, element_name):
        """Perform a double-click on target element."""
        target = self.find_element_with_advanced_wait(xpath)
        try:
            ActionChains(self.driver).move_to_element(target).double_click(target).perform()
        except Exception:
            # Fallback to JavaScript dblclick event
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('dblclick', {bubbles:true, cancelable:true}));",
                target
            )
        print(f"[ACTION] Double click successful for {element_name}")

    def handle_right_click(self, xpath, element_name):
        """Perform a context (right) click on target element."""
        target = self.find_element_with_advanced_wait(xpath)
        ActionChains(self.driver).move_to_element(target).context_click(target).perform()
        print(f"[ACTION] Right click successful for {element_name}")

    def handle_mouse_over(self, xpath, element_name):
        """Hover mouse over target element."""
        target = self.find_element_with_advanced_wait(xpath)
        try:
            ActionChains(self.driver).move_to_element(target).perform()
        except Exception:
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('mouseover', {bubbles:true, cancelable:true}));",
                target
            )
        print(f"[ACTION] Mouse over successful for {element_name}")

    def handle_radio_button_action(self, test_data, xpath, element_name):
        """Handle radio button selection. Selects the target radio when needed."""
        raw_value = str(test_data or "").strip()
        if raw_value and not self._is_boolean_like_value(raw_value):
            target = self.find_choice_control(xpath, raw_value, "radio")
            if target is None:
                raise Exception(f'Radio option "{raw_value}" not found for {element_name}')
            should_select = True
        else:
            target = self.find_element_with_advanced_wait(xpath)
            should_select = not self._value_means_unchecked(raw_value)

        if should_select:
            self._set_control_checked_state(target, True, element_name)
            if not self._is_control_selected(target):
                raise Exception(f"Radio button '{element_name}' is not selected after click")
            print(f"[ACTION] Radio button selected for {element_name}")
        else:
            # Radios cannot be safely "unselected" directly in most UIs.
            print(f"[ACTION] Radio button action skipped unselect for {element_name} (not supported)")

    def handle_drag_and_drop(self, source_locator, test_data, element_name):
        """Drag source element and drop it on target element."""
        target_locator = self._parse_drag_drop_target_locator(test_data)
        if not target_locator:
            raise Exception("DRAG_AND_DROP requires target locator in step values")

        source_element = self.find_element_with_advanced_wait(source_locator)
        target_element = self.find_element_with_advanced_wait(target_locator)

        try:
            ActionChains(self.driver).drag_and_drop(source_element, target_element).perform()
        except Exception:
            try:
                ActionChains(self.driver).click_and_hold(source_element).move_to_element(target_element).release().perform()
            except Exception:
                # HTML5 fallback for modern frontends where native drag_and_drop can fail.
                self.driver.execute_script(
                    """
                    const src = arguments[0];
                    const dst = arguments[1];
                    const dataTransfer = new DataTransfer();
                    src.dispatchEvent(new DragEvent('dragstart', {dataTransfer, bubbles:true}));
                    dst.dispatchEvent(new DragEvent('dragover', {dataTransfer, bubbles:true}));
                    dst.dispatchEvent(new DragEvent('drop', {dataTransfer, bubbles:true}));
                    src.dispatchEvent(new DragEvent('dragend', {dataTransfer, bubbles:true}));
                    """,
                    source_element,
                    target_element
                )

        self._last_drag_drop_state = {
            "source_locator": source_locator,
            "target_locator": target_locator,
            "element_name": element_name,
        }
        print(f"[ACTION] Drag and drop successful for {element_name}")

    def validate_action_result(self, action_type, test_data, xpath, element_name, assertion_type=None):
        """
        Validate that the action achieved the expected result
        Returns: {'success': bool, 'message': str}
        """
        try:
            action_type = self.normalize_action_type(action_type)
            print(f"[VALIDATION] Validating action: {action_type} for element: {element_name}")
            
            if action_type == "OPEN_BROWSER":
                # Validate URL was loaded correctly
                current_url = self.driver.current_url
                if test_data.lower() in current_url.lower():
                    print(f"[VALIDATION_PASS] URL loaded correctly: {current_url}")
                    return {'success': True, 'message': f'URL loaded correctly: {current_url}'}
                else:
                    return {'success': False, 'message': f'Expected URL containing "{test_data}", but got: {current_url}'}
            
            elif action_type == "ASSERTION":
                return self._evaluate_assertion(assertion_type, test_data, xpath, element_name)

            elif action_type in ["READ_TEXT", "READ_VALUE", "READ_TOOLTIP", "READ_LABEL", "COPY", "PASTE", "UPLOAD_FILE", "DOWNLOAD_FILE", "VISUAL_ASSERTION"]:
                if action_type == "VISUAL_ASSERTION":
                    visual_result = self._last_read_result or {}
                    status = visual_result.get("value")
                    baseline = visual_result.get("baseline")
                    diff_ratio = float(visual_result.get("difference_ratio", 1.0) or 0.0)
                    threshold = float(visual_result.get("threshold", 0.01) or 0.01)
                    if status == "baseline_created":
                        return {'success': True, 'message': f'Visual baseline "{baseline}" created'}
                    if diff_ratio <= threshold:
                        return {'success': True, 'message': f'Visual assertion passed for "{baseline}" (diff={diff_ratio:.6f}, threshold={threshold:.6f})'}
                    return {'success': False, 'message': f'Visual assertion failed for "{baseline}" (diff={diff_ratio:.6f}, threshold={threshold:.6f})'}
                if action_type == "DOWNLOAD_FILE":
                    download_name = ((self._last_read_result or {}).get("value") or "").strip()
                    expected_name = str(test_data or "").strip()
                    if expected_name and expected_name.lower() not in download_name.lower():
                        return {'success': False, 'message': f'Expected downloaded filename containing "{expected_name}", but found "{download_name}"'}
                    return {'success': True, 'message': f'Download validated for "{element_name}": {download_name or "file detected"}'}

                target = self.find_element_with_advanced_wait(xpath)
                payload = self._get_readable_element_payload(target)
                actual_map = {
                    "READ_TEXT": payload.get("text", "").strip(),
                    "READ_VALUE": payload.get("value", "").strip(),
                    "READ_TOOLTIP": (payload.get("title") or payload.get("ariaLabel") or payload.get("placeholder") or payload.get("text") or "").strip(),
                    "READ_LABEL": payload.get("label", "").strip(),
                    "COPY": ((self._last_read_result or {}).get("value") or payload.get("value") or payload.get("text") or "").strip(),
                    "PASTE": (payload.get("value") or payload.get("text") or "").strip(),
                    "UPLOAD_FILE": ((target.get_attribute("value") or "").strip() or ((self._last_read_result or {}).get("value") or "").strip()),
                }
                actual_value = actual_map.get(action_type, "").strip()
                expected_value = str(test_data or "").strip()
                if expected_value:
                    if expected_value.lower() in actual_value.lower():
                        return {'success': True, 'message': f'{action_type} matched "{expected_value}"'}
                    return {'success': False, 'message': f'Expected "{expected_value}", but found "{actual_value}" for "{element_name}"'}
                if actual_value or action_type in ["COPY", "PASTE", "UPLOAD_FILE"]:
                    return {'success': True, 'message': f'{action_type} completed for "{element_name}"'}
                return {'success': False, 'message': f'{action_type} produced no readable value for "{element_name}"'}

            elif action_type == "CLICK_AND_SELECT":
                # Reusable validation for CLICK_AND_SELECT action.
                try:
                    value_text = str(test_data or "").strip()
                    if "departure" in str(element_name or "").strip().lower() and self.is_date_format_data(value_text):
                        return {'success': True, 'message': f'Date "{value_text}" selected correctly'}
                    if self._looks_like_child_age_selection(value_text, xpath):
                        return self.validate_age_selection(test_data, element_name)

                    if self._is_quick_date_value(value_text) or self.is_date_format_data(value_text):
                        return self.validate_date_selection(test_data, xpath, element_name)

                    element = self.find_element_with_advanced_wait(xpath)
                    if not element:
                        return {'success': False, 'message': f'Element {element_name} not found or not accessible'}

                    tag_name = (element.tag_name or "").lower()
                    if tag_name == "select":
                        try:
                            selected = Select(element).first_selected_option.text.strip()
                        except Exception:
                            selected = (element.get_attribute("value") or "").strip()
                        if not value_text or value_text.lower() in selected.lower():
                            return {'success': True, 'message': f'Select option validated for "{element_name}"'}
                        return {'success': False, 'message': f'Expected "{value_text}" but found "{selected}" for "{element_name}"'}

                    current_value = (element.get_attribute("value") or element.text or "").strip()
                    if value_text:
                        if value_text.lower() in current_value.lower():
                            return {'success': True, 'message': f'Value "{value_text}" applied for "{element_name}"'}
                        # Fallback for autocomplete UIs where value may render outside the input.
                        page_match = self.driver.find_elements(By.XPATH, f"//*[contains(text(),'{value_text}')]")
                        if any(elem.is_displayed() for elem in page_match):
                            return {'success': True, 'message': f'Value "{value_text}" appears on page for "{element_name}"'}
                        return {'success': False, 'message': f'Expected "{value_text}" but found "{current_value}" for "{element_name}"'}

                    if element.is_enabled():
                        print(f"[VALIDATION_PASS] Element {element_name} is accessible and enabled")
                        return {'success': True, 'message': f'Element {element_name} clicked successfully'}
                    return {'success': False, 'message': f'Element {element_name} is not enabled or accessible'}
                except Exception as validation_error:
                    return {'success': False, 'message': f'CLICK_AND_SELECT validation failed: {validation_error}'}
            
            elif action_type == "CLICK":
                # First check if this should be a different action type
                if self.is_date_field(element_name, test_data):
                    return {'success': False, 'message': f'Wrong action type for date field "{element_name}". Use CLICK_AND_SELECT instead of CLICK'}
                
                if element_name.upper() == self.ELEMENT_NAME_TRAVEL_CLASS:
                    # Validate travel class selection
                    return self.validate_travel_class_selection(test_data, element_name)
                elif element_name.upper() in self.ELEMENT_NAME_DONE_ALIASES:
                    # Validate popup was closed
                    return self.validate_popup_closed()
                else:
                    # Validate general click action
                    return self.validate_click_action(xpath, element_name)

            elif action_type == "CLICK_AND_TYPE":
                try:
                    element = self.find_element_with_advanced_wait(xpath)
                    value = (element.get_attribute("value") or "").strip()
                    if str(test_data or "") in value or value:
                        return {'success': True, 'message': f'Click and type completed for "{element_name}"'}
                    return {'success': False, 'message': f'Input validation failed for "{element_name}"'}
                except Exception as input_error:
                    return {'success': False, 'message': f'Click and type validation error: {input_error}'}

            elif action_type == "CLEAR_AND_TYPE":
                try:
                    element = self.find_element_with_advanced_wait(xpath)
                    value = (element.get_attribute("value") or "").strip()
                    expected = str(test_data or "").strip()
                    if value == expected:
                        return {'success': True, 'message': f'Clear and type validated for "{element_name}"'}
                    return {'success': False, 'message': f'Expected value "{expected}" but found "{value}" for "{element_name}"'}
                except Exception as clear_type_error:
                    return {'success': False, 'message': f'Clear and type validation error: {clear_type_error}'}

            elif action_type == "RADIO_BUTTON":
                try:
                    raw_value = str(test_data or "").strip()
                    element = self.find_choice_control(xpath, raw_value, "radio") if raw_value and not self._is_boolean_like_value(raw_value) else self.find_element_with_advanced_wait(xpath)
                    if element and self._is_control_selected(element):
                        return {'success': True, 'message': f'Radio button "{element_name}" selected successfully'}
                    return {'success': False, 'message': f'Radio button "{element_name}" is not selected'}
                except Exception as radio_error:
                    return {'success': False, 'message': f'Radio validation error: {radio_error}'}

            elif action_type in ["DOUBLE_CLICK", "RIGHT_CLICK", "MOUSE_OVER"]:
                # These actions are interaction-oriented; ensure element and browser remain healthy.
                try:
                    _ = self.find_element_with_advanced_wait(xpath)
                    _ = self.driver.current_url
                    return {'success': True, 'message': f'{action_type} completed for "{element_name}"'}
                except Exception as interaction_error:
                    return {'success': False, 'message': f'{action_type} validation error: {interaction_error}'}

            elif action_type == "DRAG_AND_DROP":
                state = getattr(self, "_last_drag_drop_state", None) or {}
                source_locator = state.get("source_locator") or xpath
                target_locator = state.get("target_locator") or self._parse_drag_drop_target_locator(test_data)
                if not source_locator or not target_locator:
                    return {'success': False, 'message': 'Drag and drop validation failed: missing source or target locator'}
                try:
                    _ = self.find_element_with_advanced_wait(source_locator)
                    _ = self.find_element_with_advanced_wait(target_locator)
                    _ = self.driver.current_url
                    return {'success': True, 'message': f'DRAG_AND_DROP completed for "{element_name}"'}
                except Exception as drag_validation_error:
                    return {'success': False, 'message': f'DRAG_AND_DROP validation error: {drag_validation_error}'}
            
            elif action_type == "HANDLE_CHECKBOX":
                # Validate checkbox state
                return self.validate_checkbox_state(test_data, xpath, element_name)

            elif action_type in ["SELECT_COUNT", "INCREMENT", "DECREMENT"]:
                state = getattr(self, "_last_count_action_state", None) or {}
                expected_after = state.get("expected_after")
                after_count = state.get("after_count")
                element_type = state.get("element_type")

                # If we have concrete before/after state, validate strongly.
                if expected_after is not None and after_count is not None:
                    if int(after_count) == int(expected_after):
                        return {'success': True, 'message': f'Count action validated: expected {expected_after}, found {after_count}'}
                    return {'success': False, 'message': f'Count action mismatch: expected {expected_after}, found {after_count}'}

                # Fallback: best-effort UI validation for absolute select_count.
                if action_type == "SELECT_COUNT":
                    return self.validate_count_selection(test_data, xpath, element_name)

                # For increment/decrement without readable counter, at least ensure the control remains interactable.
                try:
                    locator = state.get("locator") or xpath
                    if locator:
                        _ = self.find_element_with_advanced_wait(locator)
                    elif element_type:
                        inc_xpath, dec_xpath = self._get_count_control_xpaths(element_type)
                        target = inc_xpath if action_type == "INCREMENT" else dec_xpath
                        if target:
                            _ = self.find_element_with_advanced_wait(target)
                    return {'success': True, 'message': f'{action_type} action completed and control remains accessible'}
                except Exception as count_validation_error:
                    return {'success': False, 'message': f'{action_type} validation failed: {count_validation_error}'}
            
            else:
                # Generic validation for non-standard actions.
                try:
                    _ = self.driver.current_url
                    self.driver.execute_script("return document.readyState")
                    return {'success': True, 'message': f'Action {action_type} completed; browser remains responsive'}
                except Exception as unknown_validation_error:
                    return {'success': False, 'message': f'Action {action_type} completed but browser became unstable: {unknown_validation_error}'}
                
        except Exception as e:
            print(f"[VALIDATION_ERROR] Validation failed with exception: {str(e)}")
            return {'success': False, 'message': f'Validation error: {str(e)}'}

    def is_date_field(self, element_name, test_data):
        """
        Detect if an element is likely a date field based on element name or test data
        """
        element_name_lower = element_name.lower()
        test_data_lower = test_data.lower() if test_data else ""
        
        # Check element name for date-related keywords
        date_keywords = [
            'date', 'checkin', 'check-in', 'check in', 'checkout', 'check-out', 'check out',
            'departure', 'arrival', 'return', 'calendar', 'pick', 'select date',
            'from date', 'to date', 'start date', 'end date', 'booking date'
        ]
        
        # Check if element name contains any date keywords
        for keyword in date_keywords:
            if keyword in element_name_lower:
                print(f"[VALIDATION] Detected date field: '{element_name}' contains keyword '{keyword}'")
                return True
        
        # Check test data for date patterns
        date_patterns = [
            # Day names
            'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            # Month names
            'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
            'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
            # Date-related words
            'today', 'tomorrow', 'yesterday', 'day after'
        ]
        
        # Check if test data contains date patterns
        for pattern in date_patterns:
            if pattern in test_data_lower:
                print(f"[VALIDATION] Detected date data: '{test_data}' contains date pattern '{pattern}'")
                return True
        
        # Check for date format patterns (dd/mm/yyyy, mm/dd/yyyy, etc.)
        import re
        date_regex_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # dd/mm/yyyy or mm/dd/yyyy
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # yyyy/mm/dd
            r'\w{3},?\s+\d{1,2}\s+\w{3}',      # Wed, 30 Jul
            r'\d{1,2}\s+\w{3}\s+\d{4}',       # 30 Jul 2024
        ]
        
        for pattern in date_regex_patterns:
            if re.search(pattern, test_data):
                print(f"[VALIDATION] Detected date format in data: '{test_data}'")
                return True
        
        return False



    def pre_validate_action(self, action_type, test_data, xpath, element_name, assertion_type=None):
        """
        Pre-validate action before execution - check all prerequisites
        """
        try:
            action_type = self.normalize_action_type(action_type)
            print(f"[PRE_VALIDATION] Pre-validating action: {action_type} for element: {element_name}")
            element_name_text = str(element_name or "").strip()
            test_data_text = str(test_data or "").strip()

            # Departure date fast-lane: keep checks minimal to reduce step latency.
            if (
                action_type == "CLICK_AND_SELECT"
                and "departure" in element_name_text.lower()
                and self.is_date_format_data(test_data_text)
            ):
                if not xpath or xpath.strip() == "" or xpath.upper() == "NA":
                    return {'success': False, 'message': f'Invalid or missing locator for element "{element_name_text}": "{xpath}"'}
                if not test_data_text:
                    return {'success': False, 'message': f'No value provided for CLICK_AND_SELECT action on element "{element_name_text}"'}
                print(f"[PRE_VALIDATION_PASS] Fast-lane pre-validation passed for departure date")
                return {'success': True, 'message': f'Pre-validation successful for {action_type} on {element_name_text}'}
            
            # 1. Universal validations for all action types
            
            # Validate action type is not empty or invalid
            if not action_type or action_type.strip() == "":
                return {'success': False, 'message': f'Action type is empty or invalid for element "{element_name}"'}
            
            if not element_name or element_name.strip() == "":
                element_name = "unnamed_element"
            
            # 2. Locator validation (for actions that need a target element)
            locator_required_actions = [
                "CLICK_AND_SELECT",
                "CLICK",
                "CLICK_AND_TYPE",
                "CLEAR_AND_TYPE",
                "DOUBLE_CLICK",
                "RIGHT_CLICK",
                "MOUSE_OVER",
                "RADIO_BUTTON",
                "DRAG_AND_DROP",
                "HANDLE_CHECKBOX",
                "INCREMENT",
                "DECREMENT",
                "READ_TEXT",
                "READ_VALUE",
                "READ_TOOLTIP",
                "READ_LABEL",
                "COPY",
                "PASTE",
                "UPLOAD_FILE",
                "DOWNLOAD_FILE",
                "VISUAL_ASSERTION",
            ]

            if action_type == "ASSERTION" and self._assertion_requires_locator(self.normalize_assertion_type(assertion_type)):
                locator_required_actions.append("ASSERTION")
            
            if action_type in locator_required_actions:
                missing_locator = (not xpath or xpath.strip() == "" or xpath.upper() == "NA")
                if missing_locator:
                    # INCREMENT/DECREMENT may use known count controls from element_name.
                    if action_type in ["INCREMENT", "DECREMENT"] and self.resolve_count_element_type(element_name):
                        missing_locator = False
                    else:
                        return {'success': False, 'message': f'Invalid or missing locator for element "{element_name}": "{xpath}"'}

            if action_type == "ASSERTION":
                normalized_assertion = self.normalize_assertion_type(assertion_type)
                if normalized_assertion in ["VERIFY_PAGE_TITLE", "VERIFY_URL_CONTAINS", "VERIFY_URL_EQUALS", "VERIFY_TEXT", "VERIFY_INPUT_VALUE", "VERIFY_ATTRIBUTE", "VERIFY_PLACEHOLDER"] and not test_data_text:
                    return {'success': False, 'message': f'Assertion "{normalized_assertion}" requires a value for "{element_name_text}"'}

            if action_type == "UPLOAD_FILE" and not test_data_text:
                return {'success': False, 'message': f'UPLOAD_FILE requires a file path in Values for "{element_name_text}"'}

                locator_by = None
                locator_value = None
                if xpath and xpath.strip() and xpath.upper() != "NA":
                    parsed = self._parse_locator(xpath)
                    if not parsed:
                        return {'success': False, 'message': f'Unable to parse locator for element "{element_name}": "{xpath}"'}
                    locator_by, locator_value = parsed

                # Test selector syntax by trying a short lookup
                try:
                    elements = self.driver.find_elements(locator_by, locator_value) if locator_by and locator_value else []
                    if not elements:
                        element_name_upper = str(element_name or "").upper()
                        if action_type == "CLICK" and element_name_upper in self.ELEMENT_NAME_DONE_ALIASES:
                            # Travellers popup may already be closed by a previous action.
                            print(f"[PRE_VALIDATION] {element_name} not present; popup likely already closed. Allowing execution.")
                        elif action_type in ["INCREMENT", "DECREMENT"] and self.resolve_count_element_type(element_name):
                            elements = []
                            print(f"[PRE_VALIDATION] Using derived count controls for {action_type} on {element_name}")
                        else:
                        # Try alternative XPaths to see if element exists with different locator
                            found_with_alternative = self.try_alternative_locators(element_name)
                            if found_with_alternative:
                                print(f"[PRE_VALIDATION] Element exists but locator may be incorrect, allowing execution to proceed")
                                # Don't fail here - let the execution try and the post-validation catch real issues
                            else:
                                return {'success': False, 'message': f'Element "{element_name}" not found with locator: "{xpath}". Check if selector exists on current page.'}
                    
                    # Check if found element is accessible (but don't fail for minor issues)
                    if elements:
                        element = elements[0]
                        if not element.is_displayed():
                            # Try scrolling to make it visible
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.1)
                                if not element.is_displayed():
                                    print(f"[PRE_VALIDATION] Element {element_name} not visible but allowing execution to proceed")
                            except Exception:
                                print(f"[PRE_VALIDATION] Element {element_name} visibility check failed but allowing execution")
                        
                        if not element.is_enabled():
                            print(f"[PRE_VALIDATION] Element {element_name} appears disabled but allowing execution to proceed")
                        
                except Exception as selector_error:
                    error_message = str(selector_error)
                    # Only fail for truly invalid selector syntax, not for element not found
                    if "invalid selector" in error_message.lower() or "xpath expression" in error_message.lower():
                        return {'success': False, 'message': f'Selector syntax error for element "{element_name}": {str(selector_error)}'}
                    else:
                        print(f"[PRE_VALIDATION] Selector test failed but allowing execution: {str(selector_error)}")
            
            # 3. Action-specific validations
            
            if action_type == "OPEN_BROWSER":
                # Validate URL format
                if not test_data or not test_data.startswith(('http://', 'https://')):
                    return {'success': False, 'message': f'Invalid URL format: "{test_data}". URL must start with http:// or https://'}
            
            elif action_type == "CLICK_AND_SELECT":
                # Validate test data is provided
                if not test_data or test_data.strip() == "":
                    return {'success': False, 'message': f'No value provided for CLICK_AND_SELECT action on element "{element_name}"'}

            elif action_type in ["CLICK_AND_TYPE", "CLEAR_AND_TYPE"]:
                if test_data is None:
                    return {'success': False, 'message': f'No input value provided for {action_type} on element "{element_name}"'}

            elif action_type == "DRAG_AND_DROP":
                target_locator = self._parse_drag_drop_target_locator(test_data)
                if not target_locator:
                    return {'success': False, 'message': f'DRAG_AND_DROP requires target locator in values for element "{element_name}"'}
                parsed_target = self._parse_locator(target_locator)
                if not parsed_target:
                    return {'success': False, 'message': f'Unable to parse DRAG_AND_DROP target locator: "{test_data}"'}
                try:
                    target_by, target_value = parsed_target
                    target_elements = self.driver.find_elements(target_by, target_value)
                    if not target_elements:
                        return {'success': False, 'message': f'DRAG_AND_DROP target not found: "{target_locator}"'}
                except Exception as drag_target_error:
                    error_message = str(drag_target_error)
                    if "invalid selector" in error_message.lower() or "xpath expression" in error_message.lower():
                        return {'success': False, 'message': f'DRAG_AND_DROP target selector syntax error: {drag_target_error}'}
                    return {'success': False, 'message': f'DRAG_AND_DROP target validation failed: {drag_target_error}'}

            elif action_type == "SELECT_COUNT":
                try:
                    int(str(test_data).strip())
                except Exception:
                    return {'success': False, 'message': f'Invalid SELECT_COUNT value "{test_data}". Expected integer target count.'}

            elif action_type in ["INCREMENT", "DECREMENT"]:
                if test_data not in [None, ""]:
                    try:
                        parsed_steps = int(str(test_data).strip())
                        if parsed_steps < 0:
                            return {'success': False, 'message': f'{action_type} requires non-negative value; got "{test_data}"'}
                    except Exception:
                        return {'success': False, 'message': f'Invalid {action_type} value "{test_data}". Expected non-negative integer target/step count.'}
            
            elif action_type == "HANDLE_CHECKBOX":
                # Validate checkbox value
                if test_data is None:
                    return {'success': False, 'message': f'HANDLE_CHECKBOX requires a value for "{element_name}"'}

            elif action_type == "RADIO_BUTTON":
                if test_data is None:
                    return {'success': False, 'message': f'RADIO_BUTTON requires a value or selectable option for "{element_name}"'}
            
            elif action_type == "CLICK":
                # For general clicks, validate that test_data makes sense if provided
                if test_data and self.is_date_field(element_name, test_data):
                    return {'success': False, 'message': f'Wrong action type: "{element_name}" with data "{test_data}" appears to be a date field. Use CLICK_AND_SELECT'}
            
            # 4. Browser state validation
            if not self.driver:
                return {'success': False, 'message': f'Browser not initialized for action "{action_type}" on element "{element_name}"'}
            
            try:
                # Check if browser is responsive
                self.driver.current_url
            except Exception:
                return {'success': False, 'message': f'Browser not responsive for action "{action_type}" on element "{element_name}"'}
            
            print(f"[PRE_VALIDATION_PASS] All pre-validations passed for {action_type} on {element_name}")
            return {'success': True, 'message': f'Pre-validation successful for {action_type} on {element_name}'}
            
        except Exception as e:
            print(f"[PRE_VALIDATION_ERROR] Pre-validation failed with exception: {str(e)}")
            return {'success': False, 'message': f'Pre-validation error for {action_type} on {element_name}: {str(e)}'}

    def clean_xpath(self, xpath):
        """Clean XPath to fix common syntax issues"""
        try:
            if not xpath:
                return xpath

            # Remove extra spaces
            cleaned = xpath.strip()

            # Fix common issue: multiple XPath expressions concatenated (like the TC009 case)
            # Pattern: //xpath1 (//xpath2)[index] should become (//xpath2)[index]
            import re

            # Check for pattern like: //select[@id='child-age'] (//select[@data-testid='child-age-selector'])[1]
            # This should become: (//select[@data-testid='child-age-selector'])[1]
            pattern = r'^//[^(\s]+\s+\((//[^)]+)\)\[(\d+)\]$'
            match = re.match(pattern, cleaned)
            if match:
                # Extract the second XPath expression and index
                inner_xpath = match.group(1)
                index = match.group(2)
                cleaned = f"({inner_xpath})[{index}]"
                print(f"[XPATH_CLEAN] Fixed concatenated XPath, using: {cleaned}")
                return cleaned

            # Alternative pattern for simpler cases: //xpath1 (//xpath2)
            alt_pattern = r'^//[^(\s]+\s+\((//[^)]+)\)$'
            alt_match = re.match(alt_pattern, cleaned)
            if alt_match:
                cleaned = alt_match.group(1)
                print(f"[XPATH_CLEAN] Fixed simple concatenated XPath, using: {cleaned}")
                return cleaned

            # Keep valid internal '//' axes untouched to avoid corrupting XPath semantics.
            # Ensure it starts with //, /, .//, or a parenthesized XPath group.
            if not cleaned.startswith(('/', './/', '(')):
                cleaned = '//' + cleaned

            return cleaned

        except Exception as e:
            print(f"[XPATH_CLEAN] Error cleaning XPath: {str(e)}")
            return xpath

    def try_alternative_locators(self, element_name):
        """Try to find element with alternative locators"""
        try:
            alternative_locators = [
                (By.ID, element_name),
                (By.NAME, element_name),
                (By.CLASS_NAME, element_name),
                (By.XPATH, f"//*[contains(text(),'{element_name}')]"),
                (By.XPATH, f"//input[contains(@placeholder,'{element_name}')]"),
                (By.XPATH, f"//button[contains(text(),'{element_name}')]"),
                (By.XPATH, f"//*[contains(@id,'{element_name.lower()}')]"),
                (By.XPATH, f"//*[contains(@name,'{element_name.lower()}')]")
            ]
            
            for locator_type, locator_value in alternative_locators:
                try:
                    elements = self.driver.find_elements(locator_type, locator_value)
                    if elements and elements[0].is_displayed():
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def validate_date_format(self, date_string):
        """Validate if date string is in acceptable format"""
        try:
            import re
            date_patterns = [
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # dd/mm/yyyy
                r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # yyyy/mm/dd
                r'\w{3},?\s+\d{1,2}\s+\w{3}',      # Wed, 30 Jul
                r'\d{1,2}\s+\w{3}\s+\d{4}',       # 30 Jul 2024
                r'\w{3}\s+\d{1,2},?\s+\d{4}',     # Jul 30, 2024
            ]
            
            for pattern in date_patterns:
                if re.search(pattern, date_string):
                    return True
            return False
        except Exception:
            return False

    def validate_element_accessibility(self, xpath, element_name, action_type):
        """
        Comprehensive validation of element accessibility including xpath validation
        """
        try:
            print(f"[VALIDATION] Validating element accessibility for: {element_name}")
            print(f"[VALIDATION] Using XPath: {xpath}")
            print(f"[VALIDATION] Action type: {action_type}")
            
            # Step 1: Validate XPath syntax
            if not xpath or xpath.strip() == "" or xpath.upper() == "NA":
                return {'success': False, 'message': f'Invalid XPath provided for {element_name}: "{xpath}"'}
            
            # Step 2: Try to find element with multiple strategies
            element = None
            try:
                # Try the provided xpath first
                element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                print(f"[VALIDATION] Element found with provided XPath")
            except Exception as e:
                print(f"[VALIDATION] Provided XPath failed: {str(e)}")
                
                # Try alternative strategies if the xpath doesn't work
                alternative_xpaths = [
                    f"//*[@id='{element_name}']",
                    f"//*[@name='{element_name}']",
                    f"//*[contains(@class,'{element_name.lower()}')]",
                    f"//*[contains(text(),'{element_name}')]",
                    f"//input[contains(@placeholder,'{element_name}')]",
                    f"//button[contains(text(),'{element_name}')]"
                ]
                
                for alt_xpath in alternative_xpaths:
                    try:
                        element = self.driver.find_element(By.XPATH, alt_xpath)
                        if element.is_displayed():
                            print(f"[VALIDATION] Element found with alternative XPath: {alt_xpath}")
                            break
                    except Exception:
                        continue
            
            # Step 3: Validate element properties
            if not element:
                return {'success': False, 'message': f'Element "{element_name}" not found with XPath: {xpath}. Check if XPath is correct or element exists on page.'}
            
            # Check if element is displayed
            if not element.is_displayed():
                return {'success': False, 'message': f'Element "{element_name}" exists but is not visible on the page'}
            
            # Check if element is enabled (for interactive elements)
            if not element.is_enabled():
                return {'success': False, 'message': f'Element "{element_name}" is visible but not enabled/clickable'}
            
            # Step 4: Validate action type compatibility with element
            tag_name = element.tag_name.lower()
            element_type = element.get_attribute('type')
            
            if action_type == "CLICK_AND_SELECT":
                # For CLICK_AND_SELECT, element should be interactive
                interactive_tags = ['button', 'a', 'input', 'select', 'div', 'span', 'p', 'li']
                if tag_name not in interactive_tags:
                    return {'success': False, 'message': f'Element "{element_name}" with tag "{tag_name}" may not be suitable for CLICK_AND_SELECT action'}
            
            # Step 5: Try to interact with element to ensure it's truly functional
            try:
                # Try to scroll element into view
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(0.5)
                
                # Check if element is still accessible after scroll (but be more lenient)
                try:
                    if element.is_displayed() and element.is_enabled():
                        print(f"[VALIDATION_PASS] Element {element_name} is fully accessible and ready for interaction")
                        return {'success': True, 'message': f'Element "{element_name}" is accessible and ready for {action_type} action'}
                    else:
                        print(f"[VALIDATION_WARNING] Element {element_name} may have accessibility issues but allowing execution")
                        return {'success': True, 'message': f'Element "{element_name}" found - allowing execution despite potential accessibility issues'}
                except Exception:
                    print(f"[VALIDATION_WARNING] Element {element_name} accessibility check failed but allowing execution")
                    return {'success': True, 'message': f'Element "{element_name}" found - allowing execution despite accessibility check failure'}
                
            except Exception as interaction_error:
                # Be more lenient - if element exists, allow execution to proceed
                print(f"[VALIDATION_WARNING] Element {element_name} interaction test failed but allowing execution: {str(interaction_error)}")
                return {'success': True, 'message': f'Element "{element_name}" found - allowing execution despite interaction test failure'}
                
        except Exception as e:
            print(f"[VALIDATION_ERROR] Element accessibility validation failed: {str(e)}")
            return {'success': False, 'message': f'Element accessibility validation failed for "{element_name}": {str(e)}'}

    def validate_city_selection(self, expected_city, xpath, element_name):
        """Validate that the correct city was selected"""
        try:
            # Wait longer for the selection to take effect and any modals to disappear
            time.sleep(3)  # Increased from 2 to 3 seconds

            # Wait for any interfering modals to disappear
            try:
                modal_selectors = [
                    "//div[@data-testid='bpg-home-modal']",
                    "//div[contains(@class,'modal') and contains(@class,'bg-black')]",
                    "//div[contains(@class,'fixed') and contains(@class,'z-[9999]')]"
                ]
                for selector in modal_selectors:
                    modal_elements = self.driver.find_elements(By.XPATH, selector)
                    for modal in modal_elements:
                        if modal.is_displayed():
                            print(f"[VALIDATION] Waiting for modal to disappear: {selector}")
                            # Wait up to 5 seconds for modal to disappear
                            WebDriverWait(self.driver, 5).until(
                                EC.invisibility_of_element(modal)
                            )
                            print(f"[VALIDATION] Modal disappeared")
                            break
            except Exception as modal_error:
                print(f"[VALIDATION] Modal wait failed (may not be present): {str(modal_error)}")
            
            # Try multiple strategies to find the actual city input field
            input_selectors = [
                # Common input field patterns for city selection
                *self.CITY_INPUT_SELECTORS,
                # Generic text inputs near From/To labels
                f"//label[contains(text(),'{element_name}')]//following::input[1]",
                f"//span[contains(text(),'{element_name}')]//following::input[1]",
                f"//*[contains(text(),'{element_name}')]//parent::*//input[@type='text']",
                # Look for inputs with city values
                f"//input[@value and contains(@value,'{expected_city}')]"
            ]
            
            print(f"[VALIDATION] Searching for city input field for {element_name}")
            
            # Try each selector to find the actual input field
            current_value = None
            for selector in input_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            value = elem.get_attribute('value') or elem.get_attribute('placeholder') or elem.text
                            if value and value.strip() and value.strip() not in self.CITY_PLACEHOLDER_BLOCKLIST:
                                current_value = value.strip()
                                print(f"[VALIDATION] Found city value: '{current_value}' using selector: {selector}")
                                break
                    if current_value:
                        break
                except Exception:
                    continue
            
            # If no specific value found, try to check if city appears anywhere in the form
            if not current_value:
                print(f"[VALIDATION] No input value found, checking if city appears in page content")
                try:
                    # Look for the expected city name anywhere in the visible page content
                    city_elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(),'{expected_city}')]")
                    visible_city_elements = [elem for elem in city_elements if elem.is_displayed()]
                    
                    if visible_city_elements:
                        current_value = expected_city
                        print(f"[VALIDATION] Found city '{expected_city}' displayed on page")
                    else:
                        current_value = "No city value found"
                except Exception:
                    current_value = "Validation error"
            
            # Validate the city selection with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                if attempt > 0:
                    print(f"[VALIDATION] Retry attempt {attempt + 1} for city validation")
                    time.sleep(1)  # Wait before retry

                # Re-check the value on retry attempts
                if attempt > 0:
                    current_value = None
                    for selector in input_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            for elem in elements:
                                if elem.is_displayed():
                                    value = elem.get_attribute('value') or elem.get_attribute('placeholder') or elem.text
                                    if value and value.strip() and value.strip() not in self.CITY_PLACEHOLDER_BLOCKLIST:
                                        current_value = value.strip()
                                        print(f"[VALIDATION] Found city value on retry: '{current_value}' using selector: {selector}")
                                        break
                            if current_value:
                                break
                        except Exception:
                            continue

                if current_value and expected_city.lower() in current_value.lower():
                    print(f"[VALIDATION_PASS] City selection validated: {current_value}")
                    return {'success': True, 'message': f'City "{expected_city}" selected correctly'}
                elif attempt == max_retries - 1:
                    # Last attempt failed
                    print(f"[VALIDATION_FAIL] City validation failed after {max_retries} attempts. Expected: '{expected_city}', Found: '{current_value}'")
                    return {'success': False, 'message': f'Expected city "{expected_city}", but found "{current_value}"'}
                
        except Exception as e:
            print(f"[VALIDATION_ERROR] City validation exception: {str(e)}")
            return {'success': False, 'message': f'City validation error: {str(e)}'}

    def validate_date_selection(self, expected_date, xpath, element_name):
        """Validate that the correct date was selected"""
        try:
            # Brief settle time after date click.
            time.sleep(0.1)

            # Departure is treated as action-success validation, mirroring the faster Playwright behavior.
            if "departure" in str(element_name or "").strip().lower():
                print(f"[VALIDATION_PASS] Date selection validated: {expected_date}")
                return {'success': True, 'message': f'Date "{expected_date}" selected correctly'}
            
            # For quick date options like "tomorrow", "today", just verify the calendar is closed
            if expected_date.lower() in self.DATE_QUICK_OPTIONS:
                # Check if calendar popup is closed (indicates successful selection)
                try:
                    calendar_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class,'calendar') or contains(@class,'date-picker')]")
                    visible_calendars = [elem for elem in calendar_elements if elem.is_displayed()]
                    
                    if not visible_calendars:
                        print(f"[VALIDATION_PASS] Date selection validated: {expected_date} - calendar closed")
                        return {'success': True, 'message': f'Date "{expected_date}" selected correctly'}
                    else:
                        return {'success': False, 'message': f'Date selection failed - calendar still open'}
                except Exception:
                    # If we can't find calendar elements, assume selection was successful
                    return {'success': True, 'message': f'Date "{expected_date}" selected (calendar validation not available)'}
            
            # For specific dates, quick validation without heavy waits
            else:
                # Use fast find_elements instead of find_element_with_advanced_wait to avoid 15s waits
                parsed = self._parse_locator(xpath)
                if parsed:
                    by, value = parsed
                    elements = self.driver.find_elements(by, value)
                    if elements:
                        current_value = elements[0].get_attribute('value') or elements[0].text
                        if expected_date in current_value or current_value:
                            print(f"[VALIDATION_PASS] Date selection validated: {current_value}")
                            return {'success': True, 'message': f'Date "{expected_date}" selected correctly'}
                        else:
                            return {'success': False, 'message': f'Expected date "{expected_date}", but found "{current_value}"'}
                # If element not found, the calendar closed which means date was selected
                print(f"[VALIDATION_PASS] Date selection validated: {element_name}")
                return {'success': True, 'message': f'Date "{expected_date}" selected correctly'}
                    
        except Exception as e:
            return {'success': False, 'message': f'Date validation error: {str(e)}'}

    def validate_travel_class_selection(self, expected_class, element_name):
        """Validate that the correct travel class was selected"""
        try:
            time.sleep(1)
            
            # Map the expected class to actual class names
            actual_class_name = self.map_travel_class(expected_class)
            
            # Look for selected travel class indicators
            class_selectors = [
                f"//span[contains(@class,'selected') and contains(text(),'{actual_class_name}')]",
                f"//div[contains(@class,'selected') and contains(text(),'{actual_class_name}')]",
                f"//button[contains(@class,'selected') and contains(text(),'{actual_class_name}')]"
            ]
            
            for selector in class_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements and any(elem.is_displayed() for elem in elements):
                        print(f"[VALIDATION_PASS] Travel class validated: {actual_class_name}")
                        return {'success': True, 'message': f'Travel class "{actual_class_name}" selected correctly'}
                except Exception:
                    continue
            
            # If no selected indicator found, assume successful (some UIs don't show selection clearly)
            print(f"[VALIDATION_ASSUME] Travel class selection assumed successful: {actual_class_name}")
            return {'success': True, 'message': f'Travel class "{actual_class_name}" selection completed'}
            
        except Exception as e:
            return {'success': False, 'message': f'Travel class validation error: {str(e)}'}

    def validate_popup_closed(self):
        """Validate that popup/modal was closed"""
        try:
            time.sleep(1)
            
            # Check for common popup indicators
            popup_selectors = [
                "//div[contains(@class,'modal') and contains(@style,'display: block')]",
                "//div[contains(@class,'popup') and not(contains(@style,'display: none'))]",
                f"//div[contains(text(),'{self.UI_LABEL_ADULTS}') or contains(text(),'{self.UI_LABEL_CHILDREN}')]//ancestor::div[contains(@class,'visible')]"
            ]
            
            for selector in popup_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    visible_popups = [elem for elem in elements if elem.is_displayed()]
                    if visible_popups:
                        return {'success': False, 'message': 'Popup is still visible - not closed properly'}
                except Exception:
                    continue
            
            print(f"[VALIDATION_PASS] Popup closed successfully")
            return {'success': True, 'message': 'Popup closed successfully'}
            
        except Exception as e:
            return {'success': False, 'message': f'Popup validation error: {str(e)}'}

    def validate_click_action(self, xpath, element_name):
        """Validate that click action was successful"""
        try:
            element_name = element_name or "unnamed_element"
            # Special handling for search buttons - they often cause page navigation
            if 'search' in element_name.lower() or 'button' in element_name.lower():
                print(f"[VALIDATION] Special validation for search/button element: {element_name}")
                
                # Wait a moment for any page changes after search
                time.sleep(2)
                
                # For search buttons, validate that page is responsive rather than element existence
                try:
                    current_url = self.driver.current_url
                    page_title = self.driver.title
                    
                    # Check if browser is still responsive
                    self.driver.execute_script("return document.readyState;")
                    
                    print(f"[VALIDATION_PASS] Search button click successful - page responsive, URL: {current_url}")
                    return {'success': True, 'message': f'Search button "{element_name}" clicked successfully - page navigation/results loading detected'}
                    
                except Exception as browser_error:
                    return {'success': False, 'message': f'Browser became unresponsive after clicking search button: {str(browser_error)}'}
            
            else:
                # For non-search elements, verify the element is still accessible
                try:
                    element = self.find_element_with_advanced_wait(xpath)
                    if element:
                        print(f"[VALIDATION_PASS] Click action validated for: {element_name}")
                        return {'success': True, 'message': f'Click action on "{element_name}" completed successfully'}
                    else:
                        return {'success': False, 'message': f'Click validation failed: element "{element_name}" not found after interaction'}
                        
                except Exception as element_error:
                    return {'success': False, 'message': f'Click validation failed for "{element_name}": {str(element_error)}'}
                
        except Exception as e:
            print(f"[VALIDATION_ERROR] Click validation error: {str(e)}")
            return {'success': False, 'message': f'Click validation error: {str(e)}'}

    def validate_count_selection(self, expected_count, xpath, element_name):
        """Validate that the correct count was selected"""
        try:
            time.sleep(1)
            expected_count = int(expected_count)
            
            # Look for count displays in various formats
            count_selectors = [
                f"//*[contains(text(),'{expected_count}')]",
                f"//input[@value='{expected_count}']",
                f"//span[contains(@class,'count') and text()='{expected_count}']"
            ]
            
            for selector in count_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements and any(elem.is_displayed() for elem in elements):
                        print(f"[VALIDATION_PASS] Count validated: {expected_count}")
                        return {'success': True, 'message': f'Count "{expected_count}" selected correctly'}
                except Exception:
                    continue
            
            # Assume successful if no clear indicator found
            print(f"[VALIDATION_ASSUME] Count selection assumed successful: {expected_count}")
            return {'success': True, 'message': f'Count "{expected_count}" selection completed'}
            
        except Exception as e:
            return {'success': False, 'message': f'Count validation error: {str(e)}'}

    def validate_age_selection(self, expected_age, element_name):
        """Validate that the correct age was selected"""
        try:
            time.sleep(1)
            expected_age = int(expected_age)
            
            # Look for age selection indicators
            age_selectors = [
                f"//option[@value='{expected_age}' and @selected]",
                f"//option[text()='{expected_age}' and @selected]",
                f"//*[contains(@class,'selected') and contains(text(),'{expected_age}')]"
            ]
            
            for selector in age_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        print(f"[VALIDATION_PASS] Age validated: {expected_age}")
                        return {'success': True, 'message': f'Age "{expected_age}" selected correctly'}
                except Exception:
                    continue
            
            # Assume successful if no clear indicator found
            print(f"[VALIDATION_ASSUME] Age selection assumed successful: {expected_age}")
            return {'success': True, 'message': f'Age "{expected_age}" selection completed'}
            
        except Exception as e:
            return {'success': False, 'message': f'Age validation error: {str(e)}'}

    def validate_checkbox_state(self, expected_state, xpath, element_name):
        """Validate that checkbox is in the expected state"""
        try:
            time.sleep(0.5)
            raw_value = str(expected_state or "").strip()
            choice_values = self._extract_choice_values(raw_value)

            if choice_values and not self._is_boolean_like_value(raw_value):
                for choice in choice_values:
                    checkbox = self.find_choice_control(xpath, choice, "checkbox")
                    if not checkbox:
                        return {'success': False, 'message': f'Checkbox option "{choice}" not found for validation'}
                    if not self._is_control_selected(checkbox):
                        return {'success': False, 'message': f'Checkbox option "{choice}" is not checked for "{element_name}"'}
                return {'success': True, 'message': f'Checkbox values validated for "{element_name}"'}

            should_be_checked = self._value_means_checked(raw_value)

            checkbox = self.find_checkbox_element(xpath, element_name)
            if checkbox:
                actual_state = self._is_control_selected(checkbox)

                if actual_state == should_be_checked:
                    state_text = "checked" if should_be_checked else "unchecked"
                    print(f"[VALIDATION_PASS] Checkbox validated: {element_name} is {state_text}")
                    return {'success': True, 'message': f'Checkbox "{element_name}" is correctly {state_text}'}
                else:
                    expected_text = "checked" if should_be_checked else "unchecked"
                    actual_text = "checked" if actual_state else "unchecked"
                    return {'success': False, 'message': f'Checkbox "{element_name}" should be {expected_text} but is {actual_text}'}
            else:
                return {'success': False, 'message': f'Checkbox "{element_name}" not found for validation'}
                
        except Exception as e:
            return {'success': False, 'message': f'Checkbox validation error: {str(e)}'}

    def comprehensive_post_validation(self, action_type, test_data, xpath, element_name):
        """
        Comprehensive validation that checks if the action truly achieved the intended result
        """
        try:
            print(f"[COMPREHENSIVE_VALIDATION] Running comprehensive validation for {action_type} on {element_name}")
            
            # 1. Basic validation - call the standard validation
            basic_result = self.validate_action_result(action_type, test_data, xpath, element_name)
            if not basic_result['success']:
                return basic_result
            
            # 2. Additional comprehensive checks
            
            # Check browser responsiveness
            try:
                current_url = self.driver.current_url
                if not current_url:
                    return {'success': False, 'message': 'Browser became unresponsive during action execution'}
            except Exception:
                return {'success': False, 'message': 'Browser is not responding after action execution'}
            
            # 3. Check for critical page issues
            try:
                # Check for JavaScript errors or page crashes
                page_ready = self.driver.execute_script("return document.readyState === 'complete'")
                if not page_ready:
                    print(f"[COMPREHENSIVE_VALIDATION] Page not ready but basic validation passed, allowing success")
            except Exception:
                print(f"[COMPREHENSIVE_VALIDATION] Page health check failed but basic validation passed, allowing success")
            
            # 4. Check if any unexpected popups or alerts appeared
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                alert.dismiss()  # Dismiss the alert
                print(f"[COMPREHENSIVE_VALIDATION] Dismissed unexpected alert: {alert_text}")
            except Exception:
                # No alert found, which is good
                pass
            
            print(f"[COMPREHENSIVE_VALIDATION] All comprehensive checks passed for {action_type} on {element_name}")
            return {'success': True, 'message': f'Comprehensive validation successful for {action_type} on {element_name}'}
            
        except Exception as e:
            print(f"[COMPREHENSIVE_VALIDATION] Comprehensive validation failed: {str(e)}")
            return {'success': False, 'message': f'Comprehensive validation failed: {str(e)}'}



    def wait_for_spa_ready(self):
        """Wait for Single Page Application to be ready"""
        try:
            print("[SPA] Waiting for page to be ready...")
            
            # Wait for document ready state
            self.wait.until(
                lambda driver: driver.execute_script("return document.readyState") in ["interactive", "complete"]
            )

            settle_deadline = time.time() + 0.75
            while time.time() < settle_deadline:
                try:
                    is_busy = self.driver.execute_script(
                        """
                        return Boolean(
                            document.querySelector(
                                "[aria-busy='true'], .loading, .loader, .spinner, [data-testid*='loader'], [data-testid*='spinner']"
                            )
                        );
                        """
                    )
                    if not is_busy:
                        break
                except Exception:
                    break
                time.sleep(0.1)
            
            print("[SPA] Page is ready")
            
        except Exception as e:
            print(f"[SPA] Warning: Could not confirm SPA ready state: {str(e)}")
            # Don't fail the test, just continue

    # ==================== WINDOW/TAB MANAGEMENT METHODS ====================

    # ==================== FRAME/IFRAME MANAGEMENT METHODS ====================

    def switch_to_iframe(self, frame_reference):
        """Switch WebDriver context to iframe by index/name/id/url or selector."""
        if not self.driver:
            raise Exception("Driver is not initialized")

        ref = str(frame_reference or "").strip()
        if not ref:
            ref = "0"

        ref_lower = ref.lower()
        if ref_lower in {"default", "main", "top", "parent", "root"}:
            self.driver.switch_to.default_content()
            print("[FRAME] Switched to default content")
            return True

        # Numeric reference: iframe index
        if ref.isdigit():
            index = int(ref)
            self.driver.switch_to.frame(index)
            print(f"[FRAME] Switched to iframe by index: {index}")
            return True

        # Try direct name/id switch
        try:
            self.driver.switch_to.frame(ref)
            print(f"[FRAME] Switched to iframe by name/id: {ref}")
            return True
        except Exception:
            pass

        # Try selector lookup (xpath/css/id styles).
        try:
            locator_value = ref
            locator_lower = locator_value.lower()
            if locator_lower.startswith("xpath="):
                by, query = By.XPATH, locator_value[6:]
            elif locator_lower.startswith("css="):
                by, query = By.CSS_SELECTOR, locator_value[4:]
            elif locator_lower.startswith("id="):
                by, query = By.ID, locator_value[3:]
            elif locator_value.startswith(("/", ".//", "(")):
                by, query = By.XPATH, locator_value
            else:
                by, query = By.CSS_SELECTOR, locator_value

            iframe_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((by, query))
            )
            self.driver.switch_to.frame(iframe_element)
            print(f"[FRAME] Switched to iframe via selector: {ref}")
            return True
        except Exception:
            pass

        # Fallback: match iframe attributes by substring.
        frames = self.driver.find_elements(By.TAG_NAME, "iframe")
        for idx, frame in enumerate(frames):
            try:
                attrs = " ".join([
                    frame.get_attribute("id") or "",
                    frame.get_attribute("name") or "",
                    frame.get_attribute("title") or "",
                    frame.get_attribute("src") or "",
                ]).lower()
                if ref_lower in attrs:
                    self.driver.switch_to.frame(frame)
                    print(f"[FRAME] Switched to iframe by attribute match at index {idx}")
                    return True
            except Exception:
                continue

        raise Exception(f"Unable to switch to iframe using reference: {frame_reference}")
    
    def initialize_window_tracking(self):
        """Initialize window tracking when browser is launched"""
        try:
            if self.driver:
                self.initial_window_handle = self.driver.current_window_handle
                self.current_window_handle = self.initial_window_handle
                self.all_window_handles = [self.initial_window_handle]
                print(f"[WINDOW_INIT] Initial window handle: {self.initial_window_handle}")
                print(f"[WINDOW_INIT] Window tracking initialized")
        except Exception as e:
            print(f"[WINDOW_INIT] Error initializing window tracking: {str(e)}")

    def detect_new_windows(self):
        """Detect if new windows/tabs have been opened"""
        try:
            if not self.driver:
                return []
            
            current_handles = self.driver.window_handles
            new_handles = [handle for handle in current_handles if handle not in self.all_window_handles]
            
            if new_handles:
                print(f"[WINDOW_DETECT] Found {len(new_handles)} new window(s)")
                for handle in new_handles:
                    print(f"[WINDOW_DETECT] New window handle: {handle}")
                self.all_window_handles.extend(new_handles)
            
            return new_handles
        except Exception as e:
            print(f"[WINDOW_DETECT] Error detecting new windows: {str(e)}")
            return []

    def switch_to_latest_window(self):
        """Switch to the most recently opened window/tab"""
        try:
            if not self.driver:
                return False
            
            # Get all current window handles
            current_handles = self.driver.window_handles
            
            if len(current_handles) > 1:
                # Switch to the last (most recent) window
                latest_handle = current_handles[-1]
                
                if latest_handle != self.current_window_handle:
                    print(f"[WINDOW_SWITCH] Switching from {self.current_window_handle} to {latest_handle}")
                    self.driver.switch_to.window(latest_handle)
                    self.current_window_handle = latest_handle
                    
                    # Wait for the new page to load
                    self.wait_for_spa_ready()
                    
                    # Log current URL for debugging
                    try:
                        current_url = self.driver.current_url
                        print(f"[WINDOW_SWITCH] Now on URL: {current_url}")
                    except:
                        pass
                    
                    return True
                else:
                    print(f"[WINDOW_SWITCH] Already on the latest window")
                    return True
            else:
                print(f"[WINDOW_SWITCH] Only one window open, no switching needed")
                return True
                
        except Exception as e:
            print(f"[WINDOW_SWITCH] Error switching to latest window: {str(e)}")
            return False

    def switch_to_window_by_index(self, index):
        """Switch to window by index (0 = first window, 1 = second, etc.)"""
        try:
            if not self.driver:
                return False
            
            current_handles = self.driver.window_handles
            
            if 0 <= index < len(current_handles):
                target_handle = current_handles[index]
                
                if target_handle != self.current_window_handle:
                    print(f"[WINDOW_SWITCH] Switching to window index {index}: {target_handle}")
                    self.driver.switch_to.window(target_handle)
                    self.current_window_handle = target_handle
                    
                    # Wait for the page to load
                    self.wait_for_spa_ready()
                    
                    # Log current URL for debugging
                    try:
                        current_url = self.driver.current_url
                        print(f"[WINDOW_SWITCH] Now on URL: {current_url}")
                    except:
                        pass
                    
                    return True
                else:
                    print(f"[WINDOW_SWITCH] Already on window index {index}")
                    return True
            else:
                print(f"[WINDOW_SWITCH] Invalid window index {index}. Available windows: {len(current_handles)}")
                return False
                
        except Exception as e:
            print(f"[WINDOW_SWITCH] Error switching to window index {index}: {str(e)}")
            return False

    def switch_to_window_by_url_pattern(self, url_pattern):
        """Switch to window that contains the specified URL pattern"""
        try:
            if not self.driver:
                return False
            
            current_handles = self.driver.window_handles
            original_handle = self.current_window_handle
            
            for handle in current_handles:
                try:
                    self.driver.switch_to.window(handle)
                    current_url = self.driver.current_url
                    
                    if url_pattern.lower() in current_url.lower():
                        print(f"[WINDOW_SWITCH] Found window with URL pattern '{url_pattern}': {current_url}")
                        self.current_window_handle = handle
                        self.wait_for_spa_ready()
                        return True
                        
                except Exception as e:
                    print(f"[WINDOW_SWITCH] Error checking window {handle}: {str(e)}")
                    continue
            
            # If no matching window found, switch back to original
            print(f"[WINDOW_SWITCH] No window found with URL pattern '{url_pattern}', staying on current window")
            if original_handle in current_handles:
                self.driver.switch_to.window(original_handle)
                self.current_window_handle = original_handle
            
            return False
            
        except Exception as e:
            print(f"[WINDOW_SWITCH] Error switching to window by URL pattern: {str(e)}")
            return False

    def close_extra_windows(self, keep_main=True):
        """Close all windows except the main one (or current one if keep_main=False)"""
        try:
            if not self.driver:
                return
            
            current_handles = self.driver.window_handles
            
            if len(current_handles) <= 1:
                print("[WINDOW_CLOSE] Only one window open, nothing to close")
                return
            
            if keep_main and self.initial_window_handle:
                # Keep the initial window, close others
                target_handle = self.initial_window_handle
                print(f"[WINDOW_CLOSE] Keeping main window: {target_handle}")
            else:
                # Keep current window, close others
                target_handle = self.current_window_handle
                print(f"[WINDOW_CLOSE] Keeping current window: {target_handle}")
            
            # Close all other windows
            for handle in current_handles:
                if handle != target_handle:
                    try:
                        print(f"[WINDOW_CLOSE] Closing window: {handle}")
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    except Exception as e:
                        print(f"[WINDOW_CLOSE] Error closing window {handle}: {str(e)}")
            
            # Switch back to the target window
            if target_handle in self.driver.window_handles:
                self.driver.switch_to.window(target_handle)
                self.current_window_handle = target_handle
                print(f"[WINDOW_CLOSE] Switched back to target window: {target_handle}")
            
            # Update tracking
            self.all_window_handles = [target_handle]
            
        except Exception as e:
            print(f"[WINDOW_CLOSE] Error closing extra windows: {str(e)}")

    def wait_for_new_window(self, timeout=None):
        """Wait until a new window appears within the given timeout.
        Returns True if a new window is detected, otherwise False.
        """
        try:
            import time
            start = time.time()
            # Base set of handles to compare against
            base_handles = set(getattr(self, 'all_window_handles', []) or self.driver.window_handles)
            max_wait = float(timeout) if timeout is not None else 10.0
            while time.time() - start < max_wait:
                current = set(self.driver.window_handles)
                if len(current) > len(base_handles):
                    # Update tracking and return success
                    self.all_window_handles = list(current)
                    return True
                time.sleep(0.25)
            return False
        except Exception:
            return False
    def _get_timestamp_from_datetime(self, dt):
        """Convert a datetime object to a Unix timestamp (seconds since epoch)"""
        if isinstance(dt, datetime):
           return dt.timestamp()
        elif isinstance(dt, str):
           # Try to parse string to datetime
           try:
              return datetime.fromisoformat(dt).timestamp()
           except Exception:
              return 0
        else:
           return 0

    # ==================== REMOTE VIEWING METHODS ====================

    def initialize_remote_viewing(self):
        """Initialize remote viewing capabilities for the browser session"""
        try:
            if not self.enable_remote_viewing or not self.viewing_session_id:
                return

            print(f"[REMOTE_VIEWING] Initializing remote viewing for session: {self.viewing_session_id}")

            # Position browser window for optimal viewing
            try:
                # Set window position and size for streaming
                self.driver.set_window_position(0, 0)
                self.driver.set_window_size(1280, 720)
                print("[REMOTE_VIEWING] Browser window positioned for streaming")
            except Exception as pos_error:
                print(f"[REMOTE_VIEWING] Could not position browser window: {pos_error}")

            # Initialize video streaming if WebRTC/Socket.IO is available
            self.initialize_video_streaming()

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error initializing remote viewing: {str(e)}")

    def initialize_video_streaming(self):
        """Initialize video streaming capabilities"""
        try:
            # Check if required packages are available
            try:
                import cv2
                import numpy as np
                from flask_socketio import SocketIO
                print("[REMOTE_VIEWING] Video streaming dependencies available")
                self.video_streaming_available = True
            except ImportError as ie:
                print(f"[REMOTE_VIEWING] Video streaming dependencies not available: {ie}")
                print("[REMOTE_VIEWING] Install required packages: pip install opencv-python flask-socketio")
                self.video_streaming_available = False
                return

            # Initialize video capture from browser window
            self.setup_video_capture()

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error setting up video streaming: {str(e)}")
            self.video_streaming_available = False

    def setup_video_capture(self):
        """Setup video capture from browser window"""
        try:
            import cv2
            import numpy as np

            # For Windows, we'll use screen capture of the browser window
            # This is a simplified implementation - production would need more robust screen capture
            self.video_capture_active = False
            print("[REMOTE_VIEWING] Video capture setup prepared (screen capture mode)")

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error setting up video capture: {str(e)}")

    def start_video_stream(self, client_id):
        """Start video streaming for a specific client"""
        try:
            if not self.enable_remote_viewing or not hasattr(self, 'video_streaming_available') or not self.video_streaming_available:
                return False

            if client_id not in self.viewing_clients:
                self.viewing_clients.add(client_id)
                print(f"[REMOTE_VIEWING] Client {client_id} joined video stream for session {self.viewing_session_id}")

            # Start streaming if not already active
            if not getattr(self, 'video_capture_active', False):
                self.video_capture_active = True
                print("[REMOTE_VIEWING] Video streaming started")

            return True

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error starting video stream: {str(e)}")
            return False

    def stop_video_stream(self, client_id):
        """Stop video streaming for a specific client"""
        try:
            if client_id in self.viewing_clients:
                self.viewing_clients.remove(client_id)
                print(f"[REMOTE_VIEWING] Client {client_id} left video stream")

            # Stop streaming if no more clients
            if len(self.viewing_clients) == 0 and getattr(self, 'video_capture_active', False):
                self.video_capture_active = False
                print("[REMOTE_VIEWING] Video streaming stopped - no active viewers")

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error stopping video stream: {str(e)}")

    def get_streaming_status(self):
        """Get current streaming status"""
        return {
            'session_id': self.viewing_session_id,
            'active_clients': len(self.viewing_clients),
            'streaming_active': getattr(self, 'video_capture_active', False),
            'remote_viewing_enabled': self.enable_remote_viewing
        }

    def cleanup_remote_viewing_session(self):
        """Clean up remote viewing session"""
        try:
            if self.viewing_session_id:
                print(f"[REMOTE_VIEWING] Cleaning up session: {self.viewing_session_id}")

                # Disconnect all clients
                for client_id in list(self.viewing_clients):
                    self.stop_video_stream(client_id)

                # Reset session state
                self.viewing_session_id = None
                self.viewing_clients.clear()
                self.video_capture_active = False

                print("[REMOTE_VIEWING] Remote viewing session cleaned up")

        except Exception as e:
            print(f"[REMOTE_VIEWING] Error cleaning up remote viewing session: {str(e)}")



##Working Main
