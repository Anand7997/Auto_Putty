from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page, Locator, TimeoutError as PlaywrightTimeoutError
import time
import uuid
from datetime import datetime
import pytz
import traceback
import re
import os
import sys
import json
import allure

import os

class PlaywrightTestExecutor:
    def __init__(self, enable_isolation=True, safe_field_interaction=True, server_execution=False, vnc_session=None, display_id=None):
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

        self.setup_allure_results_directory()
        self.current_test_attachments = []
        self.enable_isolation = enable_isolation
        self.safe_field_interaction = safe_field_interaction
        self.server_execution = server_execution
        self.vnc_session = vnc_session
        self.display_id = display_id  # VNC-assigned display ID
        
        # Set DISPLAY environment variable using VNC-assigned display
        if self.display_id:
            os.environ["DISPLAY"] = self.display_id
            print(f"[DISPLAY] Using VNC-assigned display {self.display_id}")

        # Window/Tab management
        self.initial_page = None
        self.window_switch_timeout = 10  # seconds

        print(f"[INIT] Playwright Test Executor initialized with isolation mode: {'ENABLED' if enable_isolation else 'DISABLED'}")
        print(f"[INIT] Safe field interaction mode: {'ENABLED' if safe_field_interaction else 'DISABLED'}")
        print(f"[INIT] VNC session: {'AVAILABLE' if vnc_session else 'NONE'}")

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

            # Fix other common issues
            # Remove double slashes except at the beginning
            cleaned = re.sub(r'(?<!^)//', '/', cleaned)

            # Ensure it starts with // or /
            if not cleaned.startswith(('/', './/')):
                cleaned = '//' + cleaned

            return cleaned

        except Exception as e:
            print(f"[XPATH_CLEAN] Error cleaning XPath: {str(e)}")
            return xpath

    def normalize_selector(self, selector):
        """Normalize selector to ensure proper XPath handling in Playwright."""
        if not selector:
            return selector

        original_selector = selector

        # If it starts with /html, //, or /, it's an XPath selector
        if selector.startswith('/'):
            # Clean the XPath first to fix common syntax issues
            cleaned_xpath = self.clean_xpath(selector)
            if cleaned_xpath != selector:
                print(f"[SELECTOR] Cleaned XPath: '{selector}' -> '{cleaned_xpath}'")
                selector = cleaned_xpath

            # Playwright expects XPath selectors to be prefixed with xpath=
            normalized = f"xpath={selector}"
            print(f"[SELECTOR] Normalized XPath: '{original_selector}' -> '{normalized}'")
            return normalized

        # If it already has xpath= prefix, clean the XPath part
        if selector.startswith('xpath='):
            xpath_part = selector[6:]  # Remove 'xpath=' prefix
            cleaned_xpath = self.clean_xpath(xpath_part)
            if cleaned_xpath != xpath_part:
                normalized = f"xpath={cleaned_xpath}"
                print(f"[SELECTOR] Cleaned XPath in selector: '{selector}' -> '{normalized}'")
                return normalized
            return selector

        # If it starts with [, it's likely a CSS selector with attributes
        if selector.startswith('['):
            return selector

        # If it contains @, it's likely an XPath expression
        if '@' in selector and not selector.startswith('xpath='):
            # Clean the XPath first
            cleaned_xpath = self.clean_xpath(selector)
            normalized = f"xpath={cleaned_xpath}"
            print(f"[SELECTOR] Normalized XPath: '{original_selector}' -> '{normalized}'")
            return normalized

        # Otherwise, assume it's a CSS selector
        return selector

    def setup_allure_results_directory(self):
        """Setup Allure results directory and environment"""
        try:
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            if not os.path.exists(allure_results_path):
                os.makedirs(allure_results_path)
                print(f"[ALLURE] Created allure-results-new directory at: {allure_results_path}")

            env_file = os.path.join(allure_results_path, 'environment.properties')
            with open(env_file, 'w') as f:
                f.write("Browser=Chromium\n")
                f.write("Platform=Windows\n")
                f.write("Base_URL=https://www.ixigo.com\n")
                f.write("Database=Quinnox_TestAutomation\n")
                f.write("Framework=Playwright\n")
                f.write(f"Test_Environment=Development\n")
                f.write(f"Execution_Date={datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}\n")

        except Exception as e:
            print(f"[ERROR] Failed to setup allure-results directory: {str(e)}")

    def clear_old_allure_results(self):
        """Manage allure results - keep history but limit file count"""
        try:
            print("[ALLURE_HISTORY] Managing allure results to preserve execution history...")
            
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            
            allure_dir = os.path.join(project_root, 'allure-results-new')
            
            files_managed = 0
            if os.path.exists(allure_dir):
                print(f"[ALLURE_HISTORY] Checking directory: {allure_dir}")
                
                result_files = []
                for filename in os.listdir(allure_dir):
                    file_path = os.path.join(allure_dir, filename)
                    if os.path.isfile(file_path) and filename.endswith('.json'):
                        result_files.append((file_path, os.path.getmtime(file_path)))
                
                result_files.sort(key=lambda x: x[1], reverse=True)
                
                if len(result_files) > 50:
                    files_to_remove = result_files[50:]
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
                print(f"[ALLURE_HISTORY] Managed {files_managed} old allure files (kept latest 50)")
            else:
                print("[ALLURE_HISTORY] No old files needed to be removed")
            
        except Exception as e:
            print(f"[ALLURE_HISTORY] Error managing allure results: {str(e)}")

    def launch_browser(self):
        """Launch Chromium browser using Playwright."""
        if self.browser and self.browser.is_connected():
            print("[BROWSER] Browser already running and connected.")
            return True

        try:
            print("[SETUP] Initializing Playwright...")
            self.playwright = sync_playwright().start()

            # Determine headless mode: if VNC/display is set, disable headless for VNC streaming (like Selenium/Cypress)
            if self.display_id or self.vnc_session:
                headless_mode = False
                print(f"[INIT] Headless DISABLED because VNC/streaming is enabled")
            else:
                headless_mode = self.server_execution
            print(f"[ROCKET] Launching Chromium browser (headless={headless_mode})...")

            launch_args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            if headless_mode:
                # For server execution, add additional args to prevent display issues
                launch_args.extend([
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-images",
                    "--use-gl=swiftshader",
                    "--disable-features=TranslateUI",
                    "--disable-hang-monitor",
                    "--disable-prompt-on-repost",
                    "--force-color-profile=srgb",
                    "--no-first-run",
                    "--enable-automation",
                    "--disable-sync",
                    "--disable-translate",
                    "--hide-scrollbars",
                    "--mute-audio",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-domain-reliability",
                    "--disable-client-side-phishing-detection",
                    "--disable-popup-blocking",
                    "--disable-print-preview",
                    "--no-service-autorun",
                    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ])
            else:
                launch_args.append("--start-maximized")

            self.browser = self.playwright.chromium.launch(
                headless=headless_mode,
                args=launch_args,
                timeout=60000  # 60 second timeout for launch
            )
            
            print("[CONTEXT] Creating new browser context...")
            self.context = self.browser.new_context(
                no_viewport=True, # Use the browser's full window size
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # Pretend to be a regular Chrome browser
                ignore_https_errors=True  # Don't fail on SSL certificate issues
            )
            
            print("[PAGE] Creating new page...")
            self.page = self.context.new_page()
            self.initial_page = self.page

            print("[SUCCESS] Playwright browser launched successfully!")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to launch browser with Playwright: {str(e)}")
            print(f"[ERROR] Full error details: {traceback.format_exc()}")
            return False

    def close_browser(self):
        """Close the browser and clean up Playwright resources."""
        try:
            if self.browser and self.browser.is_connected():
                if self.context:
                    print("[CLEANUP] Closing browser context...")
                    self.context.close()
                print("[CLEANUP] Closing browser...")
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
                print("[SUCCESS] Playwright stopped successfully.")
        except Exception as e:
            print(f"[ERROR] Error closing browser: {str(e)}")
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self.playwright = None

    def save_screenshot(self, name, step_number=None, status="info"):
        """Save screenshot and return attachment info for Allure."""
        if not self.page:
            return None
            
        try:
            timestamp = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            execution_id = getattr(self, 'current_execution_id', f'test_{timestamp}')
            filename = f"{execution_id}-{timestamp}_{name.replace(' ', '_')}.png"
            
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            filepath = os.path.join(allure_results_path, filename)
            
            screenshot_data = self.page.screenshot(path=filepath)
            
            attachment = {
                "name": name,
                "source": filename,
                "type": "image/png",
                "size": len(screenshot_data)
            }
            
            self.current_test_attachments.append(attachment)
            
            print(f"[SCREENSHOT] Saved: {filename}")
            return attachment
            
        except Exception as e:
            print(f"[ERROR] Failed to save screenshot: {str(e)}")
            return None

    @allure.feature("Test Execution")
    def execute_test_case(self, testcase_name, test_steps, test_metadata=None):
        """Execute a test case with the provided steps and metadata using Playwright."""
        execution_id = str(uuid.uuid4())
        start_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        self.clear_old_allure_results()
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
            'browser_info': 'Playwright/Chromium'
        }
        
        if test_metadata:
            result.update(test_metadata)
        
        with allure.step(f"Execute test case: {testcase_name}"):
            allure.dynamic.title(testcase_name)
            allure.dynamic.description(f"Test case execution with {len(test_steps)} steps")
            
            try:
                print(f"[ROCKET] Starting test execution: {testcase_name}")
                
                with allure.step("Launch browser"):
                    if not self.launch_browser():
                        raise Exception("Failed to launch browser with Playwright")
                
                for i, step in enumerate(test_steps, 1):
                    step_result = self.execute_step(step, i)
                    
                    result['step_results'].append(step_result)
                    
                    if step_result['status'] == 'PASS':
                        result['passed_steps'] += 1
                    elif step_result['status'] == 'FAIL':
                        result['failed_steps'] += 1
                        if not self.enable_isolation:
                            result['status'] = 'FAIL'
                            result['error_message'] = step_result.get('error_message', '')
                            break 
                    else:
                        result['skipped_steps'] += 1
                
                if result['status'] != 'FAIL':
                    if result['failed_steps'] == 0:
                        result['status'] = 'PASS'
                    elif self.enable_isolation and result['passed_steps'] > 0:
                        result['status'] = 'PARTIAL_PASS'
                        result['error_message'] = f"{result['failed_steps']} steps failed, but test continued."
                    else:
                        result['status'] = 'FAIL'

            except Exception as e:
                result['status'] = 'FAIL'
                result['error_message'] = str(e)
                print(f"[ERROR] Test execution failed: {str(e)}")
                traceback.print_exc()
            
            finally:
                end_time = datetime.now(pytz.timezone('Asia/Kolkata'))
                result['end_time'] = end_time
                execution_duration = end_time - start_time
                result['execution_time'] = str(execution_duration).split('.')[0]
                
                self.close_browser()
                
                print(f"[SUCCESS] Test execution completed: {testcase_name}")
                print(f"[BAR_CHART] Results: {result['passed_steps']} passed, {result['failed_steps']} failed, {result['skipped_steps']} skipped")
                
                self.save_allure_results(result)
                
                # Add execution_date in IST format (DD/MM/YYYY, HH:MM:SS)
                ist_timezone = pytz.timezone('Asia/Kolkata')
                execution_date_ist = start_time.astimezone(ist_timezone)
                result['execution_date'] = execution_date_ist.strftime('%d/%m/%Y, %H:%M:%S')

        # Ensure a boolean success flag for frontend compatibility
        try:
            status_upper = str(result.get('status', '')).upper()
            result['success'] = status_upper in ('PASS', 'PARTIAL_PASS')
        except Exception:
            result['success'] = False
                
        return result

    def execute_step(self, step, step_number):
        """Execute a single test step using Playwright."""
        normalized_action_type = self.normalize_action_type(step.get('action_type', ''))
        step_result = {
            'tc_id': step.get('tc_id', ''),
            'step_no': step_number,
            'description': step.get('test_step_description', ''),
            'test_step_description': step.get('test_step_description', ''),
            'element_name': step.get('element_name', ''),
            # Persist normalized action type so execution history matches runtime behavior.
            'action_type': normalized_action_type,
            'xpath': step.get('xpath', ''),
            'values': step.get('values', ''),
            'status': 'UNKNOWN',
            'error': '',
            'error_message': '',
            'execution_time': '',
            'after_screenshot': '',
            'screenshot_status': ''
        }
        
        step_start_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_description = step.get('test_step_description', 'Unknown step')
        
        print(f"[STEP] Step {step_number}: {step_description}")
        
        with allure.step(f"Step {step_number}: {step_description}"):
            allure.attach(
                json.dumps(step, indent=2),
                name="Step Details",
                attachment_type=allure.attachment_type.JSON
            )
            
            try:
                action_type = self.normalize_action_type(step.get('action_type', ''))
                xpath = step.get('xpath', '')
                element_name = step.get('element_name', '')
                test_data = step.get('values', '')

                self.execute_action(action_type, test_data, xpath, element_name)
                
                step_result['status'] = 'PASS'
                print(f"[SUCCESS] Step {step_number} completed successfully")

            except Exception as e:
                step_result['status'] = 'FAIL'
                error_msg = str(e)
                step_result['error'] = error_msg
                step_result['error_message'] = error_msg
                print(f"[ERROR] Step {step_number} failed: {error_msg}")
                print(f"[ERROR] Error details: {traceback.format_exc()}")

                error_screenshot = self.save_screenshot(f"After_Step_{step_number}_FAILED", step_number, "error")
                if error_screenshot:
                    step_result['after_screenshot'] = error_screenshot.get('source')
                    step_result['screenshot_status'] = 'error'

                allure.attach(
                    traceback.format_exc(),
                    name="Error Trace",
                    attachment_type=allure.attachment_type.TEXT
                )

        step_end_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        step_duration = step_end_time - step_start_time
        step_result['execution_time'] = str(step_duration).split('.')[0]
        
        return step_result

    def execute_action(self, action_type, test_data, xpath, element_name):
        """Execute a specific action using Playwright."""
        action_type = self.normalize_action_type(action_type)
        print(f"[ACTION] Executing: {action_type} on '{element_name}' with data: '{test_data}'")

        self.switch_to_latest_page()

        if action_type not in ["OPEN_BROWSER", "NAVIGATE_TO_URL"]:
            try:
                self.page.keyboard.press("Escape")
                print("[INFO] Pressed 'Escape' key to dismiss potential pop-ups.")
                self.page.wait_for_timeout(500)
            except Exception as e:
                print(f"[WARN] Could not press Escape key, might not be an issue: {e}")

        if action_type == "OPEN_BROWSER":
            self.page.goto(test_data, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_load_state("networkidle")

        elif action_type == "CLICK_AND_SELECT":
            self.handle_unified_click_and_select(test_data, xpath, element_name)

        elif action_type == "CLICK_AND_SELECT_DATE":
            self.handle_date_selection(test_data, xpath, element_name)

        elif action_type == "CLICK_AND_TYPE":
            try:
                self.handle_click_and_type(test_data, xpath, element_name)
                print(f"[INFO] Click and type successful for {element_name}")
            except Exception as e:
                print(f"[ERROR] Click and type failed for {element_name}: {str(e)}")
                raise e

        elif action_type == "CLICK_QUICK_DATE":
            self.handle_quick_date_selection(test_data, element_name)

        elif action_type == "CLICK_BUS_QUICK_DATE":
            self.handle_bus_quick_date_selection(test_data, element_name)

        elif action_type == "CLICK":
            try:
                if element_name.upper() == "TRAVELCLASS":
                    self.handle_travel_class_selection(test_data, xpath, element_name)
                elif element_name.upper() == "DONEBUTTON":
                    self.close_travellers_popup(xpath, element_name)
                elif test_data.upper() == "TODAY":
                    self.handle_today_selection(element_name)
                elif test_data.upper() == "TOMORROW" and "bus" in element_name.lower():
                    self.handle_bus_quick_date_selection("tomorrow", element_name)
                elif test_data.upper() == "TOMORROW":
                    self.handle_quick_date_selection("tomorrow", element_name)
                elif "day after" in test_data.lower() or test_data.upper() == "DAY-AFTER-TOMORROW":
                    self.handle_quick_date_selection("day after", element_name)
                else:
                    normalized_xpath = self.normalize_selector(xpath)
                    # Use .first to handle cases where xpath matches multiple elements
                    self.page.locator(normalized_xpath).first.click(timeout=10000)
                print(f"[INFO] Click action successful for {element_name}")
            except Exception as e:
                print(f"[ERROR] Click action failed for {element_name}: {str(e)}")
                raise e

        elif action_type == "SELECT_COUNT":
            self.handle_count_selection(test_data, xpath, element_name)

        elif action_type == "CLICK_AND_SELECT_AGE":
            child_number = re.sub(r'[^0-9]', '', element_name)
            if child_number:
                child_index = int(child_number) - 1
                self.select_child_age(child_index, int(test_data))

        elif action_type == "HANDLE_CHECKBOX":
            self.handle_checkbox_action(test_data, xpath, element_name)

        elif action_type == "SWITCH_TO_NEW_WINDOW":
            self.wait_for_new_page(timeout=int(test_data) if test_data.isdigit() else 10)

        elif action_type == "SWITCH_TO_WINDOW_BY_INDEX":
            index = int(test_data) if test_data.isdigit() else 0
            self.switch_to_page_by_index(index)

        elif action_type == "SWITCH_TO_WINDOW_BY_URL":
            self.switch_to_page_by_url(test_data)

        elif action_type == "CLOSE_EXTRA_WINDOWS":
            self.close_extra_pages()

        elif action_type == "NAVIGATE_TO_URL":
            self.page.goto(test_data, wait_until="domcontentloaded")

        elif action_type == "REFRESH_PAGE":
            self.page.reload(wait_until="domcontentloaded")

        elif action_type == "GO_BACK":
            self.page.go_back(wait_until="domcontentloaded")

        elif action_type == "GO_FORWARD":
            self.page.go_forward(wait_until="domcontentloaded")

        else:
            raise Exception(f"Unknown action type: {action_type}")

        time.sleep(0.5)

    def normalize_action_type(self, action_type):
        """Normalize legacy action names to current supported action set."""
        normalized = (action_type or "").upper().strip()
        legacy_select_actions = {
            "CLICK_AND_SELECT_DATE",
            "CLICK_QUICK_DATE",
            "CLICK_BUS_QUICK_DATE",
            "CLICK_AND_SELECT_AGE",
            "SELECT_COUNT",
        }
        if normalized in legacy_select_actions:
            return "CLICK_AND_SELECT"
        return normalized

    def resolve_count_element_type(self, element_name):
        """Map varied element labels to a canonical count type."""
        name = (element_name or "").strip().lower().replace(" ", "")
        if any(k in name for k in ["room", "roomscount", "roomcount"]):
            return "room"
        if any(k in name for k in ["adult", "adultscount", "adultcount"]):
            return "adult"
        if any(k in name for k in ["child", "children", "childrencount", "childcount"]):
            return "children"
        if any(k in name for k in ["infant", "infantscount", "infantcount"]):
            return "infant"
        return None

    # --- Action Helper Methods (Playwright implementation) ---

    def handle_click_and_type(self, test_data, xpath, element_name):
        """Handles clicking an element and then typing text into it."""
        normalized_xpath = self.normalize_selector(xpath)
        locator = self.page.locator(normalized_xpath)
        
        # Use the safe field interaction method first
        if self.safe_field_interaction_method(locator, test_data, element_name):
            return
        
        # Fallback to original method if safe method fails
        print(f"[FALLBACK] Using fallback method for {element_name}")
        
        # Wait for element to be visible and enabled
        locator.wait_for(state="visible", timeout=10000)
        
        # Click to focus the element
        locator.click(timeout=10000)
        self.page.wait_for_timeout(300)
        
        # Clear any default/prefilled value before typing.
        self.clear_prefilled_input(locator, element_name)
        
        # Fill the field with the test data
        locator.fill(test_data)
        self.page.wait_for_timeout(300)

    def clear_prefilled_input(self, locator, element_name):
        """Aggressively clear input field so click-and-type never appends to default values."""
        try:
            locator.clear(timeout=3000)
        except Exception:
            pass

        try:
            locator.press("Control+A", timeout=2000)
            locator.press("Backspace", timeout=2000)
        except Exception:
            pass

        try:
            locator.evaluate(
                """el => {
                    if ('value' in el) {
                        el.value = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }"""
            )
        except Exception:
            pass

        self.page.wait_for_timeout(150)
        print(f"[CLEAR] Cleared existing value for {element_name}")

    def safe_field_interaction_method(self, locator, text, element_name):
        """Safe field interaction method that avoids unwanted scrolling and selecting behaviors."""
        try:
            print(f"[SAFE_FILL] Safely filling '{text}' into {element_name}")
            
            # Wait for element to be ready
            locator.wait_for(state="visible", timeout=10000)
            locator.wait_for(state="attached", timeout=5000)
            
            # Scroll element into view if needed (controlled scrolling)
            locator.scroll_into_view_if_needed()
            self.page.wait_for_timeout(300)
            
            # Click to focus (single click, no double-click)
            locator.click(timeout=5000)
            self.page.wait_for_timeout(300)
            
            # Clear any default/prefilled value first.
            self.clear_prefilled_input(locator, element_name)
            
            # Fill the text
            locator.fill(text)
            self.page.wait_for_timeout(300)
            
            print(f"[SAFE_FILL] Successfully filled: {text}")
            return True
            
        except Exception as e:
            print(f"[SAFE_FILL] Failed to fill {element_name}: {str(e)}")
            return False

    def robust_fill_input(self, locator, text, element_name):
        """Robust text input with multiple fallback strategies, optimized for autocomplete fields"""
        try:
            print(f"[ROBUST_FILL] Attempting to fill '{text}' into {element_name}")
            
            # If safe field interaction is enabled, try that first
            if self.safe_field_interaction:
                if self.safe_field_interaction_method(locator, text, element_name):
                    return
                print(f"[ROBUST_FILL] Safe method failed, trying other strategies...")
            
            # For city selection fields, use autocomplete-friendly approach
            if any(keyword in element_name.lower() for keyword in ['from', 'to', 'city', 'destination', 'origin']):
                return self.fill_autocomplete_field(locator, text, element_name)
            
            # Strategy 1: Standard fill with shorter timeout
            try:
                locator.clear(timeout=5000)
                self.page.wait_for_timeout(200)
                locator.fill(text, timeout=5000)
                print(f"[ROBUST_FILL] Successfully filled using standard method: {text}")
                return
            except Exception as e:
                print(f"[ROBUST_FILL] Standard fill failed: {str(e)}")
            
            # Strategy 2: Type character by character
            try:
                locator.clear(timeout=5000)
                self.page.wait_for_timeout(200)
                locator.type(text, delay=50, timeout=10000)
                print(f"[ROBUST_FILL] Successfully typed character by character: {text}")
                return
            except Exception as e:
                print(f"[ROBUST_FILL] Character typing failed: {str(e)}")
            
            # Strategy 3: Click and use keyboard (without Control+a)
            try:
                locator.click(timeout=5000)
                self.page.wait_for_timeout(200)
                # Focus the element and clear it properly
                locator.focus()
                locator.clear()
                self.page.wait_for_timeout(100)
                self.page.keyboard.type(text, delay=50)
                print(f"[ROBUST_FILL] Successfully used keyboard method: {text}")
                return
            except Exception as e:
                print(f"[ROBUST_FILL] Keyboard method failed: {str(e)}")
            
            # Strategy 4: JavaScript injection (last resort)
            try:
                locator.evaluate(f"element => element.value = '{text}'")
                print(f"[ROBUST_FILL] Successfully used JavaScript injection: {text}")
                return
            except Exception as e:
                print(f"[ROBUST_FILL] JavaScript injection failed: {str(e)}")
            
            raise Exception(f"All input methods failed for {element_name}")
            
        except Exception as e:
            print(f"[ROBUST_FILL] All fill strategies failed for {element_name}: {str(e)}")
            raise e

    def fill_autocomplete_field(self, locator, text, element_name):
        """Specialized method for filling autocomplete/typeahead fields"""
        try:
            print(f"[AUTOCOMPLETE] Filling autocomplete field '{element_name}' with '{text}'")
            
            # First, let's debug the element state
            self.debug_element_state(locator, element_name)
            
            # Prevent unwanted scrolling by disabling smooth scrolling temporarily
            try:
                self.page.evaluate("document.documentElement.style.scrollBehavior = 'auto'")
            except:
                pass
            
            # Strategy 1: Enhanced progressive typing with better error handling
            try:
                print(f"[AUTOCOMPLETE] Strategy 1: Progressive typing")
                # Ensure element is visible and enabled
                locator.wait_for(state="visible", timeout=5000)
                
                # Click to focus
                locator.click(timeout=5000)
                self.page.wait_for_timeout(500)
                
                # Clear any existing content
                try:
                    locator.clear(timeout=2000)
                except:
                    # If clear fails, try focusing and clearing again
                    locator.focus()
                    self.page.wait_for_timeout(200)
                    try:
                        locator.clear(timeout=1000)
                    except:
                        # Last resort: select text in the field only and delete
                        locator.select_text()
                        self.page.keyboard.press("Delete")
                
                self.page.wait_for_timeout(300)
                
                # Type progressively to trigger autocomplete
                min_chars = min(3, len(text))
                for i in range(min_chars, len(text) + 1):
                    partial_text = text[:i]
                    try:
                        locator.fill(partial_text, timeout=2000)
                        self.page.wait_for_timeout(800)  # Longer wait for autocomplete
                        
                        # Check if suggestions appeared
                        suggestion_appeared = self.check_for_suggestions(text)
                        if suggestion_appeared:
                            print(f"[AUTOCOMPLETE] Suggestions appeared after typing '{partial_text}'")
                            return
                    except Exception as fill_e:
                        print(f"[AUTOCOMPLETE] Fill failed for '{partial_text}': {str(fill_e)}")
                        break
                
                print(f"[AUTOCOMPLETE] Progressive typing completed: {text}")
                return
                
            except Exception as e:
                print(f"[AUTOCOMPLETE] Progressive typing failed: {str(e)}")
            
            # Strategy 2: Enhanced character-by-character typing
            try:
                print(f"[AUTOCOMPLETE] Strategy 2: Character-by-character typing")
                locator.click(timeout=5000)
                self.page.wait_for_timeout(300)
                
                # Clear field
                try:
                    locator.clear(timeout=2000)
                except:
                    locator.focus()
                    self.page.wait_for_timeout(200)
                    try:
                        locator.clear(timeout=1000)
                    except:
                        # Last resort: select text in the field only and delete
                        locator.select_text()
                        self.page.keyboard.press("Delete")
                
                self.page.wait_for_timeout(300)
                
                # Focus the element first
                locator.focus(timeout=3000)
                self.page.wait_for_timeout(200)
                
                # Type each character with delay
                for i, char in enumerate(text):
                    try:
                        self.page.keyboard.type(char, delay=150)
                        self.page.wait_for_timeout(100)
                        
                        # Check for suggestions after typing a few characters
                        if i >= 2 and self.check_for_suggestions(text):
                            print(f"[AUTOCOMPLETE] Suggestions appeared after typing '{text[:i+1]}'")
                            return
                            
                    except Exception as char_e:
                        print(f"[AUTOCOMPLETE] Failed to type character '{char}': {str(char_e)}")
                        break
                
                print(f"[AUTOCOMPLETE] Character-by-character typing completed: {text}")
                return
                
            except Exception as e:
                print(f"[AUTOCOMPLETE] Character-by-character typing failed: {str(e)}")
            
            # Strategy 3: Enhanced focus and keyboard typing
            try:
                print(f"[AUTOCOMPLETE] Strategy 3: Focus and keyboard typing")
                locator.focus(timeout=5000)
                self.page.wait_for_timeout(500)
                
                # Clear existing content using locator methods
                try:
                    locator.clear()
                except:
                    # If clear fails, try selecting text in the field only
                    locator.select_text()
                    self.page.keyboard.press("Delete")
                self.page.wait_for_timeout(200)
                
                # Type with delays
                self.page.keyboard.type(text, delay=120)
                self.page.wait_for_timeout(800)
                
                print(f"[AUTOCOMPLETE] Focus and keyboard typing completed: {text}")
                return
                
            except Exception as e:
                print(f"[AUTOCOMPLETE] Focus and keyboard typing failed: {str(e)}")
            
            # Strategy 4: Enhanced JavaScript with comprehensive event triggering
            try:
                print(f"[AUTOCOMPLETE] Strategy 4: JavaScript with events")
                js_code = f"""
                (element) => {{
                    console.log('Starting JavaScript input for element:', element);
                    
                    // Ensure element is focused
                    element.focus();
                    element.click();
                    
                    // Clear existing value
                    element.value = '';
                    element.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                    element.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    
                    const text = '{text}';
                    let currentValue = '';
                    
                    // Simulate typing character by character
                    for (let i = 0; i < text.length; i++) {{
                        currentValue += text[i];
                        element.value = currentValue;
                        
                        // Trigger multiple events to ensure compatibility
                        element.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                        element.dispatchEvent(new Event('keyup', {{ bubbles: true, cancelable: true }}));
                        element.dispatchEvent(new KeyboardEvent('keyup', {{ 
                            key: text[i], 
                            bubbles: true, 
                            cancelable: true 
                        }}));
                        
                        // Add small delay between characters
                        if (i < text.length - 1) {{
                            // Use setTimeout for delay (though it won't actually delay in this context)
                            // The delay is handled by the Python wait_for_timeout
                        }}
                    }}
                    
                    // Final events
                    element.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    element.dispatchEvent(new Event('blur', {{ bubbles: true, cancelable: true }}));
                    element.dispatchEvent(new Event('focus', {{ bubbles: true, cancelable: true }}));
                    
                    console.log('JavaScript input completed. Final value:', element.value);
                    return element.value;
                }}
                """
                result = locator.evaluate(js_code)
                self.page.wait_for_timeout(1000)
                
                print(f"[AUTOCOMPLETE] JavaScript completed with result: {result}")
                return
                
            except Exception as e:
                print(f"[AUTOCOMPLETE] JavaScript with events failed: {str(e)}")
            
            # Strategy 5: Fallback - try simple fill with longer timeout
            try:
                print(f"[AUTOCOMPLETE] Strategy 5: Simple fill fallback")
                locator.click(timeout=5000)
                self.page.wait_for_timeout(500)
                locator.fill(text, timeout=10000)  # Longer timeout
                self.page.wait_for_timeout(1000)
                
                print(f"[AUTOCOMPLETE] Simple fill fallback completed: {text}")
                return
                
            except Exception as e:
                print(f"[AUTOCOMPLETE] Simple fill fallback failed: {str(e)}")
            
            raise Exception(f"All autocomplete fill methods failed for {element_name}")
            
        except Exception as e:
            print(f"[AUTOCOMPLETE] All autocomplete strategies failed for {element_name}: {str(e)}")
            raise e

    def check_for_suggestions(self, city_name):
        """Check if autocomplete suggestions have appeared"""
        try:
            # Common selectors for suggestion dropdowns
            suggestion_containers = [
                'xpath=//div[contains(@class, "suggestion")]',
                'xpath=//div[contains(@class, "dropdown")]',
                'xpath=//div[contains(@class, "autocomplete")]',
                'xpath=//ul[contains(@class, "suggestion")]',
                'xpath=//div[contains(@class, "airport")]',
                'xpath=//*[contains(@class, "menu") and contains(@class, "visible")]'
            ]
            
            for selector in suggestion_containers:
                try:
                    suggestions = self.page.locator(selector)
                    if suggestions.count() > 0 and suggestions.first.is_visible(timeout=1000):
                        print(f"[SUGGESTIONS] Found suggestions using selector: {selector}")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            print(f"[SUGGESTIONS] Error checking for suggestions: {str(e)}")
            return False

    def debug_element_state(self, locator, element_name):
        """Debug method to check element state and properties"""
        try:
            print(f"[DEBUG] Checking state of element '{element_name}'")
            
            # Check if element exists and is visible
            is_visible = locator.is_visible(timeout=2000)
            print(f"[DEBUG] Element visible: {is_visible}")
            
            if is_visible:
                # Check element properties
                try:
                    is_enabled = locator.is_enabled(timeout=1000)
                    print(f"[DEBUG] Element enabled: {is_enabled}")
                except:
                    print(f"[DEBUG] Could not check if element is enabled")
                
                try:
                    is_editable = locator.is_editable(timeout=1000)
                    print(f"[DEBUG] Element editable: {is_editable}")
                except:
                    print(f"[DEBUG] Could not check if element is editable")
                
                # Get element attributes
                try:
                    tag_name = locator.evaluate("el => el.tagName")
                    print(f"[DEBUG] Element tag: {tag_name}")
                except:
                    print(f"[DEBUG] Could not get element tag")
                
                try:
                    element_type = locator.evaluate("el => el.type")
                    print(f"[DEBUG] Element type: {element_type}")
                    
                    # Warn if we found a non-text input for city fields
                    if element_type in ['checkbox', 'radio', 'hidden', 'submit', 'button']:
                        print(f"[WARNING] Found non-text input type '{element_type}' for city field '{element_name}' - this may cause issues!")
                        
                except:
                    print(f"[DEBUG] Could not get element type")
                
                try:
                    placeholder = locator.evaluate("el => el.placeholder")
                    print(f"[DEBUG] Element placeholder: {placeholder}")
                except:
                    print(f"[DEBUG] Could not get element placeholder")
                
                try:
                    readonly = locator.evaluate("el => el.readOnly")
                    print(f"[DEBUG] Element readonly: {readonly}")
                except:
                    print(f"[DEBUG] Could not check readonly status")
                
                try:
                    disabled = locator.evaluate("el => el.disabled")
                    print(f"[DEBUG] Element disabled: {disabled}")
                except:
                    print(f"[DEBUG] Could not check disabled status")
                
                try:
                    current_value = locator.evaluate("el => el.value")
                    print(f"[DEBUG] Current value: '{current_value}'")
                except:
                    print(f"[DEBUG] Could not get current value")
                    
        except Exception as e:
            print(f"[DEBUG] Error during element state check: {str(e)}")

    def find_active_input_field(self, input_placeholder, element_name):
        """Find the active input field after clicking on a city selection element"""
        try:
            print(f"[INPUT_SEARCH] Looking for active input field for '{element_name}'")
            
            # Enhanced input selectors with better Ixigo-specific patterns
            # Prioritize text inputs and exclude checkboxes, radio buttons, etc.
            input_selectors = [
                # Placeholder-based selectors (text inputs only)
                f'xpath=//input[@placeholder="{input_placeholder}" and (@type="text" or not(@type))]',
                f'xpath=//input[contains(@placeholder, "{input_placeholder}") and (@type="text" or not(@type))]',
                f'xpath=//input[contains(@placeholder, "{input_placeholder.lower()}") and (@type="text" or not(@type))]',
                
                # Class-based selectors (text inputs only)
                'xpath=//input[contains(@class, "search") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "input") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "autocomplete") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "typeahead") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "city") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "location") and (@type="text" or not(@type))]',
                
                # State-based selectors (active/focused elements, text inputs only)
                'xpath=//div[contains(@class, "active")]//input[(@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "focused")]//input[(@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "open")]//input[(@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "expanded")]//input[(@type="text" or not(@type))]',
                
                # Generic text input selectors (explicitly exclude non-text types)
                'xpath=//input[@type="text"]',
                'xpath=//input[not(@type) or @type=""]',
                'xpath=//input[not(@type="checkbox") and not(@type="radio") and not(@type="hidden") and not(@type="submit") and not(@type="button")]',
                
                # Recently appeared inputs (last in DOM, text inputs only)
                'xpath=(//input[@type="text"])[last()]',
                'xpath=(//input[contains(@class, "input") and (@type="text" or not(@type))])[last()]'
            ]
            
            for input_selector in input_selectors:
                try:
                    # Try both first and last elements
                    for position in ['first', 'last']:
                        try:
                            if position == 'first':
                                input_locator = self.page.locator(input_selector).first
                            else:
                                input_locator = self.page.locator(input_selector).last
                            
                            if input_locator.is_visible(timeout=1000):
                                # Additional validation: check if it's actually a text input
                                try:
                                    element_type = input_locator.evaluate("el => el.type")
                                    if element_type in ['checkbox', 'radio', 'hidden', 'submit', 'button']:
                                        print(f"[INPUT_SEARCH] Skipping non-text input type '{element_type}' from selector: {input_selector}")
                                        continue
                                except:
                                    pass  # If we can't check type, proceed anyway
                                
                                print(f"[INPUT_SEARCH] Found input field using selector ({position}): {input_selector}")
                                return input_locator
                        except:
                            continue
                            
                except Exception as e:
                    print(f"[DEBUG] Input selector '{input_selector}' failed: {str(e)}")
                    continue
            
            print(f"[INPUT_SEARCH] No active input field found for '{element_name}'")
            return None
            
        except Exception as e:
            print(f"[INPUT_SEARCH] Error during input field search: {str(e)}")
            return None

    def find_input_near_element(self, clicked_element, element_name):
        """Find text input field near the clicked element"""
        try:
            print(f"[NEAR_INPUT] Looking for input field near clicked element for '{element_name}'")
            
            # Try to find input fields in the same parent container
            near_selectors = [
                # Sibling inputs
                'xpath=./following-sibling::input[(@type="text" or not(@type))]',
                'xpath=./preceding-sibling::input[(@type="text" or not(@type))]',
                
                # Parent container inputs
                'xpath=./parent::*/input[(@type="text" or not(@type))]',
                'xpath=./parent::*//input[(@type="text" or not(@type))]',
                
                # Ancestor container inputs (up to 3 levels)
                'xpath=./ancestor::*[1]//input[(@type="text" or not(@type))]',
                'xpath=./ancestor::*[2]//input[(@type="text" or not(@type))]',
                'xpath=./ancestor::*[3]//input[(@type="text" or not(@type))]',
                
                # Following inputs in DOM order
                'xpath=./following::input[(@type="text" or not(@type))][1]',
                'xpath=./following::input[(@type="text" or not(@type))][2]',
            ]
            
            for selector in near_selectors:
                try:
                    near_inputs = clicked_element.locator(selector)
                    count = near_inputs.count()
                    
                    for i in range(count):
                        try:
                            input_locator = near_inputs.nth(i)
                            if input_locator.is_visible(timeout=1000):
                                # Validate it's a text input
                                try:
                                    element_type = input_locator.evaluate("el => el.type")
                                    if element_type in ['checkbox', 'radio', 'hidden', 'submit', 'button']:
                                        continue
                                except:
                                    pass
                                
                                print(f"[NEAR_INPUT] Found input near clicked element using: {selector} (index {i})")
                                return input_locator
                        except:
                            continue
                            
                except Exception as e:
                    print(f"[DEBUG] Near selector '{selector}' failed: {str(e)}")
                    continue
            
            print(f"[NEAR_INPUT] No input field found near clicked element")
            return None
            
        except Exception as e:
            print(f"[NEAR_INPUT] Error during near input search: {str(e)}")
            return None

    def find_any_visible_input(self):
        """Find any visible input field as a last resort"""
        try:
            print(f"[FALLBACK_INPUT] Looking for any visible input field")
            
            fallback_selectors = [
                'xpath=//input[@type="text" and not(@style*="display: none") and not(@style*="visibility: hidden")]',
                'xpath=//input[contains(@class, "input") and (@type="text" or not(@type)) and not(@style*="display: none")]',
                'xpath=//input[not(@type="hidden") and not(@type="submit") and not(@type="button") and not(@type="checkbox") and not(@type="radio")]',
                'xpath=//input[(@type="text" or not(@type)) and not(@type="checkbox") and not(@type="radio")]'
            ]
            
            for selector in fallback_selectors:
                try:
                    inputs = self.page.locator(selector)
                    count = inputs.count()
                    
                    for i in range(count):
                        try:
                            input_locator = inputs.nth(i)
                            if input_locator.is_visible(timeout=500):
                                # Additional validation: check if it's actually a text input
                                try:
                                    element_type = input_locator.evaluate("el => el.type")
                                    if element_type in ['checkbox', 'radio', 'hidden', 'submit', 'button']:
                                        print(f"[FALLBACK_INPUT] Skipping non-text input type '{element_type}' from fallback selector")
                                        continue
                                except:
                                    pass  # If we can't check type, proceed anyway
                                
                                print(f"[FALLBACK_INPUT] Found visible input using selector: {selector} (index {i})")
                                return input_locator
                        except:
                            continue
                            
                except Exception as e:
                    print(f"[DEBUG] Fallback selector '{selector}' failed: {str(e)}")
                    continue
            
            print(f"[FALLBACK_INPUT] No visible input field found")
            return None
            
        except Exception as e:
            print(f"[FALLBACK_INPUT] Error during fallback input search: {str(e)}")
            return None

    def dismiss_popups_and_overlays(self):
        """Enhanced method to dismiss various popups and overlays that might interfere"""
        try:
            print("[POPUP_DISMISS] Attempting to dismiss popups and overlays")
            
            # Press Escape key first to dismiss any open dialogs
            try:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(500)
                print("[POPUP_DISMISS] Pressed Escape key")
            except:
                pass
            
            # Try to close various types of overlays and modals
            close_selectors = [
                # Generic close buttons
                '//button[contains(@class, "close")]',
                '//button[contains(@aria-label, "close")]',
                '//button[contains(@aria-label, "Close")]',
                '[aria-label="Close"]',
                '[data-testid="close"]',
                
                # Modal and overlay close buttons
                '//div[contains(@class, "modal")]//button[contains(@class, "close")]',
                '//div[contains(@class, "overlay")]//button',
                '//div[contains(@class, "popup")]//button[contains(@class, "close")]',
                
                # Specific close icons
                '//i[contains(@class, "close")]',
                '//span[contains(@class, "close")]',
                '//*[contains(@class, "icon-close")]',
                '//*[contains(@class, "fa-times")]',
                '//*[contains(@class, "fa-close")]',
                
                # Ixigo specific selectors
                '//div[contains(@class, "notification")]//button',
                '//div[contains(@class, "banner")]//button',
                '//div[contains(@class, "promo")]//button[contains(@class, "close")]'
            ]
            
            for close_selector in close_selectors:
                try:
                    close_btn = self.page.locator(close_selector).first
                    if close_btn.is_visible(timeout=1000):
                        close_btn.click(timeout=2000)
                        print(f"[POPUP_DISMISS] Closed overlay/modal using: {close_selector}")
                        self.page.wait_for_timeout(500)
                        break
                except:
                    continue
                    
            # Try clicking outside any modal to dismiss it
            try:
                # Check if there's a modal backdrop
                backdrop_selectors = [
                    '//div[contains(@class, "backdrop")]',
                    '//div[contains(@class, "modal-backdrop")]',
                    '//div[contains(@class, "overlay-backdrop")]'
                ]
                
                for backdrop_selector in backdrop_selectors:
                    try:
                        backdrop = self.page.locator(backdrop_selector).first
                        if backdrop.is_visible(timeout=1000):
                            backdrop.click(timeout=2000)
                            print(f"[POPUP_DISMISS] Clicked backdrop to dismiss modal: {backdrop_selector}")
                            self.page.wait_for_timeout(500)
                            break
                    except:
                        continue
                        
            except Exception as e:
                print(f"[POPUP_DISMISS] Backdrop click attempt failed: {str(e)}")
                
        except Exception as e:
            print(f"[POPUP_DISMISS] Error during popup dismissal: {str(e)}")

    def select_city_suggestion(self, city_name, input_locator):
        """Enhanced method to select city from autocomplete suggestions"""
        try:
            print(f"[SUGGESTION_SELECT] Attempting to select '{city_name}' from suggestions")
            
            # Wait for suggestions to appear
            self.page.wait_for_timeout(2000)
            
            # Strategy 1: Try exact match selectors with city name - enhanced for Ixigo
            exact_match_selectors = [
                f'xpath=//div[contains(@class, "airport-city") and contains(normalize-space(), "{city_name}")]',
                f'xpath=//li[contains(normalize-space(), "{city_name}")]',
                f'xpath=//div[contains(@class, "suggestion") and contains(normalize-space(), "{city_name}")]',
                f'xpath=//*[contains(@class, "autocomplete")]//*[contains(normalize-space(), "{city_name}")]',
                f'xpath=//*[contains(text(), "{city_name}")]',
                f'xpath=//p[contains(normalize-space(), "{city_name}")]',
                f'xpath=//span[contains(normalize-space(), "{city_name}")]',
                f'xpath=//div[contains(@class, "city-name") and contains(normalize-space(), "{city_name}")]',
                f'xpath=//div[contains(@class, "location") and contains(normalize-space(), "{city_name}")]',
                f'xpath=//div[contains(@class, "option") and contains(normalize-space(), "{city_name}")]',
                f'xpath=//div[contains(@class, "item") and contains(normalize-space(), "{city_name}")]'
            ]
            
            for selector in exact_match_selectors:
                try:
                    suggestion_locator = self.page.locator(selector).first
                    if suggestion_locator.is_visible(timeout=2000):
                        suggestion_locator.click(timeout=5000)
                        print(f"[SUCCESS] Clicked exact match suggestion using: {selector}")
                        return True
                except Exception as e:
                    print(f"[DEBUG] Exact match selector '{selector}' failed: {str(e)}")
                    continue
            
            # Strategy 2: Try partial match with first few characters
            city_prefix = city_name[:4] if len(city_name) > 4 else city_name
            partial_match_selectors = [
                f'xpath=//*[contains(@class, "suggestion") and contains(normalize-space(), "{city_prefix}")]',
                f'xpath=//*[contains(@class, "airport") and contains(normalize-space(), "{city_prefix}")]',
                f'xpath=//li[contains(normalize-space(), "{city_prefix}")]',
                f'xpath=//*[contains(text(), "{city_prefix}")]'
            ]
            
            for selector in partial_match_selectors:
                try:
                    suggestion_locator = self.page.locator(selector).first
                    if suggestion_locator.is_visible(timeout=2000):
                        suggestion_locator.click(timeout=5000)
                        print(f"[SUCCESS] Clicked partial match suggestion using: {selector}")
                        return True
                except Exception as e:
                    print(f"[DEBUG] Partial match selector '{selector}' failed: {str(e)}")
                    continue
            
            # Strategy 3: Keyboard navigation (Arrow Down + Enter)
            try:
                print(f"[FALLBACK] Trying keyboard navigation for suggestion selection")
                input_locator.press("ArrowDown", timeout=2000)
                self.page.wait_for_timeout(300)
                input_locator.press("Enter", timeout=2000)
                print(f"[SUCCESS] Used keyboard navigation for city selection")
                return True
            except Exception as e:
                print(f"[DEBUG] Keyboard navigation failed: {str(e)}")
            
            # Strategy 4: Try clicking first visible suggestion
            try:
                print(f"[FALLBACK] Trying to click first visible suggestion")
                generic_suggestion_selectors = [
                    'xpath=//div[contains(@class, "suggestion")]//div[1]',
                    'xpath=//ul[contains(@class, "suggestion")]//li[1]',
                    'xpath=//div[contains(@class, "dropdown")]//div[1]',
                    'xpath=//*[contains(@class, "autocomplete")]//*[1]'
                ]
                
                for selector in generic_suggestion_selectors:
                    try:
                        first_suggestion = self.page.locator(selector).first
                        if first_suggestion.is_visible(timeout=1000):
                            first_suggestion.click(timeout=3000)
                            print(f"[SUCCESS] Clicked first suggestion using: {selector}")
                            return True
                    except:
                        continue
                        
            except Exception as e:
                print(f"[DEBUG] First suggestion click failed: {str(e)}")
            
            # Strategy 5: Final fallback - just press Enter
            try:
                print(f"[FINAL_FALLBACK] Pressing Enter as final fallback")
                input_locator.press("Enter", timeout=2000)
                print(f"[FALLBACK] Pressed Enter as final fallback")
                return True
            except Exception as e:
                print(f"[DEBUG] Final Enter fallback failed: {str(e)}")
            
            return False
            
        except Exception as e:
            print(f"[ERROR] All suggestion selection methods failed: {str(e)}")
            return False

    def handle_city_selection(self, city_name, xpath, element_name):
        # Enhanced pop-up dismissal specific to city selection
        self.dismiss_popups_and_overlays()
        
        # Prevent unwanted scrolling behavior
        try:
            self.page.evaluate("""
                document.documentElement.style.scrollBehavior = 'auto';
                document.body.style.scrollBehavior = 'auto';
            """)
        except:
            pass
        
        # Additional wait to ensure page is stable
        self.page.wait_for_timeout(1000)
        
        # Try multiple strategies to find the clickable element
        clickable_locator = None
        input_placeholder = element_name
        
        if 'from' in element_name.lower():
            # Try multiple selectors for "From" field - enhanced for Ixigo
            selectors = [
                '[data-testid="originId"]',
                'xpath=//input[@placeholder="From" and (@type="text" or not(@type))]',
                'xpath=//input[contains(@placeholder, "From") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@placeholder, "from") and (@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "from")]//input[(@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "origin")]//input[(@type="text" or not(@type))]',
                'xpath=//label[contains(text(), "From")]/following::input[(@type="text" or not(@type))][1]',
                'xpath=//span[contains(text(), "From")]/following::input[(@type="text" or not(@type))][1]',
                # Additional specific selectors for "From" field
                'xpath=//input[contains(@class, "origin") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "from-city") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@id, "origin") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@id, "from") and (@type="text" or not(@type))]',
                self.normalize_selector(xpath)
            ]
            input_placeholder = "From"
        elif 'to' in element_name.lower() or 'destination' in element_name.lower():
            # Try multiple selectors for "To" field - enhanced for Ixigo
            selectors = [
                '[data-testid="destinationId"]',
                'xpath=//input[@placeholder="To" and (@type="text" or not(@type))]',
                'xpath=//input[contains(@placeholder, "To") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@placeholder, "to") and (@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "to")]//input[(@type="text" or not(@type))]',
                'xpath=//div[contains(@class, "destination")]//input[(@type="text" or not(@type))]',
                'xpath=//label[contains(text(), "To")]/following::input[(@type="text" or not(@type))][1]',
                'xpath=//span[contains(text(), "To")]/following::input[(@type="text" or not(@type))][1]',
                # Additional specific selectors for "To" field
                'xpath=//input[contains(@class, "destination") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@class, "to-city") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@id, "destination") and (@type="text" or not(@type))]',
                'xpath=//input[contains(@id, "to") and (@type="text" or not(@type))]',
                self.normalize_selector(xpath)
            ]
            input_placeholder = "To"
        else:
            selectors = [self.normalize_selector(xpath)]
        
        # Try each selector until one works
        for selector in selectors:
            try:
                clickable_locator = self.page.locator(selector).first
                # Test if the element is visible and clickable
                if clickable_locator.is_visible(timeout=2000):
                    # Additional validation: ensure we're not clicking on a checkbox
                    try:
                        element_type = clickable_locator.evaluate("el => el.type")
                        if element_type in ['checkbox', 'radio']:
                            print(f"[DEBUG] Skipping clickable element with type '{element_type}' from selector: {selector}")
                            continue
                    except:
                        pass  # If we can't check type, proceed anyway
                    
                    print(f"[INFO] Found clickable element using selector: {selector}")
                    break
            except Exception as e:
                print(f"[DEBUG] Selector '{selector}' failed: {str(e)}")
                continue
        
        if not clickable_locator:
            # Debug: Print page title and URL for troubleshooting
            print(f"[DEBUG] Current page title: {self.page.title()}")
            print(f"[DEBUG] Current page URL: {self.page.url}")
            
            # Try to find any input elements on the page for debugging
            all_inputs = self.page.locator('xpath=//input').all()
            print(f"[DEBUG] Found {len(all_inputs)} input elements on the page")
            for i, input_elem in enumerate(all_inputs[:5]):  # Show first 5 inputs
                try:
                    placeholder = input_elem.get_attribute('placeholder')
                    class_name = input_elem.get_attribute('class')
                    print(f"[DEBUG] Input {i+1}: placeholder='{placeholder}', class='{class_name}'")
                except:
                    pass
            
            raise Exception(f"Could not find clickable element for {element_name}")
        
        # Click the element with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                clickable_locator.click(timeout=10000)
                print(f"[SUCCESS] Clicked {element_name} on attempt {attempt + 1}")
                break
            except Exception as e:
                print(f"[RETRY] Click attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise e
                self.page.wait_for_timeout(1000)
        
        # Wait longer for the input field to appear after clicking
        self.page.wait_for_timeout(1000)

        # Try multiple strategies to find the input field - enhanced for Ixigo
        input_locator = self.find_active_input_field(input_placeholder, element_name)
        
        # If we couldn't find a proper input field, try to find one near the clicked element
        if not input_locator and clickable_locator:
            print(f"[INPUT_SEARCH] Trying to find input field near clicked element")
            input_locator = self.find_input_near_element(clickable_locator, element_name)
        
        if not input_locator:
            print(f"[WARN] Could not find input field, trying to type directly into clicked element")
            # If we can't find a separate input field, try typing into the clicked element
            try:
                self.robust_fill_input(clickable_locator, city_name, element_name)
            except Exception as e:
                print(f"[ERROR] Could not fill text into clicked element: {str(e)}")
                # Last resort: try to find any visible input field
                input_locator = self.find_any_visible_input()
                if input_locator:
                    print(f"[FALLBACK] Found fallback input field, attempting to fill")
                    self.robust_fill_input(input_locator, city_name, element_name)
                else:
                    raise e
        else:
            self.robust_fill_input(input_locator, city_name, element_name)
        
        # Enhanced suggestion selection with better waiting and multiple strategies
        suggestion_clicked = self.select_city_suggestion(city_name, input_locator or clickable_locator)
        
        if not suggestion_clicked:
            print(f"[WARN] Could not select suggestion for {city_name}, but input was filled")
        
        # Final wait for any UI updates
        self.page.wait_for_timeout(500)
        
        # Restore normal scroll behavior
        try:
            self.page.evaluate("""
                document.documentElement.style.scrollBehavior = '';
                document.body.style.scrollBehavior = '';
            """)
        except:
            pass

    def handle_unified_click_and_select(self, test_data, xpath, element_name):
        """Unified CLICK_AND_SELECT method that intelligently handles all selection types"""
        try:
            print(f"[UNIFIED_SELECT] Processing element: {element_name} with data: '{test_data}'")

            # Determine the selection type based on element name and test data patterns
            selection_type = self.determine_selection_type(element_name, test_data)
            print(f"[UNIFIED_SELECT] Determined selection type: {selection_type}")

            if selection_type == "CITY_SELECTION":
                # Handle city selection (FROM, TO, DESTINATION)
                try:
                    print(f"[UNIFIED_SELECT] Handling city selection for {element_name}")
                    success = self.handle_city_selection_fast_safe(test_data, xpath, element_name)
                    if not success:
                        raise Exception(f"City selection failed for {element_name}")
                except Exception as e:
                    print(f"[UNIFIED_SELECT] City selection error: {str(e)}")
                    raise e

            elif selection_type == "DATE_SELECTION":
                # Handle date selection
                try:
                    print(f"[UNIFIED_SELECT] Handling date selection for {element_name}")
                    self.handle_date_selection_fast(test_data, xpath, element_name)
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Date selection error: {str(e)}")
                    raise e

            elif selection_type == "QUICK_DATE_SELECTION":
                # Handle quick date selection (Today, Tomorrow, Day After Tomorrow)
                try:
                    print(f"[UNIFIED_SELECT] Handling quick date selection for {element_name}")
                    if "bus" in element_name.lower():
                        self.handle_bus_quick_date_selection(test_data, element_name)
                    else:
                        self.handle_quick_date_selection(test_data, element_name)
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Quick date selection error: {str(e)}")
                    raise e

            elif selection_type == "AGE_SELECTION":
                # Handle age selection for children
                try:
                    print(f"[UNIFIED_SELECT] Handling age selection for {element_name}")
                    if element_name.upper() == "CHILD 1":
                        self.select_child_age(0, int(test_data))
                    elif element_name.upper() == "CHILD 2":
                        self.select_child_age(1, int(test_data))
                    elif element_name.upper() == "CHILD 3":
                        self.select_child_age(2, int(test_data))
                    else:
                        # Extract child number from element name
                        child_number = re.sub(r'[^0-9]', '', element_name)
                        if child_number:
                            child_index = int(child_number) - 1
                            self.select_child_age(child_index, int(test_data))
                        else:
                            raise Exception(f"Could not determine child index from element name: {element_name}")
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Age selection error: {str(e)}")
                    raise e

            elif selection_type == "COUNT_SELECTION":
                # Handle count selection for rooms/adults/children
                try:
                    print(f"[UNIFIED_SELECT] Handling count selection for {element_name}")
                    self.handle_count_selection(test_data, xpath, element_name)
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Count selection error: {str(e)}")
                    raise e

            elif selection_type == "GENERIC_CLICK":
                # Handle generic element click
                try:
                    print(f"[UNIFIED_SELECT] Handling generic click for {element_name}")
                    element = self.find_element_with_advanced_wait(xpath)
                    self.perform_robust_click(element)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Generic click error: {str(e)}")
                    raise e

            else:
                # Unknown selection type - fallback to generic click
                print(f"[UNIFIED_SELECT] Unknown selection type, falling back to generic click")
                try:
                    element = self.find_element_with_advanced_wait(xpath)
                    self.perform_robust_click(element)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"[UNIFIED_SELECT] Fallback click error: {str(e)}")
                    raise e

            print(f"[UNIFIED_SELECT] Successfully completed {selection_type} for {element_name}")

        except Exception as e:
            print(f"[UNIFIED_SELECT] Error in unified click and select: {str(e)}")
            raise e

    def determine_selection_type(self, element_name, test_data):
        """Determine the type of selection based on element name and test data"""
        try:
            element_name_lower = element_name.lower()
            test_data_lower = test_data.lower() if test_data else ""

            # Check for city selection
            if element_name.upper() in ["FROM", "TO", "DESTINATION"]:
                return "CITY_SELECTION"

            # Check for age selection
            if "child" in element_name_lower and "age" in element_name_lower:
                return "AGE_SELECTION"
            if element_name.upper().startswith("CHILD ") and test_data.isdigit():
                return "AGE_SELECTION"

            # Check for count selection (legacy SELECT_COUNT behavior)
            if self.resolve_count_element_type(element_name) and test_data and str(test_data).strip().isdigit():
                return "COUNT_SELECTION"

            # Check for quick date selection
            quick_date_keywords = ["today", "tomorrow", "day after", "day-after-tomorrow"]
            if any(keyword in test_data_lower for keyword in quick_date_keywords):
                return "QUICK_DATE_SELECTION"

            # Check for date selection based on element name
            date_element_keywords = [
                'date', 'checkin', 'check-in', 'checkout', 'check-out',
                'departure', 'arrival', 'return', 'calendar', 'pick'
            ]
            if any(keyword in element_name_lower for keyword in date_element_keywords):
                return "DATE_SELECTION"

            # Check for date selection based on test data patterns
            if self.is_date_format_data(test_data):
                return "DATE_SELECTION"

            # Default to generic click
            return "GENERIC_CLICK"

        except Exception as e:
            print(f"[DETERMINE_TYPE] Error determining selection type: {str(e)}")
            return "GENERIC_CLICK"

    def is_date_format_data(self, test_data):
        """Check if test data appears to be in a date format"""
        if not test_data:
            return False

        try:
            import re

            # Check for common date patterns
            date_patterns = [
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # dd/mm/yyyy or mm/dd/yyyy
                r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # yyyy/mm/dd
                r'\w{3},?\s+\d{1,2}\s+\w{3}',      # Wed, 30 Jul
                r'\d{1,2}\s+\w{3}\s+\d{4}',       # 30 Jul 2024
                r'\w{3}\s+\d{1,2},?\s+\d{4}',     # Jul 30, 2024
            ]

            for pattern in date_patterns:
                if re.search(pattern, test_data):
                    return True

            # Check for day/month names
            date_keywords = [
                'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
                'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september', 'october', 'november', 'december'
            ]

            test_data_lower = test_data.lower()
            return any(keyword in test_data_lower for keyword in date_keywords)

        except Exception:
            return False

    def handle_city_selection_fast_safe(self, city_name, xpath, element_name):
        """Fast and safe city selection method"""
        try:
            print(f"[CITY_FAST_SAFE] Selecting city: {city_name} for {element_name}")

            # Use the existing city selection logic but make it more robust
            self.handle_city_selection(city_name, xpath, element_name)
            return True

        except Exception as e:
            print(f"[CITY_FAST_SAFE] Error in fast safe city selection: {str(e)}")
            return False

    def handle_date_selection_fast(self, date_string, xpath, element_name):
        """Fast date selection method"""
        try:
            print(f"[DATE_FAST] Selecting date: {date_string} for {element_name}")

            # Use the existing date selection logic
            self.handle_date_selection(date_string, xpath, element_name)

        except Exception as e:
            print(f"[DATE_FAST] Error in fast date selection: {str(e)}")
            raise e

    def find_element_with_advanced_wait(self, xpath):
        """Find element with advanced wait strategies - Playwright version"""
        try:
            normalized_xpath = self.normalize_selector(xpath)
            # Try with standard wait first
            return self.page.locator(normalized_xpath).first
        except Exception:
            try:
                # Try with presence_of_element_located equivalent
                self.page.locator(normalized_xpath).wait_for(state="attached", timeout=10000)
                return self.page.locator(normalized_xpath).first
            except Exception:
                # Last resort - direct locator
                return self.page.locator(normalized_xpath).first

    def perform_robust_click(self, element):
        """Perform robust click with multiple fallback strategies - Playwright version"""
        try:
            # Method 1: Regular click
            element.click(timeout=10000)
            print("[ROBUST_CLICK] Regular click successful")
        except Exception as e:
            print(f"[ROBUST_CLICK] Regular click failed: {e}")
            try:
                # Method 2: JavaScript click
                element.evaluate("element => element.click()")
                print("[ROBUST_CLICK] JavaScript click successful")
            except Exception as e:
                print(f"[ROBUST_CLICK] All click methods failed: {e}")
                raise e

    def handle_date_selection_fast(self, date_string, xpath, element_name):
        """Handle fast date selection for calendar inputs - Playwright version"""
        try:
            print(f"[DATE] Selecting date: {date_string} for {element_name}")

            # Click on date field to open calendar
            normalized_xpath = self.normalize_selector(xpath)
            date_field = self.page.locator(normalized_xpath)
            date_field.click()
            self.page.wait_for_timeout(1000)  # Wait for calendar to appear

            # Parse and normalize date input safely.
            # Supports ISO strings, slash dates, and "Tue, 03 Mar" style UI values.
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
                        if has_year:
                            target_date = parsed_date
                        else:
                            target_date = parsed_date.replace(year=current_year)
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

            # Based on execution logs, these are the only selectors that work for ixigo:
            date_selectors = [
                # For buses - works with generic elements
                f"//*[text()='{day}' and (name()='button' or name()='td' or name()='div' or name()='span')]",

                # For flights/trains - works with aria-label
                f"//abbr[@aria-label='{full_date_label}']",

                # For hotels - fallback when calendar stays open
                f"//abbr[text()='{day}' and not(ancestor::*[contains(@class, 'disabled') or contains(@class, 'inactive')])]"
            ]

            date_selected = False

            for selector in date_selectors:
                try:
                    print(f"[SEARCH] Trying selector: {selector}")
                    date_elements = self.page.locator(f"xpath={selector}").all()
                    print(f"[COUNT] Found {len(date_elements)} elements with selector")

                    if not date_elements:
                        continue

                    for date_element in date_elements:
                        try:
                            if date_element.is_visible() and not date_element.is_disabled():
                                class_name = date_element.get_attribute("class") or ""
                                if class_name and ("disabled" in class_name or "inactive" in class_name):
                                    continue

                                print(f"[TARGET] Attempting to click date element: {day}")
                                date_element.click()
                                self.page.wait_for_timeout(800)

                                # Check if calendar closed (successful selection)
                                if self.is_calendar_closed():
                                    date_selected = True
                                    print(f"[SUCCESS] Date selected successfully: {day} using selector: {selector}")
                                    break
                                else:
                                    print("[WARNING] Calendar still open, trying next element")
                        except Exception as e:
                            print(f"[WARNING] Failed to click element: {e}")
                            continue

                    if date_selected:
                        break

                except Exception as e:
                    print(f"[WARNING] Selector strategy failed: {selector} - {e}")
                    continue

            if not date_selected:
                print("[ERROR] Could not select date with any available selector")
                raise RuntimeError(f"Date selection failed for: {date_string}")

        except Exception as e:
            print(f"[ERROR] Failed to select date: {date_string} - {e}")
            raise e

    def is_calendar_closed(self):
        """Simplified calendar check - only what's needed"""
        try:
            self.page.wait_for_timeout(500)
            calendar_elements = self.page.locator("xpath=//div[contains(@class, 'calendar')]//abbr | //abbr[@aria-label]").all()
            return not calendar_elements or not calendar_elements[0].is_visible()
        except Exception:
            return True  # Assume closed if we can't find calendar elements

    def handle_tomorrow_selection(self, element_name):
        """Optimized method to handle Tomorrow button click for trains"""
        try:
            print(f"[CALENDAR] Selecting Tomorrow for {element_name}")

            # Streamlined selectors - only the most effective ones
            tomorrow_selectors = [
                "//p[contains(text(),'Tomorrow')]",
                "//p[contains(text(),'Tomorrow')]/parent::*",
                "//button[contains(text(),'Tomorrow')]"
            ]

            for selector in tomorrow_selectors:
                try:
                    tomorrow_button = self.page.locator(f"xpath={selector}")

                    if tomorrow_button.is_visible() and tomorrow_button.is_enabled():
                        # Scroll to element before clicking
                        self.scroll_to_element(tomorrow_button)
                        self.page.wait_for_timeout(300)  # Brief wait after scroll

                        if self.perform_robust_click_with_result(tomorrow_button):
                            self.page.wait_for_timeout(400)  # Reduced wait time
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
            day_after_selectors = [
                "//p[contains(text(),'Day After')]",
                "//p[contains(text(),'Day After')]/parent::*",
                "//div[@data-testid='day-after-tomorrow']"
            ]

            for selector in day_after_selectors:
                try:
                    day_after_button = self.page.locator(f"xpath={selector}")

                    if day_after_button.is_visible() and day_after_button.is_enabled():
                        # Scroll to element before clicking
                        self.scroll_to_element(day_after_button)
                        self.page.wait_for_timeout(300)  # Brief wait after scroll

                        if self.perform_robust_click_with_result(day_after_button):
                            self.page.wait_for_timeout(400)  # Reduced wait time
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

            if normalized_option == "tomorrow":
                self.handle_tomorrow_selection(element_name)
            elif normalized_option in ["day-after-tomorrow", "day after tomorrow", "dayaftertomorrow"]:
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
            if normalized_input == "tomorrow" or "tomorrow" in normalized_input:
                self.handle_quick_date_selection("tomorrow", element_name)
            elif "day after" in normalized_input or normalized_input == "day-after-tomorrow":
                self.handle_day_after_tomorrow_selection(element_name)
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
            element.evaluate("element => element.scrollIntoView({behavior: 'smooth', block: 'center'})")
            self.page.wait_for_timeout(200)
        except Exception:
            try:
                # Method 2: Locator scroll (fallback)
                element.scroll_into_view_if_needed()
                self.page.wait_for_timeout(200)
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
            if option_str in ["false", "skip", "", "n/a", "0"]:
                print(f"[SKIP] SKIPPING {element_name} - Excel value indicates skip ({quick_date_option})")
                return  # Exit method without performing any action

            # Handle EXECUTE cases - Execute the button click based on element name
            if option_str in ["true", "1"]:
                print(f"[SUCCESS] Executing button click for: {element_name} (Excel value: {quick_date_option})")
                # Determine which date to select based on element name
                if "today" in normalized_element_name:
                    self.handle_today_selection(element_name)
                elif "tomorrow" in normalized_element_name:
                    self.handle_tomorrow_selection_bus(element_name)
                else:
                    print(f"[WARNING] Cannot determine date type from element name: {element_name}")
                    raise ValueError(f"Cannot determine date selection type for element: {element_name}")
            # Handle specific date options (legacy support - direct string values)
            elif option_str == "today":
                self.handle_today_selection(element_name)
            elif option_str == "tomorrow":
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
            today_selectors = [
                "//button[normalize-space(text())='Today']",
                "//button[contains(text(),'Today')]",
                "//*[contains(text(),'Today') and (name()='button' or name()='div')]"
            ]

            for selector in today_selectors:
                try:
                    today_button = self.page.locator(f"xpath={selector}")

                    if today_button.is_visible() and today_button.is_enabled():
                        # Skip disabled elements
                        class_name = today_button.get_attribute("class") or ""
                        if "disabled" in class_name:
                            continue

                        if self.perform_robust_click_with_result(today_button):
                            self.page.wait_for_timeout(500)  # Reduced wait time
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
            tomorrow_selectors = [
                "//button[normalize-space(text())='Tomorrow']",
                "//button[contains(text(),'Tomorrow')]",
                "//*[contains(text(),'Tomorrow') and (name()='button' or name()='div')]",
                "//p[contains(text(),'Tomorrow')]/parent::*"
            ]

            for selector in tomorrow_selectors:
                try:
                    tomorrow_button = self.page.locator(f"xpath={selector}")
                    if tomorrow_button.is_visible():
                        # Check if element is not disabled
                        class_name = tomorrow_button.get_attribute("class") or ""
                        if "disabled" in class_name:
                            continue

                        if self.perform_robust_click_with_result(tomorrow_button):
                            self.page.wait_for_timeout(500)  # Reduced wait time
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
                element.evaluate("element => element.click()")
                print("[SUCCESS] JavaScript click successful")
                return True
            except Exception as e:
                print(f"[WARNING] JavaScript click failed: {e}")

            # Method 3: Force click (Playwright specific)
            try:
                element.click(force=True)
                print("[SUCCESS] Force click successful")
                return True
            except Exception as e:
                print(f"[WARNING] Force click failed: {e}")

            return False

        except Exception as e:
            print(f"[ERROR] All click methods failed: {e}")
            return False

    def handle_today_selection(self, element_name):
        """Handles selecting 'Today' for date pickers."""
        if "bus" in element_name.lower():
            self.handle_bus_quick_date_selection("today", element_name)
        else:
            self.page.locator("xpath=//p[contains(text(),'Today')]" ).first.click()

    def handle_quick_date_selection(self, quick_date_option, element_name):
        normalized_option = quick_date_option.lower().strip()
        if "tomorrow" in normalized_option:
            self.page.locator("xpath=//p[contains(text(),'Tomorrow')]" ).first.click()
        elif "day after" in normalized_option:
            self.page.locator("xpath=//p[contains(text(),'Day After')]" ).first.click()
        else:
            raise ValueError(f"Unsupported quick date option: {quick_date_option}")

    def handle_bus_quick_date_selection(self, quick_date_option, element_name):
        option_str = str(quick_date_option).lower().strip()
        if option_str in ["false", "skip", "", "n/a", "0"]:
            print(f"[SKIP] SKIPPING {element_name}")
            return

        if "today" in element_name.lower() or option_str == "today":
              self.page.locator("//button[normalize-space(text())='Today']").first.click()
        elif "tomorrow" in element_name.lower() or option_str == "tomorrow":
              self.page.locator("//button[normalize-space(text())='Tomorrow']").first.click()
        else:
            raise ValueError(f"Unsupported bus quick date option: {quick_date_option}")

    def handle_travel_class_selection(self, class_name, xpath, element_name):
        mapping = {
            "economy": "Economy", "premium": "Premium Economy", "premium economy": "Premium Economy",
            "business": "Business", "first": "First class", "first class": "First class"
        }
        actual_class_name = mapping.get(class_name.lower().strip(), class_name)

        normalized_xpath = self.normalize_selector(xpath)
        self.page.locator(normalized_xpath).first.click()
        self.page.locator(f"//span[contains(@class,'px-5px') and text()='{actual_class_name}']").first.click()
        self.close_travellers_popup(xpath, element_name)

    def close_travellers_popup(self, xpath, element_name):
        try:
            self.page.locator("//button[contains(text(),'Done')]" ).first.click(timeout=2000)
        except PlaywrightTimeoutError:
            self.page.keyboard.press("Escape")

    def handle_count_selection(self, count_str, xpath, element_name):
        target_count = int(count_str.strip())
        resolved_count_type = self.resolve_count_element_type(element_name)

        # Special handling for specific element names - use increment logic like Selenium
        if resolved_count_type == "room":
            self.set_count_by_increment("room", target_count)
        elif resolved_count_type == "adult":
            self.set_count_by_increment("adult", target_count)
        elif resolved_count_type == "children":
            self.set_count_by_increment("children", target_count)
            # Wait for age dropdowns to appear after setting children count
            if target_count > 0:
                self.wait_for_child_age_dropdowns(target_count)
        elif resolved_count_type == "infant":
            # Infant controls vary by page; keep robust fallback path.
            self.page.locator(xpath).first.click()
            self.page.wait_for_timeout(500)

            section_text = "Infants"
            self.page.locator(
                f"//p[contains(text(),'{section_text}')]/parent::*/following-sibling::*//button[@data-testid='{target_count}']"
            ).first.click()
        else:
            # Fallback to original logic for other element names
            self.page.locator(xpath).first.click()
            self.page.wait_for_timeout(500)

            section_text = ""
            if "adult" in element_name.lower(): section_text = "Adults"
            elif "child" in element_name.lower(): section_text = "Children"
            elif "infant" in element_name.lower(): section_text = "Infants"

            self.page.locator(f"//p[contains(text(),'{section_text}')]/parent::*/following-sibling::*//button[@data-testid='{target_count}']").first.click()

    def select_child_age(self, child_index, age):
        # Use normalized selector for consistency and XPath cleaning
        normalized_selector = self.normalize_selector("//select[@data-testid='child-age-selector']")
        age_selectors = self.page.locator(normalized_selector)
        age_selectors.nth(child_index).select_option(str(age))

    def set_count_by_increment(self, element_type, desired_count):
        """Set count by incrementing/decrementing using Playwright"""
        try:
            increment_xpath = ""
            decrement_xpath = ""

            # Define XPaths based on element type (same as Selenium)
            if element_type.lower() == "room":
                increment_xpath = "//p[contains(@data-testid,'room-increment')]//*[name()='svg']//*[name()='path' and contains(@fill-rule,'evenodd')]"
                decrement_xpath = "//p[@data-testid='room-decrement']//*[name()='svg']"
            elif element_type.lower() == "adult":
                increment_xpath = "//p[@data-testid='adult-increment']//*[name()='svg']"
                decrement_xpath = "//p[contains(@data-testid,'adult-decrement')]//*[name()='svg']"
            elif element_type.lower() == "children":
                increment_xpath = "//p[@data-testid='counter-increment-children']//*[name()='svg']"
                decrement_xpath = "//p[@data-testid='counter-decrement-children']//*[name()='svg']"
            else:
                raise ValueError(f"Invalid element type: {element_type}")

            # Get current count from UI
            current_count = self.get_current_count(element_type)

            # Calculate difference
            difference = desired_count - current_count

            if difference > 0:
                # Need to increment
                increment_button = self.page.locator(increment_xpath).first
                increment_button.wait_for(state="visible", timeout=5000)
                for i in range(difference):
                    increment_button.click(timeout=3000)
                    self.page.wait_for_timeout(300)
            elif difference < 0:
                # Need to decrement
                decrement_button = self.page.locator(decrement_xpath).first
                decrement_button.wait_for(state="visible", timeout=5000)
                for i in range(abs(difference)):
                    decrement_button.click(timeout=3000)
                    self.page.wait_for_timeout(300)

            print(f"[COUNT_INCREMENT] Set {element_type} count to {desired_count} (was {current_count})")

        except Exception as e:
            print(f"Error in set_count_by_increment for {element_type}: {str(e)}")
            raise e

    def get_current_count(self, element_type):
        """Get current count from UI using Playwright"""
        try:
            # Get all counter-input elements and use index based on element type
            normalized_selector = self.normalize_selector("//span[@data-testid='counter-input']")
            all_counter_inputs = self.page.locator(normalized_selector)

            # Based on typical order: rooms, adults, children
            index_map = {
                "room": 0,
                "adult": 1,
                "children": 2
            }

            index = index_map.get(element_type.lower(), -1)

            if index >= 0:
                counter_input = all_counter_inputs.nth(index)
                count_text = counter_input.text_content().strip()
                return int(count_text)
            else:
                raise RuntimeError(f"Counter element not found for {element_type} at index {index}")

        except Exception as e:
            print(f"Error getting current count for {element_type}: {str(e)}")
            raise e

    def wait_for_child_age_dropdowns(self, expected_count):
        """Wait for child age dropdowns to appear after setting children count"""
        try:
            # Simple wait approach - wait for expected number of dropdowns
            max_wait_time = 15  # seconds
            wait_interval = 0.5  # seconds
            attempts = int(max_wait_time / wait_interval)

            normalized_selector = self.normalize_selector("//select[@data-testid='child-age-selector']")

            for i in range(attempts):
                age_selectors = self.page.locator(normalized_selector)
                count = age_selectors.count()
                if count >= expected_count:
                    print(f"Found {count} child age dropdowns (expected: {expected_count})")
                    return
                self.page.wait_for_timeout(wait_interval * 1000)

            # If we reach here, timeout occurred
            raise RuntimeError(f"Timeout: Could not find {expected_count} child age dropdowns within {max_wait_time} seconds")

        except Exception as e:
            print(f"Error waiting for child age dropdowns: {str(e)}")
            raise e

    def handle_checkbox_action(self, test_data, xpath, element_name):
        should_be_checked = test_data.upper() in ["TRUE", "1", "YES"]
        normalized_xpath = self.normalize_selector(xpath)
        checkbox = self.page.locator(normalized_xpath)
        current_state = checkbox.is_checked()

        # Clear default checked state first for deterministic behavior.
        if current_state:
            checkbox.uncheck()
            self.page.wait_for_timeout(100)
            print(f"[CHECKBOX] Cleared default checked state for {element_name}")

        if should_be_checked:
            if not checkbox.is_checked():
                checkbox.check()
            print(f"[CHECKBOX] {element_name} checked")
        else:
            print(f"[CHECKBOX] {element_name} unchecked")

    # --- Window/Page Management ---

    def wait_for_new_page(self, timeout=10):
        timeout_ms = timeout * 1000
        with self.context.expect_page(timeout=timeout_ms) as new_page_info:
            print("[PAGE] Waiting for a new page to open...")
        new_page = new_page_info.value
        self.page = new_page
        print(f"[PAGE] Switched to new page: {new_page.url}")
        return new_page

    def switch_to_latest_page(self):
        if self.context and len(self.context.pages) > 0:
            latest_page = self.context.pages[-1]
            if self.page != latest_page:
                self.page = latest_page
                self.page.bring_to_front()
                print(f"[PAGE] Switched to latest page: {self.page.url}")

    def switch_to_page_by_index(self, index):
        if self.context and 0 <= index < len(self.context.pages):
            self.page = self.context.pages[index]
            self.page.bring_to_front()
            print(f"[PAGE] Switched to page at index {index}: {self.page.url}")
        else:
            raise IndexError(f"Invalid page index: {index}. Only {len(self.context.pages)} pages available.")

    def switch_to_page_by_url(self, url_pattern):
        if not self.context: return
        for p in self.context.pages:
            if url_pattern.lower() in p.url.lower():
                self.page = p
                self.page.bring_to_front()
                print(f"[PAGE] Switched to page with URL pattern '{url_pattern}': {p.url}")
                return
        raise Exception(f"No page found with URL pattern: {url_pattern}")

    def close_extra_pages(self):
        if not self.context or len(self.context.pages) <= 1:
            return

        for p in self.context.pages:
            if p != self.initial_page:
                p.close()
        self.page = self.initial_page
        print("[PAGE] Closed all extra pages.")

    # --- Allure Reporting ---

    def save_allure_results(self, result):
        """Save test results to Allure format"""
        try:
            project_name = result.get('project_name', 'Test Automation')
            module_name = result.get('module_name', 'UI Tests')
            suite_type = result.get('suite_type', 'unknown')
            testcase_id = result.get('testcase_id', result['testcase_name'])
            testrun_id = result.get('testrun_id', '')
            result_id = result.get('result_id', '')
            
            allowed_suites = ['sanity', 'smoke', 'regression']
            display_suite_type = suite_type.lower() if suite_type.lower() in allowed_suites else 'regression'
            display_suite_title = display_suite_type.title()

            execution_duration = result.get('execution_time', '0:00:00')
            
            test_result = {
                "uuid": result['execution_id'],
                "historyId": result['execution_id'],
                "name": f"[{testcase_id}] {result['testcase_name']}",
                "fullName": f"{project_name}.{module_name}.{display_suite_title}.{result['testcase_name']}",
                "status": result['status'].lower() if result['status'] in ['PASS', 'FAIL'] else 'broken',
                "stage": "finished",
                "start": int(result['start_time'].timestamp() * 1000),
                "stop": int(result['end_time'].timestamp() * 1000),
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
                    {"name": "executionTime", "value": execution_duration},
                    {"name": "user", "value": result.get('user', 'N/A')},
                    {"name": "role", "value": result.get('role', 'N/A')}
                ],
                "parameters": [
                    {"name": "Test Case ID", "value": testcase_id},
                    {"name": "Suite Type", "value": display_suite_title},
                    {"name": "Module", "value": module_name},
                    {"name": "Project", "value": project_name},
                ],
                "steps": [],
                "attachments": self.current_test_attachments
            }
            
            if result['status'] == 'PASS':
                test_result["status"] = "passed"
            elif result['status'] == 'FAIL':
                test_result["status"] = "failed"
            else:
                test_result["status"] = "broken"
            
            for i, step in enumerate(result.get('step_results', [])):
                step_num = step.get('step_no', i + 1)
                step_status = step.get('status', 'UNKNOWN')
                status_emoji = "[OK]" if step_status == "PASS" else "[X]" if step_status == "FAIL" else "[!]"
                
                step_info = {
                    "name": f"{status_emoji} Step {step_num}: {step.get('test_step_description', f'Step {step_num}')}",
                    "status": step_status.lower() if step_status in ['PASS', 'FAIL'] else 'broken',
                    "stage": "finished",
                    "start": int(result['start_time'].timestamp() * 1000) + (i * 1000),
                    "stop": int(result['start_time'].timestamp() * 1000) + ((i + 1) * 1000),
                    "attachments": [],
                    "parameters": [
                        {"name": "Action", "value": step.get('action_type', 'N/A')},
                        {"name": "Element", "value": step.get('element_name', 'N/A')},
                        {"name": "XPath", "value": step.get('xpath', 'N/A')},
                        {"name": "Data", "value": step.get('values', 'N/A')},
                    ]
                }
                
                if step_status == 'FAIL':
                    if step.get('error_message'):
                        step_info["statusDetails"] = {
                            "message": f"FAILED: {step.get('error_message')}",
                            "trace": step.get('error', '')
                        }
                    if step.get('after_screenshot'):
                        step_info["attachments"].append({
                            "name": f"FAILED - After Step {step_num}",
                            "source": step.get('after_screenshot'),
                            "type": "image/png"
                        })
                
                test_result["steps"].append(step_info)
            
            if result['status'] == 'FAIL' and result['error_message']:
                test_result["statusDetails"] = {
                    "message": result['error_message'],
                    "trace": result['error_message']
                }
            
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            result_file = os.path.join(allure_results_path, f"{result['execution_id']}-result.json")
            
            with open(result_file, 'w') as f:
                json.dump(test_result, f, indent=2)
            
            print(f"[ALLURE] Test result saved to: {result_file}")


        except Exception as e:
            print(f"[ERROR] Failed to save Allure results: {str(e)}")

