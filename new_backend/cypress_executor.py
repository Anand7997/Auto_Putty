import os
import json
import uuid
from datetime import datetime, timezone
import traceback
import re
import subprocess
import time
import pytz
import tempfile
import shutil
import sys
from time import localtime, strftime

class CypressTestExecutor:
    def __init__(self, enable_isolation=True, server_execution=False, vnc_session=None, display_id=None, headless=False):
        self.setup_allure_results_directory()
        self.current_test_attachments = []
        self.enable_isolation = enable_isolation
        self.server_execution = server_execution
        self.vnc_session = vnc_session
        self.display_id = display_id  # VNC-assigned display ID
        self.headless = headless  # Headless mode setting (default: False = window opens)
        self.default_wait_timeout = int(os.getenv("CYPRESS_WAIT_TIMEOUT_SECONDS", "15"))
        self.default_step_timeout = int(os.getenv("CYPRESS_STEP_TIMEOUT_SECONDS", "45"))

        # If VNC/display is set, force headed mode for VNC streaming (like Selenium)
        if self.display_id or self.vnc_session:
            self.headless = False
            print(f"[INIT] Headless DISABLED because VNC/streaming is enabled")
        elif self.server_execution:
            self.headless = True
            print(f"[INIT] Forced headless mode for server execution")

        # Set DISPLAY environment variable using VNC-assigned display
        if self.display_id:
            os.environ["DISPLAY"] = self.display_id
            print(f"[DISPLAY] Using VNC-assigned display {self.display_id}")

        print(f"[INIT] Cypress Test Executor initialized with isolation mode: {'ENABLED' if enable_isolation else 'DISABLED'}")
        print(f"[INIT] Server execution mode: {'ENABLED' if server_execution else 'DISABLED'}")
        print(f"[INIT] VNC session: {'AVAILABLE' if vnc_session else 'NONE'}")
        print(f"[INIT] Headless mode: {'DISABLED - Window will open' if not self.headless else 'ENABLED'}")
        print(f"[INIT] Default wait timeout: {self.default_wait_timeout}s")
        print(f"[INIT] Default step timeout: {self.default_step_timeout}s")

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

            self.allure_results_path = allure_results_path
            env_file = os.path.join(allure_results_path, 'environment.properties')
            with open(env_file, 'w') as f:
                f.write("Browser=Chrome\n")
                f.write("Platform=Windows\n")
                f.write("Base_URL=https://www.ixigo.com\n")
                f.write("Database=Ixigo_TestAutomation\n")
                f.write("Framework=Cypress\n")
                f.write(f"Test_Environment=Development\n")
                f.write(f"Execution_Date=\n")

        except Exception as e:
            print(f"[ERROR] Failed to setup allure-results directory: {str(e)}")

    def get_local_time_string(self):
        """Get current local time as formatted string"""
        return strftime('%m/%d/%Y %I:%M:%S %p', localtime())

    def update_execution_date(self, execution_start_time=None):
        """Update execution date in environment.properties with actual test start time"""
        try:
            env_file = os.path.join(self.allure_results_path, 'environment.properties')
            with open(env_file, 'r') as f:
                lines = f.readlines()
            
            execution_time_str = self.get_local_time_string()
            
            with open(env_file, 'w') as f:
                for line in lines:
                    if line.startswith('Execution_Date='):
                        f.write(f"Execution_Date={execution_time_str}\n")
                    else:
                        f.write(line)
            
            print(f"[EXECUTION_DATE] Updated execution date to: {execution_time_str}")
        except Exception as e:
            print(f"[ERROR] Failed to update execution date: {str(e)}")

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

    def generate_cypress_test_file(self, testcase_name, test_steps, execution_id):
        """Generate a Cypress test file from test steps"""
        try:
            # Create a temporary directory for Cypress tests
            self.cypress_test_dir = tempfile.mkdtemp(prefix=f"cypress_test_{execution_id}_")
            print(f"[CYPRESS] Created test directory: {self.cypress_test_dir}")

            # Create cypress.config.js with performance optimizations
            config_content = f"""
import {{ defineConfig }} from 'cypress'

export default defineConfig({{
  e2e: {{
    viewportWidth: 1280,
    viewportHeight: 720,
    defaultCommandTimeout: {self.default_wait_timeout * 1000},
    requestTimeout: {self.default_wait_timeout * 1000},
    responseTimeout: {self.default_wait_timeout * 1000},
    pageLoadTimeout: {self.default_step_timeout * 1000},
    video: false,
    screenshotOnRunFailure: true,
    supportFile: 'cypress/support/e2e.js',
    chromeWebSecurity: false,
    numTestsKeptInMemory: 1,
    protocolVersion: 3,
    retries: {{
      runMode: 0,
      openMode: 0
    }},
    setupNodeEvents(on, config) {{
      on('before:browser:launch', (browser = {{}}, launchOptions) => {{
        if (browser.name === 'chrome' || browser.family === 'chromium') {{
          launchOptions.args.push('--disable-blink-features=AutomationControlled')
          launchOptions.args.push('--disable-infobars')
          launchOptions.args.push('--no-default-browser-check')
          launchOptions.args.push('--no-first-run')
          launchOptions.args.push('--disable-dev-shm-usage')
          launchOptions.args.push('--disable-background-networking')
          launchOptions.args.push('--disable-background-timer-throttling')
          launchOptions.args.push('--disable-renderer-backgrounding')
          launchOptions.args.push('--disable-popup-blocking')
          launchOptions.args.push('--window-size=1366,768')
        }}
        return launchOptions
      }})
      return config
    }},
    env: {{
      execution_id: '{execution_id}',
      testcase_name: '{testcase_name}'
    }}
  }},
  browser: {{
    name: 'chrome',
    launchOptions: {{
      args: ['--disable-gpu']
    }}
  }}
}})
"""
            config_path = os.path.join(self.cypress_test_dir, 'cypress.config.js')
            with open(config_path, 'w') as f:
                f.write(config_content)

            # Create cypress directory structure
            cypress_dir = os.path.join(self.cypress_test_dir, 'cypress')
            os.makedirs(cypress_dir)

            support_dir = os.path.join(cypress_dir, 'support')
            os.makedirs(support_dir)

            # Create support file with xpath plugin and custom commands
            support_content = """
try {
  require('cypress-xpath')
  console.log('cypress-xpath loaded successfully')
} catch (e) {
  console.warn('cypress-xpath not available, xpath commands may not work:', e.message)
}

Cypress.Commands.add('switchToFrame', (frameRef = '') => {
  const ref = `${frameRef || ''}`.trim()
  const normalized = ref.toLowerCase()
  if (!ref || ['default', 'main', 'top', 'parent', 'root'].includes(normalized)) {
    Cypress.env('qfastFrameRef', null)
    return cy.log('Switched to default content')
  }
  Cypress.env('qfastFrameRef', ref)
  return cy.log(`Active iframe context set to: ${ref}`)
})

Cypress.Commands.add('getActiveFrameBody', () => {
  const frameRef = Cypress.env('qfastFrameRef')
  if (!frameRef) {
    return cy.get('body')
  }

  const ref = `${frameRef}`.trim()
  const lowerRef = ref.toLowerCase()

  if (lowerRef.startsWith('index:')) {
    const index = Number(lowerRef.split(':')[1] || 0)
    return cy.get('iframe').eq(index).its('0.contentDocument.body').should('not.be.empty').then(cy.wrap)
  }

  if (lowerRef.startsWith('xpath=') || ref.startsWith('/') || ref.startsWith('.//') || ref.startsWith('(')) {
    const xpathSelector = lowerRef.startsWith('xpath=') ? ref.slice(6) : ref
    if (!cy.xpath) {
      throw new Error('cypress-xpath plugin not loaded. Install with: npm install cypress-xpath')
    }
    return cy.xpath(xpathSelector).first().its('0.contentDocument.body').should('not.be.empty').then(cy.wrap)
  }

  const cssSelector = lowerRef.startsWith('css=') ? ref.slice(4) : ref
  return cy.get(cssSelector).first().its('0.contentDocument.body').should('not.be.empty').then(cy.wrap)
})

Cypress.Commands.add('xpathOrCSS', (selector, isXPath = true) => {
  const frameRef = Cypress.env('qfastFrameRef')
  if (frameRef) {
    if (isXPath) {
      return cy.getActiveFrameBody().then(($body) => {
        const doc = $body[0]?.ownerDocument || $body[0]
        const result = doc.evaluate(selector, doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null)
        const node = result.singleNodeValue
        if (!node) {
          throw new Error(`XPath not found in iframe: ${selector}`)
        }
        return cy.wrap(node)
      })
    }
    return cy.getActiveFrameBody().find(selector)
  }

  if (isXPath) {
    if (cy.xpath) {
      return cy.xpath(selector)
    } else {
      throw new Error('cypress-xpath plugin not loaded. Install with: npm install cypress-xpath')
    }
  } else {
    return cy.get(selector)
  }
})

Cypress.Commands.add('visitStealth', (url, options = {}) => {
  Cypress.env('qfastFrameRef', null)
  const visitOptions = {
    failOnStatusCode: false,
    ...options,
    onBeforeLoad(win) {
      try {
        Object.defineProperty(win.navigator, 'webdriver', { get: () => false })
      } catch (e) {}
      try {
        Object.defineProperty(win.navigator, 'language', { get: () => 'en-US' })
        Object.defineProperty(win.navigator, 'languages', { get: () => ['en-US', 'en'] })
      } catch (e) {}
      try {
        Object.defineProperty(win.navigator, 'platform', { get: () => 'Win32' })
      } catch (e) {}
      try {
        Object.defineProperty(win.navigator, 'plugins', {
          get: () => [1, 2, 3, 4, 5]
        })
      } catch (e) {}
      try {
        if (!win.chrome) {
          win.chrome = { runtime: {} }
        }
      } catch (e) {}
      if (options.onBeforeLoad) {
        options.onBeforeLoad(win)
      }
    }
  }
  return cy.visit(url, visitOptions)
})

Cypress.Commands.overwrite('scrollIntoView', (originalFn, subject, options) => {
  try {
    if (!subject) {
      return originalFn(subject, options)
    }

    const $subject = Cypress.$(subject)
    if ($subject.length <= 1) {
      return originalFn(subject, options)
    }

    const $visible = $subject.filter(':visible')
    const $chosen = $visible.length > 0 ? $visible.first() : $subject.first()
    Cypress.log({
      name: 'scrollIntoView',
      message: `matched ${$subject.length} elements; using one element for Cypress compatibility`,
    })
    return originalFn($chosen, options)
  } catch (e) {
    return originalFn(subject, options)
  }
})

Cypress.on('uncaught:exception', (err, runnable) => {
  return false
})
"""
            support_file = os.path.join(support_dir, 'e2e.js')
            with open(support_file, 'w') as f:
                f.write(support_content)

            e2e_dir = os.path.join(cypress_dir, 'e2e')
            os.makedirs(e2e_dir)

            # Create package.json to ensure cypress-xpath is available
            package_json_content = """{
  "name": "cypress-test",
  "version": "1.0.0",
  "devDependencies": {
    "cypress": "^15.0.0",
    "cypress-xpath": "^2.0.1"
  }
}
"""
            package_json_path = os.path.join(self.cypress_test_dir, 'package.json')
            with open(package_json_path, 'w') as f:
                f.write(package_json_content)

            # Generate the test file
            test_content = self.generate_cypress_test_content(testcase_name, test_steps, execution_id)
            test_file_path = os.path.join(e2e_dir, f'{execution_id}.cy.js')

            with open(test_file_path, 'w') as f:
                f.write(test_content)

            print(f"[CYPRESS] Generated test file: {test_file_path}")
            
            # Log the test file content for debugging
            with open(test_file_path, 'r') as f:
                file_content = f.read()
                print(f"[CYPRESS] Test file content ({len(file_content)} bytes):")
                print(file_content)
            
            return self.cypress_test_dir

        except Exception as e:
            print(f"[ERROR] Failed to generate Cypress test file: {str(e)}")
            raise e

    def generate_cypress_test_content(self, testcase_name, test_steps, execution_id):
        """Generate Cypress test content from test steps"""
        try:
            print(f"[CYPRESS_GEN] Generating test content for {len(test_steps)} steps")
            
            if not test_steps:
                print("[CYPRESS_GEN] WARNING: No test steps provided!")
                # Return a minimal test that at least loads the page
                return f"""
describe('{testcase_name}', () => {{
  it('Load test page', () => {{
    cy.visitStealth('/')
  }})
}})
"""
            
            # Start building the test content
            first_step = test_steps[0] if test_steps else None
            first_action = first_step.get('action_type', '').upper() if first_step else ''
            
            # If first step is OPEN_BROWSER, use its URL instead of default
            if first_action == "OPEN_BROWSER":
                url = first_step.get('values', '/')
                visit_statement = f"cy.visitStealth('{self.escape_string_for_js(url)}')"
                start_index = 1  # Skip first step since we're handling it
            else:
                visit_statement = "cy.visitStealth('/')"
                start_index = 0
            
            test_content = f"""
describe('{testcase_name}', () => {{
  it('Execute test case steps', () => {{
    {visit_statement}

    // Test steps
"""

            for i, step in enumerate(test_steps, 1):
                if i < start_index + 1:  # Skip the first OPEN_BROWSER step we already handled
                    continue
                
                step_description = step.get('test_step_description', f'Step {i}')
                action_type = self.normalize_action_type(step.get('action_type', ''))
                xpath = step.get('xpath', '')
                element_name = step.get('element_name', '')
                test_data = step.get('values', '')

                print(f"[CYPRESS_GEN] Step {i}: action={action_type}, element={element_name}, data={test_data[:50] if test_data else ''}")

                # Add step comment
                test_content += f"""
    // Step {i}: {step_description}
"""

                # Generate Cypress command based on action type
                timeout_seconds = self._resolve_step_timeout_seconds(step)
                cypress_command = self.generate_cypress_command(action_type, xpath, element_name, test_data, i, timeout_seconds)
                print(f"[CYPRESS_GEN] Generated command: {cypress_command[:100]}")
                test_content += f"    {cypress_command}\n"

            # Close the test
            test_content += """
  })
})
"""

            print(f"[CYPRESS_GEN] Final test content length: {len(test_content)} chars")
            print(f"[CYPRESS_GEN] Test content preview:\n{test_content[:800]}")
            return test_content

        except Exception as e:
            print(f"[ERROR] Failed to generate Cypress test content: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e

    def escape_string_for_js(self, text):
        """Escape special characters for JavaScript string"""
        if not text:
            return ""
        text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "\\'")
        text = text.replace('"', '\\"')
        return text

    def normalize_action_type(self, action_type):
        """Normalize legacy action names to current supported action set."""
        normalized = (action_type or "").upper().strip()
        legacy_select_actions = {
            "CLICK_AND_SELECT_DATE",
            "CLICK_QUICK_DATE",
            "CLICK_BUS_QUICK_DATE",
            "CLICK_AND_SELECT_AGE",
        }
        if normalized in legacy_select_actions:
            return "CLICK_AND_SELECT"
        alias_map = {
            "SWITCH_FRAME": "SWITCH_TO_IFRAME",
            "SWITCH_TO_FRAME": "SWITCH_TO_IFRAME",
            "SWITCH_IFRAME": "SWITCH_TO_IFRAME",
        }
        return alias_map.get(normalized, normalized)

    def _resolve_step_timeout_seconds(self, step):
        """Resolve per-step timeout with a safe default."""
        try:
            raw_timeout = step.get("timeout_seconds", step.get("timeout", self.default_step_timeout))
            timeout_value = int(raw_timeout)
            return max(timeout_value, 1)
        except Exception:
            return self.default_step_timeout

    def _parse_drag_drop_target_locator(self, test_data):
        """Extract target locator for drag/drop from values payload."""
        raw = str(test_data or "").strip()
        if not raw:
            return None

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                for key in ["target_locator", "target_xpath", "target_selector", "target", "to"]:
                    value = payload.get(key)
                    if value and str(value).strip():
                        return str(value).strip()
        except Exception:
            pass

        kv_match = re.search(r"(?:target_locator|target_xpath|target_selector|target|to)\s*[:=]\s*(.+)$", raw, re.IGNORECASE)
        if kv_match:
            value = kv_match.group(1).strip().strip("'\"")
            return value or None

        return raw

    def _selector_command(self, locator):
        """Return JS snippet to resolve locator across xpath/css/id prefixes."""
        raw = str(locator or "").strip()
        if not raw:
            return "cy.get('body')"

        lowered = raw.lower()
        if lowered.startswith("xpath="):
            selector = self.escape_string_for_js(raw[6:])
            return f"cy.xpathOrCSS('{selector}', true)"
        if lowered.startswith("css="):
            selector = self.escape_string_for_js(raw[4:])
            return f"cy.get('{selector}')"
        if lowered.startswith("id="):
            selector = self.escape_string_for_js(raw[3:].lstrip('#'))
            return f"cy.get('#{selector}')"
        if lowered.startswith("name="):
            selector = self.escape_string_for_js(raw[5:])
            return f"cy.get('[name=\"{selector}\"]')"

        if raw.startswith(("/", "(", ".//")):
            selector = self.escape_string_for_js(raw)
            return f"cy.xpathOrCSS('{selector}', true)"
        if raw.startswith(("#", ".", "[")) or any(token in raw for token in [" ", ">", "~", ":", "*"]):
            selector = self.escape_string_for_js(raw)
            return f"cy.get('{selector}')"

        selector = self.escape_string_for_js(raw)
        return f"cy.xpathOrCSS('{selector}', true)"

    def generate_cypress_command(self, action_type, xpath, element_name, test_data, step_number, timeout_seconds=None):
        """Generate Cypress command for a specific action"""
        try:
            action_type = self.normalize_action_type(action_type)
            timeout_seconds = int(timeout_seconds or self.default_step_timeout)
            timeout_ms = max(timeout_seconds, 1) * 1000
            
            # Escape strings for JavaScript
            test_data_escaped = self.escape_string_for_js(test_data)
            selector_cmd = self._selector_command(xpath)
            test_data_text = str(test_data or "")

            if action_type == "OPEN_BROWSER":
                return f"cy.visitStealth('{test_data_escaped}')"

            elif action_type == "CLICK_AND_SELECT":
                # Handle different selection types
                selection_type = self.determine_selection_type(element_name, test_data)

                if selection_type == "CITY_SELECTION":
                    return self.generate_city_selection_command(xpath, element_name, test_data_escaped)
                elif selection_type == "DATE_SELECTION":
                    return self.generate_date_selection_command(xpath, element_name, test_data_escaped)
                elif selection_type == "QUICK_DATE_SELECTION":
                    return self.generate_quick_date_command(element_name, test_data_escaped)
                elif selection_type == "AGE_SELECTION":
                    return self.generate_age_selection_command(xpath, element_name, test_data_escaped)
                elif selection_type == "COUNT_SELECTION":
                    return self.generate_count_selection_command(test_data_escaped, xpath, element_name)
                else:
                    return f"{selector_cmd}.scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "CLICK_AND_TYPE":
                return f"{selector_cmd}.scrollIntoView().clear({{ force: true }}).type('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "CLEAR_AND_TYPE":
                return f"{selector_cmd}.scrollIntoView().clear({{ force: true }}).type('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "CLICK":
                if element_name.upper() == "TRAVELCLASS":
                    return self.generate_travel_class_command(test_data_escaped, xpath, element_name)
                elif element_name.upper() in ["DONEBUTTON", "DONE"]:
                    return "cy.contains('Done').first().click({ force: true })"
                elif test_data_text.upper() == "TODAY":
                    return f"cy.contains('Today').scrollIntoView().click({{ force: true }})"
                elif test_data_text.upper() == "TOMORROW":
                    return f"cy.contains('Tomorrow').scrollIntoView().click({{ force: true }})"
                else:
                    return f"{selector_cmd}.scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "DOUBLE_CLICK":
                return f"{selector_cmd}.scrollIntoView().dblclick({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "RIGHT_CLICK":
                return f"{selector_cmd}.scrollIntoView().rightclick({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "MOUSE_OVER":
                return f"{selector_cmd}.scrollIntoView().trigger('mouseover', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "RADIO_BUTTON":
                should_check = str(test_data or '').strip().lower() in ["", "true", "1", "yes", "on", "select", "selected"]
                if should_check:
                    return f"{selector_cmd}.scrollIntoView().check({{ force: true, timeout: {timeout_ms} }})"
                return f"{selector_cmd}.scrollIntoView().uncheck({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "DRAG_AND_DROP":
                target_locator = self._parse_drag_drop_target_locator(test_data)
                if not target_locator:
                    return "// DRAG_AND_DROP skipped: missing target locator"
                target_cmd = self._selector_command(target_locator)
                return (
                    f"{selector_cmd}.scrollIntoView().trigger('mousedown', {{ which: 1, force: true }}); "
                    f"{target_cmd}.scrollIntoView().trigger('mousemove', {{ force: true }}).trigger('mouseup', {{ force: true }})"
                )

            elif action_type == "HANDLE_CHECKBOX":
                should_check = test_data_text.upper() in ["TRUE", "1", "YES"]
                if should_check:
                    return (
                        f"{selector_cmd}.scrollIntoView()"
                        ".then(($el) => { if ($el.prop('checked')) { cy.wrap($el).uncheck({ force: true }); } })"
                        f".check({{ force: true, timeout: {timeout_ms} }})"
                    )
                else:
                    return (
                        f"{selector_cmd}.scrollIntoView()"
                        ".then(($el) => { if ($el.prop('checked')) { cy.wrap($el).uncheck({ force: true }); } })"
                    )

            elif action_type == "SELECT_COUNT":
                return self.generate_count_selection_command(test_data_escaped, xpath, element_name)

            elif action_type == "INCREMENT":
                return self.generate_increment_decrement_command("INCREMENT", test_data_escaped, xpath, element_name)

            elif action_type == "DECREMENT":
                return self.generate_increment_decrement_command("DECREMENT", test_data_escaped, xpath, element_name)

            elif action_type == "SWITCH_TO_IFRAME":
                frame_reference = str(xpath or test_data or "").strip()
                if str(test_data_text).strip().isdigit() and not str(xpath or "").strip():
                    frame_reference = f"index:{test_data_text.strip()}"
                frame_reference_escaped = self.escape_string_for_js(frame_reference)
                return f"cy.switchToFrame('{frame_reference_escaped}')"

            elif action_type == "NAVIGATE_TO_URL":
                return f"cy.visitStealth('{test_data_escaped}')"

            elif action_type == "REFRESH_PAGE":
                return "cy.reload()"

            elif action_type == "GO_BACK":
                return "cy.go('back')"

            elif action_type == "GO_FORWARD":
                return "cy.go('forward')"

            else:
                return f"// Unknown action type: {action_type}"

        except Exception as e:
            print(f"[ERROR] Failed to generate Cypress command for {action_type}: {str(e)}")
            return f"// Error generating command for {action_type}"

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
            count_element_names = {"ROOMSCOUNT", "ADULTSCOUNT", "CHILDRENCOUNT"}
            if element_name.upper() in count_element_names and test_data and str(test_data).strip().isdigit():
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

    def generate_city_selection_command(self, xpath, element_name, city_name):
        """Generate Cypress command for city selection"""
        selector_cmd = self._selector_command(xpath)
        return f"""
    {selector_cmd}.scrollIntoView().click({{ force: true }})
    {selector_cmd}.clear().type('{city_name}')
    cy.wait(1000)
    cy.get('body').type('{{downarrow}}{{enter}}')
    cy.wait(2000)"""

    def generate_date_selection_command(self, xpath, element_name, date_string):
        """Generate Cypress command for date selection"""
        selector_cmd = self._selector_command(xpath)
        return f"""
    {selector_cmd}.scrollIntoView().click({{ force: true }})
    cy.wait(1000)
    cy.contains('{date_string}').scrollIntoView().click({{ force: true }})
    cy.wait(1000)"""

    def generate_quick_date_command(self, element_name, quick_date_option):
        """Generate Cypress command for quick date selection"""
        normalized_option = quick_date_option.lower().strip()

        if normalized_option == "tomorrow":
            return "cy.contains('Tomorrow').scrollIntoView().click({ force: true })"
        elif normalized_option in ["day-after-tomorrow", "day after tomorrow"]:
            return "cy.contains('Day After').scrollIntoView().click({ force: true })"
        else:
            return f"cy.contains('{quick_date_option}').scrollIntoView().click({{ force: true }})"

    def generate_age_selection_command(self, xpath, element_name, age_value):
        """Generate Cypress command for child age selection."""
        selector_cmd = self._selector_command(xpath)
        return f"""
    {selector_cmd}.scrollIntoView().select('{age_value}', {{ force: true }})
    cy.wait(500)"""

    def generate_travel_class_command(self, class_name, xpath, element_name):
        """Generate Cypress command for travel class selection"""
        mapping = {
            "economy": "Economy",
            "premium": "Premium Economy",
            "premium economy": "Premium Economy",
            "business": "Business",
            "first": "First class",
            "first class": "First class"
        }
        actual_class_name = mapping.get(class_name.lower().strip(), class_name)
        selector_cmd = self._selector_command(xpath)

        return f"""
    {selector_cmd}.scrollIntoView().click({{ force: true }})
    cy.wait(500)
    cy.contains('{actual_class_name}').scrollIntoView().click({{ force: true }})
    cy.wait(500)
    cy.contains('Done').scrollIntoView().click({{ force: true }})"""

    def generate_count_selection_command(self, count_str, xpath, element_name):
        """Generate Cypress command for count selection"""
        try:
            target_count = int(count_str.strip())
            element_type = self.resolve_count_element_type(element_name)
            if element_type:
                return f"""
    {self.generate_increment_decrement_command("SELECT_COUNT", str(target_count), xpath, element_name)}
    cy.contains('Done').scrollIntoView().click({{ force: true }})"""
            selector_cmd = self._selector_command(xpath)
            return f"{selector_cmd}.scrollIntoView().click({{ force: true }})"

        except Exception as e:
            print(f"[ERROR] Failed to generate count selection command: {str(e)}")
            selector_cmd = self._selector_command(xpath)
            return f"{selector_cmd}.scrollIntoView().click({{ force: true }})"

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

    def _get_count_control_xpaths(self, element_type):
        element_type = (element_type or "").lower()
        if element_type == "room":
            return (
                "//p[contains(@data-testid,'room-increment')]//*[name()='svg']//*[name()='path' and contains(@fill-rule,'evenodd')]",
                "//p[@data-testid='room-decrement']//*[name()='svg']"
            )
        if element_type == "adult":
            return (
                "//p[@data-testid='adult-increment']//*[name()='svg']",
                "//p[contains(@data-testid,'adult-decrement')]//*[name()='svg']"
            )
        if element_type == "children":
            return (
                "//p[@data-testid='counter-increment-children']//*[name()='svg']",
                "//p[@data-testid='counter-decrement-children']//*[name()='svg']"
            )
        if element_type == "infant":
            return (
                "//p[@data-testid='counter-increment-infant']//*[name()='svg'] | //p[contains(@data-testid,'infant-increment')]//*[name()='svg']",
                "//p[@data-testid='counter-decrement-infant']//*[name()='svg'] | //p[contains(@data-testid,'infant-decrement')]//*[name()='svg']"
            )
        return (None, None)

    def _get_count_input_index(self, element_type):
        index_map = {
            "room": 0,
            "adult": 1,
            "children": 2,
            "infant": 3,
        }
        return index_map.get((element_type or "").lower(), None)

    def generate_increment_decrement_command(self, action_type, count_str, xpath, element_name):
        """Generate Cypress command for INCREMENT/DECREMENT/SELECT_COUNT."""
        try:
            parsed_count = int(str(count_str).strip() or "1")
            if parsed_count < 0:
                parsed_count = 0

            element_type = self.resolve_count_element_type(element_name)
            if element_type:
                inc_xpath, dec_xpath = self._get_count_control_xpaths(element_type)
                inc_cmd = self._selector_command(f"xpath={inc_xpath}") if inc_xpath else None
                dec_cmd = self._selector_command(f"xpath={dec_xpath}") if dec_xpath else None
                count_index = self._get_count_input_index(element_type)

                if count_index is not None:
                    if action_type == "INCREMENT" and inc_cmd:
                        return f"""cy.get('body').then(() => {{
      const _target = {parsed_count};
      const _currentText = (Cypress.$("span[data-testid='counter-input']").eq({count_index}).text() || '').trim();
      const _current = Number.parseInt(_currentText, 10) || 0;
      const _steps = Math.max(_target - _current, 0);
      for (let i = 0; i < _steps; i += 1) {{ {inc_cmd}.click({{ force: true }}); cy.wait(200); }}
    }})"""
                    if action_type == "DECREMENT" and dec_cmd:
                        return f"""cy.get('body').then(() => {{
      const _target = {parsed_count};
      const _currentText = (Cypress.$("span[data-testid='counter-input']").eq({count_index}).text() || '').trim();
      const _current = Number.parseInt(_currentText, 10) || 0;
      const _steps = Math.max(_current - _target, 0);
      for (let i = 0; i < _steps; i += 1) {{ {dec_cmd}.click({{ force: true }}); cy.wait(200); }}
    }})"""
                    if action_type == "SELECT_COUNT" and (inc_cmd or dec_cmd):
                        if inc_cmd and dec_cmd:
                            return f"""cy.get('body').then(() => {{
      const _target = {parsed_count};
      const _currentText = (Cypress.$("span[data-testid='counter-input']").eq({count_index}).text() || '').trim();
      const _current = Number.parseInt(_currentText, 10) || 0;
      if (_target > _current) {{
        for (let i = 0; i < (_target - _current); i += 1) {{ {inc_cmd}.click({{ force: true }}); cy.wait(200); }}
      }} else if (_target < _current) {{
        for (let i = 0; i < (_current - _target); i += 1) {{ {dec_cmd}.click({{ force: true }}); cy.wait(200); }}
      }}
    }})"""
                        if inc_cmd:
                            return f"""cy.get('body').then(() => {{
      const _target = {parsed_count};
      const _currentText = (Cypress.$("span[data-testid='counter-input']").eq({count_index}).text() || '').trim();
      const _current = Number.parseInt(_currentText, 10) || 0;
      const _steps = Math.max(_target - _current, 0);
      for (let i = 0; i < _steps; i += 1) {{ {inc_cmd}.click({{ force: true }}); cy.wait(200); }}
    }})"""
                        if dec_cmd:
                            return f"""cy.get('body').then(() => {{
      const _target = {parsed_count};
      const _currentText = (Cypress.$("span[data-testid='counter-input']").eq({count_index}).text() || '').trim();
      const _current = Number.parseInt(_currentText, 10) || 0;
      const _steps = Math.max(_current - _target, 0);
      for (let i = 0; i < _steps; i += 1) {{ {dec_cmd}.click({{ force: true }}); cy.wait(200); }}
    }})"""

            selector_cmd = self._selector_command(xpath)
            return f"for (let i = 0; i < {parsed_count}; i += 1) {{ {selector_cmd}.click({{ force: true }}); cy.wait(200); }}"
        except Exception as e:
            print(f"[ERROR] Failed to generate {action_type} command: {str(e)}")
            return "// Failed to generate increment/decrement command"

    def run_cypress_test(self, test_dir, execution_id, test_steps=None):
        """Run the Cypress test and capture results"""
        try:
            print(f"[CYPRESS] Running Cypress test in directory: {test_dir}")
            print(f"[CYPRESS] Execution ID: {execution_id}")
            print(f"[CYPRESS] Test steps count: {len(test_steps) if test_steps else 0}")
            
            # Verify test directory exists
            if not os.path.exists(test_dir):
                raise Exception(f"Test directory does not exist: {test_dir}")
            
            # Verify test file exists
            test_file_path = os.path.join(test_dir, 'cypress', 'e2e', f'{execution_id}.cy.js')
            if not os.path.exists(test_file_path):
                raise Exception(f"Test file does not exist: {test_file_path}")
            
            print(f"[CYPRESS] Test file verified: {test_file_path}")
            print(f"[CYPRESS] Test file size: {os.path.getsize(test_file_path)} bytes")

            # Change to the test directory
            original_dir = os.getcwd()
            os.chdir(test_dir)

            # Install dependencies in the test directory (only if needed)
            node_modules_path = os.path.join(test_dir, 'node_modules')

            if not os.path.exists(node_modules_path):
                print("[CYPRESS] Installing dependencies (cypress-xpath)...")
                # Use --prefer-offline to speed up npm install using cache
                install_cmd = "npm install --prefer-offline --no-audit --no-fund --no-progress"
                try:
                    env = os.environ.copy()
                    env['PYTHONIOENCODING'] = 'utf-8'
                    proc = subprocess.Popen(
                        install_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                        env=env,
                        cwd=test_dir  # Ensure we're in the test directory
                    )
                    stdout_data, stderr_data = proc.communicate(timeout=120)
                    stdout_text = stdout_data.decode('utf-8', errors='replace')
                    stderr_text = stderr_data.decode('utf-8', errors='replace')

                    if proc.returncode != 0:
                        print(f"[CYPRESS] Warning: npm install had issues: {stderr_text[:200]}")
                        # Try global install as fallback
                        print("[CYPRESS] Attempting global install of cypress-xpath...")
                        try:
                            global_install_cmd = "npm install -g cypress-xpath --no-fund --no-progress"
                            global_proc = subprocess.Popen(
                                global_install_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                shell=True,
                                env=env
                            )
                            global_stdout, global_stderr = global_proc.communicate(timeout=60)
                            if global_proc.returncode == 0:
                                print("[CYPRESS] Global cypress-xpath installed successfully")
                            else:
                                print(f"[CYPRESS] Global install also failed: {global_stderr.decode('utf-8', errors='replace')[:200]}")
                        except Exception as global_e:
                            print(f"[CYPRESS] Global install failed: {str(global_e)}")
                    else:
                        print("[CYPRESS] Dependencies installed successfully")
                except Exception as e:
                    print(f"[CYPRESS] Warning: Failed to run npm install: {str(e)}")
            else:
                print("[CYPRESS] Dependencies already installed, skipping npm install (FAST MODE)")

            # Build command with headless flag and performance optimizations
            # Create a persistent Chrome user data directory for faster startup
            chrome_user_data = os.path.join(tempfile.gettempdir(), 'cypress_chrome_profile')
            if not os.path.exists(chrome_user_data):
                os.makedirs(chrome_user_data, exist_ok=True)
            
            # For Cypress 10+, use different approach for headed vs headless mode
            if self.headless:
                cmd_parts = [
                    "npx", "cypress", "run",
                    "--spec", f"cypress/e2e/{execution_id}.cy.js",
                    "--browser", "chrome",
                    "--headless"
                ]
                print("[CYPRESS] Running in HEADLESS mode (no window)")
            else:
                # For headed mode in Cypress 10+, we need to use cypress open with --spec flag
                # But since we need programmatic control, we'll use run with headed mode
                cmd_parts = [
                    "npx", "cypress", "run",
                    "--spec", f"cypress/e2e/{execution_id}.cy.js",
                    "--browser", "chrome",
                    "--headed"  # This is supported in newer Cypress versions
                ]
                print("[CYPRESS] Running in INTERACTIVE mode (window will open for viewing)")
                print("[CYPRESS] ** PERFORMANCE OPTIMIZATIONS ENABLED: **")
                print("[CYPRESS]   - Persistent Chrome profile: faster reuse between tests")
                print("[CYPRESS]   - Minimal memory footprint (numTestsKeptInMemory=1)")
                print("[CYPRESS] Cypress browser window should now be visible on your screen")

            cmd = " ".join(cmd_parts)
            print(f"[CYPRESS] Executing command: {cmd}")
            
            # Always capture output for parsing, even in non-headless mode
            print("[CYPRESS] Running Cypress test...")
            execution_start = datetime.now(pytz.timezone('Asia/Kolkata'))
            print(f"[CYPRESS] Execution started at: {execution_start}")
            
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['CYPRESS_INTERNAL_ENV'] = 'production'
            
            # Windows-specific optimization: CREATE_NEW_PROCESS_GROUP for faster process creation
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'shell': True,
                'env': env
            }
            
            # Add Windows-specific flags for faster process creation
            if sys.platform == 'win32':
                popen_kwargs['creationflags'] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
            
            print(f"[CYPRESS] Attempting to start subprocess with command: {cmd}")
            print(f"[CYPRESS] Current working directory: {os.getcwd()}")
            print(f"[CYPRESS] Python platform: {sys.platform}")
            print(f"[CYPRESS] DISPLAY environment variable: {env.get('DISPLAY', 'NOT SET')}")
            proc = subprocess.Popen(cmd, **popen_kwargs)
            print(f"[CYPRESS] Subprocess started successfully with PID: {proc.pid}")
            
            try:
                stdout_data, stderr_data = proc.communicate(timeout=300)
                stdout_text = stdout_data.decode('utf-8', errors='replace')
                stderr_text = stderr_data.decode('utf-8', errors='replace')
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                stdout_text = stdout_data.decode('utf-8', errors='replace')
                stderr_text = stderr_data.decode('utf-8', errors='replace')
                returncode = proc.returncode
                raise
            
            execution_end = datetime.now(pytz.timezone('Asia/Kolkata'))
            execution_duration = execution_end - execution_start

            # Change back to original directory
            os.chdir(original_dir)

            print(f"[CYPRESS] Cypress exit code: {returncode}")
            print(f"[CYPRESS] Execution duration: {execution_duration}")
            
            if stdout_text:
                print(f"[CYPRESS] STDOUT length: {len(stdout_text)} chars")
                # Parse passing tests from output
                import re
                passing_match = re.search(r'(\d+)\s+passing', stdout_text)
                failing_match = re.search(r'(\d+)\s+failing', stdout_text)
                
                if passing_match:
                    passed = int(passing_match.group(1))
                    print(f"[CYPRESS] Extracted {passed} passing test(s)")
                if failing_match:
                    failed = int(failing_match.group(1))
                    print(f"[CYPRESS] Extracted {failed} failing test(s)")
                    
            if stderr_text:
                print(f"[CYPRESS] STDERR: {stderr_text[:500]}")

            # Parse results with the captured output
            test_results = self.parse_cypress_results(stdout_text, stderr_text, returncode, execution_duration)

            return test_results

        except subprocess.TimeoutExpired:
            print("[CYPRESS] Cypress test timed out after 300 seconds")
            os.chdir(original_dir)
            total_steps = len(test_steps) if test_steps else 1
            return {
                'status': 'FAIL',
                'error_message': 'Cypress test execution timed out',
                'passed_steps': 0,
                'failed_steps': total_steps,
                'total_steps': total_steps,
                'execution_time': '05:00:00'
            }
        except Exception as e:
            print(f"[ERROR] Failed to run Cypress test: {str(e)}")
            print(f"[ERROR] Error type: {type(e).__name__}")
            print(f"[ERROR] Full exception details:")
            import traceback
            traceback.print_exc()
            os.chdir(original_dir)
            
            error_msg = str(e)
            print(f"[ERROR] Extracted error message: {error_msg}")
            if "The system cannot find the file specified" in error_msg or "No such file or directory" in error_msg:
                error_msg = f"Cypress or npm not available in PATH. {error_msg}. Make sure Node.js and npm are installed."
            
            total_steps = len(test_steps) if test_steps else 1
            print(f"[ERROR] Returning failure response with: passed_steps=0, failed_steps={total_steps}, error={error_msg}")
            return {
                'status': 'FAIL',
                'error_message': f'Failed to run Cypress test: {error_msg}',
                'passed_steps': 0,
                'failed_steps': total_steps,
                'total_steps': total_steps
            }

    def parse_cypress_results(self, stdout, stderr, exit_code, execution_duration=None):
        """Parse Cypress test results from output"""
        try:
            stdout = stdout or ""
            stderr = stderr or ""
            print(f"[PARSE] Parsing results - exit_code: {exit_code}, stdout_len: {len(stdout)}, stderr_len: {len(stderr)}")
            
            # Log raw output for debugging with proper encoding
            try:
                stdout_preview = repr(stdout[:500])
                stderr_preview = repr(stderr[:500])
                print(f"[PARSE] Raw STDOUT: {stdout_preview}")
                print(f"[PARSE] Raw STDERR: {stderr_preview}")
            except Exception as e:
                print(f"[PARSE] Error logging raw output: {str(e)}")
             
            # Handle character encoding issues
            try:
                stdout = stdout.encode('utf-8', errors='replace').decode('utf-8')
                stderr = stderr.encode('utf-8', errors='replace').decode('utf-8')
            except Exception as e:
                print(f"[PARSE] Character encoding error: {str(e)}")
                # Fallback to using the original strings if encoding fails
                pass
              
            results = {
                'status': 'UNKNOWN',
                'passed_steps': 0,
                'failed_steps': 0,
                'total_steps': 1,
                'error_message': '',
                'execution_time': '00:00:00'
            }

            import re
             
            # Try to extract passing tests
            passing_match = re.search(r'(\d+)\s+passing', stdout)
            if passing_match:
                results['passed_steps'] = int(passing_match.group(1))
                print(f"[PARSE] Found {results['passed_steps']} passing test(s)")
             
            # Try to extract failing tests
            failing_match = re.search(r'(\d+)\s+failing', stdout)
            if failing_match:
                results['failed_steps'] = int(failing_match.group(1))
                print(f"[PARSE] Found {results['failed_steps']} failing test(s)")
             
            # Calculate total steps
            results['total_steps'] = results['passed_steps'] + results['failed_steps']
            if results['total_steps'] == 0:
                results['total_steps'] = 1
             
            # Calculate execution time from duration if provided
            if execution_duration:
                total_seconds = int(execution_duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                results['execution_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                print(f"[PARSE] Execution time: {results['execution_time']}")
            else:
                # Fallback: try to extract execution time from Cypress output
                time_match = re.search(r'(\d+):(\d+):(\d+)', stdout)
                if time_match:
                    results['execution_time'] = f"{time_match.group(1)}:{time_match.group(2)}:{time_match.group(3)}"
                    print(f"[PARSE] Execution time from output: {results['execution_time']}")
 
            # Determine test status based on passing/failing counts
            if results['failed_steps'] == 0 and results['passed_steps'] > 0:
                results['status'] = 'PASS'
                print(f"[PARSE] Test PASSED ({results['passed_steps']} passed, {results['failed_steps']} failed)")
            else:
                results['status'] = 'FAIL'
                results['error_message'] = stderr.strip() if stderr else 'Cypress test failed'
                print(f"[PARSE] Test FAILED ({results['passed_steps']} passed, {results['failed_steps']} failed)")
                
                # Extract error details from output
                if 'CypressError' in stdout:
                    error_start = stdout.find('CypressError')
                    error_section = stdout[error_start:error_start+500]
                    results['error_message'] = error_section
                    print(f"[PARSE] Error message: {error_section[:200]}")
 
            print(f"[PARSE] Final result: status={results['status']}, passed={results['passed_steps']}, failed={results['failed_steps']}")
            return results
 
        except Exception as e:
            print(f"[ERROR] Failed to parse Cypress results: {str(e)}")
            # Provide more detailed error information
            import traceback
            traceback.print_exc()
            return {
                'status': 'FAIL',
                'error_message': f'Failed to parse results: {str(e)}',
                'passed_steps': 0,
                'failed_steps': 1,
                'total_steps': 1
            }

    def extract_failed_step_number(self, error_message, total_steps):
        """Try to extract which step failed from error message"""
        try:
            if not error_message:
                return None
            
            import re
            step_pattern = r'Step\s+(\d+)'
            matches = re.findall(step_pattern, error_message)
            if matches:
                return int(matches[0])
            return None
        except Exception as e:
            print(f"[DEBUG] Could not extract failed step number: {str(e)}")
            return None

    def cleanup_test_directory(self):
        """Clean up the temporary test directory"""
        try:
            if hasattr(self, 'cypress_test_dir') and self.cypress_test_dir and os.path.exists(self.cypress_test_dir):
                shutil.rmtree(self.cypress_test_dir, ignore_errors=True)
                print(f"[CLEANUP] Removed test directory: {self.cypress_test_dir}")
                self.cypress_test_dir = None
        except Exception as e:
            print(f"[CLEANUP_WARNING] Failed to remove test directory: {e}")

    def execute_test_case(self, testcase_name, test_steps, test_metadata=None):
        """Execute a test case with the provided steps using Cypress"""
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
            'browser_info': 'Cypress/Chrome'
        }

        if test_metadata:
            result.update(test_metadata)

        try:
            print(f"[ROCKET] Starting Cypress test execution: {testcase_name}")
            print(f"[CLIPBOARD] Total steps: {len(test_steps)}")
            
            self.update_execution_date()
            
            # Debug: Print test steps
            print("[DEBUG] Test steps received:")
            for i, step in enumerate(test_steps, 1):
                print(f"  Step {i}: action_type='{step.get('action_type', 'N/A')}', description='{step.get('test_step_description', 'N/A')}'")
                print(f"    xpath='{step.get('xpath', '')}', element='{step.get('element_name', '')}', values='{step.get('values', '')}'")

            # Generate Cypress test file
            test_dir = self.generate_cypress_test_file(testcase_name, test_steps, execution_id)
            print(f"[CYPRESS] Test directory created: {test_dir}")

            # Run the Cypress test
            print("[CYPRESS] Running Cypress test...")
            cypress_results = self.run_cypress_test(test_dir, execution_id, test_steps)
            print(f"[CYPRESS] Cypress execution completed with status: {cypress_results.get('status')}")

            # Update result with Cypress results
            result.update(cypress_results)

            # Create step results from test_steps data
            print("[CYPRESS] Processing step results...")
            for i, step in enumerate(test_steps, 1):
                step_result = {
                    'tc_id': step.get('tc_id', ''),
                    'step_no': i,
                    'description': step.get('test_step_description', f'Step {i}'),
                    'test_step_description': step.get('test_step_description', f'Step {i}'),
                    'element_name': step.get('element_name', ''),
                    'action_type': step.get('action_type', ''),
                    'xpath': step.get('xpath', ''),
                    'values': step.get('values', ''),
                    'status': 'PASS' if result['status'] == 'PASS' else 'FAIL',
                    'error': result.get('error_message', ''),
                    'error_message': result.get('error_message', ''),
                    'execution_time': result.get('execution_time', '00:00:00'),
                    'after_screenshot': '',
                    'screenshot_status': ''
                }
                result['step_results'].append(step_result)
                
                if step_result['status'] == 'PASS':
                    print(f"[STEP {i}] PASSED - {step_result['description']}")
                else:
                    print(f"[STEP {i}] FAILED - {step_result['description']}")

            # Determine overall status
            if result['failed_steps'] == 0 and result['passed_steps'] > 0:
                result['status'] = 'PASS'
                result['execution_status'] = 'COMPLETED'
                print("[FINAL] All steps passed - Test PASSED")
            elif result['failed_steps'] > 0 and result['passed_steps'] > 0:
                result['status'] = 'PARTIAL_PASS'
                result['execution_status'] = 'COMPLETED'
                print(f"[FINAL] Partial pass - {result['passed_steps']} step(s) passed, {result['failed_steps']} step(s) failed")
            elif result['failed_steps'] > 0:
                result['status'] = 'FAIL'
                result['execution_status'] = 'COMPLETED'
                print(f"[FINAL] {result['failed_steps']} step(s) failed - Test FAILED")
            else:
                result['status'] = 'UNKNOWN'
                result['execution_status'] = 'COMPLETED'
                print("[FINAL] Test status unknown")

        except Exception as e:
            result['status'] = 'FAIL'
            result['error_message'] = str(e)
            print(f"[ERROR] Cypress test execution failed: {str(e)}")
            traceback.print_exc()

        result['end_time'] = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        # Calculate execution time
        if result['end_time'] and result['start_time']:
            duration = (result['end_time'] - result['start_time']).total_seconds()
            minutes, seconds = divmod(int(duration), 60)
            hours, minutes = divmod(minutes, 60)
            result['execution_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        print(f"[FINAL] Test execution completed in {result['execution_time']}")
        print(f"[FINAL] Result: {result['status']} | Passed: {result['passed_steps']} | Failed: {result['failed_steps']} | Total: {result['total_steps']}")
        
        # Add execution_date in IST format (DD/MM/YYYY, HH:MM:SS)
        ist_timezone = pytz.timezone('Asia/Kolkata')
        execution_date_ist = start_time.astimezone(ist_timezone)
        result['execution_date'] = execution_date_ist.strftime('%d/%m/%Y, %H:%M:%S')
        
        return result