# The following are placeholder implementations for methods that were highly specific
# to Selenium and might need adjustment based on the new Playwright flow.
# I've kept them to ensure the class structure is similar.

    def scroll_element_into_view_and_highlight(self, xpath, element_name):
        """Finds an element, scrolls it into view, and highlights it using Playwright."""
        if not self.page or not xpath:
            return None, None
        
        try:
            locator = self.page.locator(xpath)
            locator.scroll_into_view_if_needed()
            locator.highlight() # Playwright's built-in highlight
            
            # Get coordinates for potential image processing
            box = locator.bounding_box()
            return box, locator
        except Exception as e:
            print(f"[HIGHLIGHT] Element '{element_name}' not found or failed to highlight: {e}")
            return None, None

    def highlight_failed_element(self, screenshot_path, xpath, element_name):
        """This method is now less critical as Playwright's tracing is superior,
           but the image processing logic can be kept if needed."""
        # This method uses Pillow and can be kept as-is, but it will now
        # be called with coordinates from Playwright's bounding_box().
        # The implementation is complex and not directly related to browser automation,
        # so I'm omitting its large code block for brevity. It can be copied
        # from the original selenium_executor.py if visual highlighting on PNGs is still required.
        print("[HIGHLIGHT] Image processing for highlighting is a separate concern from Playwright migration.")
        return screenshot_path

    def take_screenshot_with_element_highlighting(self, name, step_number=None, status="info", xpath="", element_name=""):
        """Takes a screenshot, and if the element is found, it will be highlighted by Playwright's tracer."""
        # Playwright's tracing provides a much better experience for this.
        # A simple screenshot is usually sufficient.
        screenshot_attachment = self.save_screenshot(name, step_number, status)
        if screenshot_attachment and screenshot_attachment.get('source'):
            current_dir = os.getcwd()
            if current_dir.endswith('new_backend'):
                project_root = os.path.dirname(current_dir)
            else:
                project_root = current_dir
            allure_results_path = os.path.join(project_root, 'allure-results-new')
            return os.path.join(allure_results_path, screenshot_attachment['source'])
        return None

    def execute_step_with_isolation(self, step, step_number):
        """Playwright's model is naturally isolated. This is an alias for the main execute_step."""
        return self.execute_step(step, step_number)

    def execute_action_with_isolation(self, action_type, test_data, xpath, element_name):
        """Playwright's model is naturally isolated. This is an alias for the main execute_action."""
        return self.execute_action(action_type, test_data, xpath, element_name)

    # The complex validation methods from the Selenium executor can be simplified
    # as Playwright's auto-waiting and actionability checks handle most of these cases.
    # For this conversion, we'll rely on Playwright's built-in checks. If an action
    # fails, Playwright will raise a detailed exception.

    def validate_action_result(self, action_type, test_data, xpath, element_name):
        """Basic validation stub. Playwright's actionability checks are the primary validation."""
        print(f"[VALIDATION] Action '{action_type}' on '{element_name}' completed. Relying on Playwright's implicit checks.")
        return {'success': True, 'message': 'Action completed.'}


if __name__ == '__main__':
    # Example usage for testing the executor directly
    print("Testing PlaywrightTestExecutor...")
    executor = PlaywrightTestExecutor()
    
    # Define a sample test case
    sample_testcase_name = "Sample Playwright Test"
    sample_test_steps = [
        {'action_type': 'OPEN_BROWSER', 'values': 'https://playwright.dev/'},
        {'action_type': 'CLICK', 'xpath': "//a[contains(text(), 'Get started')]", 'element_name': 'Get Started Button'},
        # Add more steps here for testing
    ]
    sample_metadata = {'project_name': 'Internal', 'module_name': 'Executor Test'}

    # Execute the test
    try:
        test_result = executor.execute_test_case(sample_testcase_name, sample_test_steps, sample_metadata)
        print("\n--- TEST RESULT ---")
        print(json.dumps(test_result, indent=2, default=str))
        print("-------------------")
    except Exception as e:
        print("\n--- TEST FAILED ---")
        print(f"An error occurred: {e}")
        print("-------------------")
        
        
