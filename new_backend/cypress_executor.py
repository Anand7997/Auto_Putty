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
            support_content = r"""
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

const qfastVisible = ($elements) => Cypress.$($elements).filter((_, el) => {
  const $el = Cypress.$(el)
  if (!$el.is(':visible')) {
    return false
  }
  const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null
  return !rect || (rect.width > 0 && rect.height > 0)
})

Cypress.Commands.add('resolveAnchoredInput', { prevSubject: true }, (subject) => {
  const $subject = Cypress.$(subject).first()
  if (!$subject.length) {
    throw new Error('resolveAnchoredInput requires a subject')
  }

  if ($subject.is('input, textarea')) {
    return cy.wrap($subject)
  }

  const subjectEl = $subject[0]
  const byVisibility = ($els) => qfastVisible($els).first()
  const selector = 'input:visible, textarea:visible'

  const candidates = []

  const ariaControls = subjectEl.getAttribute && subjectEl.getAttribute('aria-controls')
  if (ariaControls) {
    candidates.push(Cypress.$(`#${ariaControls}`).find(selector))
  }

  const forId = subjectEl.getAttribute && subjectEl.getAttribute('for')
  if (forId) {
    candidates.push(Cypress.$(`#${forId}`))
  }

  const $closestLabel = $subject.closest('label')
  if ($closestLabel.length) {
    candidates.push($closestLabel.find(selector))
  }

  const $closestField = $subject.closest('[role="group"], [role="combobox"], label, form, section, article, div')
  if ($closestField.length) {
    candidates.push($closestField.find(selector))
    candidates.push($closestField.siblings().find(selector))
  }

  candidates.push($subject.parent().find(selector))
  candidates.push($subject.nextAll().find(selector))
  candidates.push($subject.prevAll().find(selector))

  for (const group of candidates) {
    const $match = byVisibility(group)
    if ($match.length) {
      return cy.wrap($match)
    }
  }

  return cy.focused().then(($focused) => {
    if ($focused.is('input, textarea')) {
      return cy.wrap($focused)
    }
    const $fallback = byVisibility(Cypress.$(selector))
    if ($fallback.length) {
      return cy.wrap($fallback)
    }
    throw new Error('Unable to resolve a visible input for the current trigger')
  })
})

Cypress.Commands.add('findActiveLayerRoot', { prevSubject: 'optional' }, (subject, kind = 'generic') => {
  const $subject = subject ? Cypress.$(subject).first() : Cypress.$()
  const layerSelector = [
    '[role="dialog"]',
    '[role="listbox"]',
    '[role="menu"]',
    '[role="presentation"]',
    '[data-testid*="calendar"]',
    '[data-testid*="popover"]',
    '[data-testid*="dropdown"]',
    '[data-testid*="modal"]',
    '[class*="calendar"]',
    '[class*="Calendar"]',
    '[class*="datepicker"]',
    '[class*="DatePicker"]',
    '[class*="popover"]',
    '[class*="Popover"]',
    '[class*="dropdown"]',
    '[class*="Dropdown"]',
    '[class*="modal"]',
    '[class*="Modal"]'
  ].join(', ')

  const detectorByKind = {
    calendar: 'abbr[aria-label], button[aria-label], [data-testid*="calendar"], [class*="calendar"], [class*="DatePicker"], [class*="datepicker"]',
    popup: 'button, [role="button"], [role="option"], li, p, span',
    generic: 'button, input, textarea, abbr, [role="button"], [role="option"]'
  }

  const detector = detectorByKind[kind] || detectorByKind.generic

  const score = (el) => {
    const $el = Cypress.$(el)
    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 0, height: 0, top: 0, left: 0 }
    const zIndex = Number.parseInt(($el.css('z-index') || '0').toString(), 10) || 0
    let proximity = 0
    if ($subject.length && $subject[0].getBoundingClientRect) {
      const sRect = $subject[0].getBoundingClientRect()
      const dx = Math.abs((rect.left + rect.width / 2) - (sRect.left + sRect.width / 2))
      const dy = Math.abs((rect.top + rect.height / 2) - (sRect.top + sRect.height / 2))
      proximity = Math.max(0, 5000 - dx - dy)
    }
    return proximity + zIndex + rect.width + rect.height
  }

  return cy.getActiveFrameBody().then(($body) => {
    const pools = []

    if ($subject.length) {
      pools.push($subject.closest(layerSelector))
      pools.push($subject.parents().filter(layerSelector))
      pools.push($subject.siblings(layerSelector))
    }

    pools.push(Cypress.$(layerSelector, $body))
    pools.push(Cypress.$('body > div, body > section, body > aside', $body))

    const candidates = []
    for (const pool of pools) {
      qfastVisible(pool).each((_, el) => {
        const $el = Cypress.$(el)
        if ($el.find(detector).length || $el.is(detector)) {
          candidates.push(el)
        }
      })
    }

    const uniqueCandidates = [...new Set(candidates)]
    if (!uniqueCandidates.length) {
      return cy.wrap($body)
    }

    uniqueCandidates.sort((a, b) => score(b) - score(a))
    return cy.wrap(uniqueCandidates[0])
  })
})

Cypress.Commands.add('selectAutocompleteOption', { prevSubject: 'optional' }, (subject, targetText) => {
  const normalizedTarget = (targetText || '').replace(/\s+/g, ' ').trim().toLowerCase()

  const scoreSuggestion = (el) => {
    const $el = Cypress.$(el)
    const text = ($el.text() || '').replace(/\s+/g, ' ').trim().toLowerCase()
    const clickable = $el.is('button, a, li, [role="option"], [role="button"]')
      ? $el
      : $el.closest('button, a, li, [role="option"], [role="button"], [data-testid], [tabindex]')
    const clickableText = (clickable.text() || text || '').replace(/\s+/g, ' ').trim().toLowerCase()
    const combined = clickableText || text

    if (!combined || !normalizedTarget || !combined.includes(normalizedTarget)) {
      return null
    }

    let score = 0
    if (combined === normalizedTarget) score += 100
    if (combined.startsWith(normalizedTarget)) score += 60
    if (combined.includes(` ${normalizedTarget}`)) score += 20
    if (clickable.length && clickable[0] !== el) score += 10
    if ($el.attr('role') === 'option' || clickable.attr('role') === 'option') score += 30
    if ($el.is('li') || clickable.is('li')) score += 20
    if ((clickable.attr('class') || '').toLowerCase().includes('disabled')) score -= 200
    score -= Math.max(0, combined.length - normalizedTarget.length)

    return {
      element: clickable.length ? clickable[0] : el,
      score
    }
  }

  return cy.findActiveLayerRoot(subject, 'popup').then(($popupRoot) => {
    const $root = Cypress.$($popupRoot)
    const candidates = $root
      .find('[role="option"], li, button, a, [role="button"], [data-testid], div, span, p')
      .filter(':visible')
      .toArray()
      .map(scoreSuggestion)
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)

    if (!candidates.length) {
      return cy.wrap(null, { log: false })
    }

    return cy.wrap(Cypress.$(candidates[0].element), { log: false })
  })
})

Cypress.Commands.add('resolveChoiceControl', { prevSubject: true }, (subject, optionText, controlKind = 'checkbox') => {
  const $subject = Cypress.$(subject).first()
  if (!$subject.length) {
    throw new Error('resolveChoiceControl requires a subject')
  }

  const normalizedTarget = (optionText || '').replace(/\s+/g, ' ').trim().toLowerCase()
  const normalizedKind = (controlKind || 'checkbox').toString().trim().toLowerCase()
  const selectors = normalizedKind === 'radio'
    ? 'input[type="radio"], [role="radio"]'
    : 'input[type="checkbox"], [role="checkbox"]'

  const collectTexts = (el) => {
    const $el = Cypress.$(el)
    const texts = [
      el.value,
      $el.attr('value'),
      $el.attr('aria-label'),
      $el.attr('aria-labelledby'),
      $el.attr('data-testid'),
      $el.attr('id'),
      $el.attr('name'),
      $el.text(),
      $el.parent().text(),
      $el.next().text(),
      $el.prev().text(),
      $el.closest('label').text(),
    ]

    if (el.labels && el.labels.length) {
      Array.from(el.labels).forEach((label) => texts.push(label.textContent))
    }

    return texts
      .map((value) => (value || '').replace(/\s+/g, ' ').trim().toLowerCase())
      .filter(Boolean)
  }

  const scoreCandidate = (el) => {
    const texts = collectTexts(el)
    if (!normalizedTarget) {
      return Cypress.$(el).is(selectors) ? 1 : 0
    }

    let bestScore = 0
    texts.forEach((text) => {
      if (text === normalizedTarget) bestScore = Math.max(bestScore, 100)
      else if (text.includes(normalizedTarget)) bestScore = Math.max(bestScore, 60)
      else if (normalizedTarget.includes(text)) bestScore = Math.max(bestScore, 40)
    })
    return bestScore
  }

  const candidates = []
  const addCandidates = ($root) => {
    if (!$root || !$root.length) return
    if ($root.is(selectors)) candidates.push($root[0])
    $root.find(selectors).each((_, el) => candidates.push(el))
  }

  addCandidates($subject)
  addCandidates($subject.closest('label'))
  addCandidates($subject.closest('[role="group"], fieldset, form, section, article, div'))
  addCandidates($subject.parent())
  addCandidates($subject.siblings())

  const unique = [...new Set(candidates)]
    .map((el) => ({ element: el, score: scoreCandidate(el) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)

  if (!unique.length) {
    throw new Error(`Unable to resolve ${normalizedKind} option "${optionText}"`)
  }

  return cy.wrap(Cypress.$(unique[0].element), { log: false })
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
                assertion_type = step.get('assertion_type', '')

                print(f"[CYPRESS_GEN] Step {i}: action={action_type}, element={element_name}, data={test_data[:50] if test_data else ''}")

                # Add step comment
                test_content += f"""
    // Step {i}: {step_description}
"""

                # Generate Cypress command based on action type
                timeout_seconds = self._resolve_step_timeout_seconds(step)
                cypress_command = self.generate_cypress_command(action_type, xpath, element_name, test_data, i, timeout_seconds, assertion_type)
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

    def clean_xpath(self, xpath):
        """Clean XPath to fix common syntax issues before emitting Cypress selectors."""
        try:
            if not xpath:
                return xpath

            cleaned = str(xpath).strip()

            # Fix concatenated XPath values like:
            # //select[@id='child-age'] (//select[@data-testid='child-age-selector'])[1]
            # by keeping the actual indexed selector.
            concatenated_with_index = r"^//[^(\s]+\s+\((//[^)]+)\)\[(\d+)\]$"
            match = re.match(concatenated_with_index, cleaned)
            if match:
                inner_xpath = match.group(1)
                index = match.group(2)
                cleaned = f"({inner_xpath})[{index}]"
                print(f"[XPATH_CLEAN] Fixed concatenated XPath, using: {cleaned}")
                return cleaned

            concatenated_simple = r"^//[^(\s]+\s+\((//[^)]+)\)$"
            match = re.match(concatenated_simple, cleaned)
            if match:
                cleaned = match.group(1)
                print(f"[XPATH_CLEAN] Fixed simple concatenated XPath, using: {cleaned}")
                return cleaned

            if not cleaned.startswith(("/", ".//", "(")):
                cleaned = "//" + cleaned

            return cleaned
        except Exception as e:
            print(f"[XPATH_CLEAN] Failed to clean XPath '{xpath}': {str(e)}")
            return xpath

    def _safe_log_preview(self, text, limit=500):
        """Return an ASCII-safe preview string for console logging."""
        preview = ascii((text or "")[:limit])
        if text and len(text) > limit:
            preview += "..."
        return preview

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

    def normalize_assertion_type(self, assertion_type):
        normalized = re.sub(r"[\s\-/]+", "_", str(assertion_type or "").upper().strip())
        alias_map = {
            "": "ELEMENT_VISIBLE",
            "VERIFY_ELEMENT_EXISTS": "ELEMENT_EXISTS",
            "VERIFY_ELEMENT_VISIBLE": "ELEMENT_VISIBLE",
            "VERIFY_ELEMENT_ENABLED": "ELEMENT_ENABLED",
            "VERIFY_ELEMENT_DISABLED": "ELEMENT_DISABLED",
            "VERIFY_ELEMENT_CLICKABLE": "ELEMENT_CLICKABLE",
            "VERIFY_INPUT": "VERIFY_INPUT_VALUE",
            "VERIFY_VALUE": "VERIFY_INPUT_VALUE",
            "VERIFY_URL": "VERIFY_URL_CONTAINS",
            "VERIFY_PAGE_LOAD_COMPLETION": "VERIFY_PAGE_LOADED",
            "WAIT_FOR_ELEMENT_VISIBLE": "WAIT_FOR_VISIBLE",
        }
        return alias_map.get(normalized, normalized or "ELEMENT_VISIBLE")

    def _translate_press_key_for_cypress(self, key_value):
        raw = str(key_value or "").strip()
        if not raw:
            return "{enter}"

        tokens = [token.strip() for token in re.split(r"\s*\+\s*", raw) if token.strip()]
        alias_map = {
            "CTRL": "{ctrl}",
            "CONTROL": "{ctrl}",
            "CMD": "{meta}",
            "COMMAND": "{meta}",
            "WIN": "{meta}",
            "WINDOWS": "{meta}",
            "ALT": "{alt}",
            "OPTION": "{alt}",
            "SHIFT": "{shift}",
            "ENTER": "{enter}",
            "RETURN": "{enter}",
            "TAB": "{tab}",
            "ESC": "{esc}",
            "ESCAPE": "{esc}",
            "SPACE": " ",
            "BACKSPACE": "{backspace}",
            "DELETE": "{del}",
            "DEL": "{del}",
            "ARROW_UP": "{uparrow}",
            "UP": "{uparrow}",
            "ARROW_DOWN": "{downarrow}",
            "DOWN": "{downarrow}",
            "ARROW_LEFT": "{leftarrow}",
            "LEFT": "{leftarrow}",
            "ARROW_RIGHT": "{rightarrow}",
            "RIGHT": "{rightarrow}",
        }

        translated = []
        for token in tokens:
            normalized = token.upper().replace(" ", "_").replace("-", "_")
            if normalized in alias_map:
                translated.append(alias_map[normalized])
            elif len(token) == 1:
                translated.append(token.lower())
            else:
                raise ValueError(f"Unsupported Cypress key token: {token}")
        return "".join(translated) if translated else "{enter}"

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
            selector = self.escape_string_for_js(self.clean_xpath(raw[6:]))
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
            selector = self.escape_string_for_js(self.clean_xpath(raw))
            return f"cy.xpathOrCSS('{selector}', true)"
        if raw.startswith(("#", ".", "[")) or any(token in raw for token in [" ", ">", "~", ":", "*"]):
            selector = self.escape_string_for_js(raw)
            return f"cy.get('{selector}')"

        selector = self.escape_string_for_js(self.clean_xpath(raw))
        return f"cy.xpathOrCSS('{selector}', true)"

    def generate_cypress_command(self, action_type, xpath, element_name, test_data, step_number, timeout_seconds=None, assertion_type=None):
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
                    return self.generate_generic_click_and_select_command(xpath, element_name, test_data, timeout_ms)

            elif action_type == "CLICK_AND_TYPE":
                return f"{selector_cmd}.scrollIntoView().clear({{ force: true }}).type('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "CLEAR_AND_TYPE":
                return f"{selector_cmd}.scrollIntoView().clear({{ force: true }}).type('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "CLICK":
                if element_name.upper() == "TRAVELCLASS":
                    return self.generate_travel_class_command(test_data_escaped, xpath, element_name)
                elif element_name.upper() in ["DONEBUTTON", "DONE"]:
                    return """
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {
      const _root = Cypress.$($popupRoot)
      const _match = _root.find('button, [role="button"], p, span').filter((_, el) => {
        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        return text === 'done'
      }).first()

      if (_match.length) {
        cy.wrap(_match).scrollIntoView().click({ force: true })
      } else {
        cy.contains('Done').first().click({ force: true })
      }
    })"""
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
                radio_value = str(test_data or '').strip()
                normalized_radio_value = radio_value.lower()
                radio_boolean_values = ["", "true", "1", "yes", "on", "select", "selected", "false", "0", "no", "off", "uncheck", "unchecked", "deselect", "unselected"]
                if normalized_radio_value not in radio_boolean_values and radio_value:
                    radio_value_escaped = self.escape_string_for_js(radio_value)
                    return (
                        f"{selector_cmd}.scrollIntoView()"
                        f".resolveChoiceControl('{radio_value_escaped}', 'radio')"
                        f".scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})"
                    )
                should_check = normalized_radio_value in ["", "true", "1", "yes", "on", "select", "selected"]
                if should_check:
                    return f"{selector_cmd}.scrollIntoView().check({{ force: true, timeout: {timeout_ms} }})"
                return "// RADIO_BUTTON unselect skipped: radios cannot be safely unchecked directly"

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
                checkbox_value = str(test_data or '').strip()
                normalized_checkbox_value = checkbox_value.lower()
                checkbox_boolean_values = ["", "true", "1", "yes", "on", "check", "checked", "select", "selected", "false", "0", "no", "off", "uncheck", "unchecked", "deselect", "unselected"]
                if normalized_checkbox_value not in checkbox_boolean_values and checkbox_value:
                    choice_values = [self.escape_string_for_js(part.strip()) for part in re.split(r"[,;\n]+", checkbox_value) if part.strip()]
                    choice_commands = [
                        (
                            f"{selector_cmd}.scrollIntoView()"
                            f".resolveChoiceControl('{choice}', 'checkbox')"
                            f".then(($choice) => {{ if (!$choice.prop('checked')) {{ cy.wrap($choice).scrollIntoView().click({{ force: true, timeout: {timeout_ms} }}); }} }})"
                        )
                        for choice in choice_values
                    ]
                    return "\n".join(choice_commands)
                should_check = normalized_checkbox_value in ["true", "1", "yes", "on", "check", "checked", "select", "selected"]
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

            elif action_type == "PRESS_KEY":
                key_sequence = self.escape_string_for_js(self._translate_press_key_for_cypress(test_data))
                return (
                    "cy.focused().then(($focused) => { "
                    "if ($focused && $focused.length) { "
                    f"cy.wrap($focused).type('{key_sequence}', {{ force: true, parseSpecialCharSequences: true, timeout: {timeout_ms} }}); "
                    "} else { "
                    f"cy.get('body').type('{key_sequence}', {{ force: true, parseSpecialCharSequences: true, timeout: {timeout_ms} }}); "
                    "} "
                    "})"
                )

            elif action_type == "READ_TEXT":
                assertion_js = f"expect(actual).to.contain('{test_data_escaped}')" if test_data_text else "cy.log(`READ_TEXT: ${actual}`)"
                return f"{selector_cmd}.invoke('text').then((text) => {{ const actual = String(text || '').replace(/\\\\s+/g, ' ').trim(); {assertion_js}; }})"

            elif action_type == "READ_VALUE":
                assertion_js = f"expect(actual).to.contain('{test_data_escaped}')" if test_data_text else "cy.log(`READ_VALUE: ${actual}`)"
                return f"{selector_cmd}.invoke('val').then((value) => {{ const actual = String(value || '').trim(); {assertion_js}; }})"

            elif action_type == "READ_TOOLTIP":
                assertion_js = f"expect(actual).to.contain('{test_data_escaped}')" if test_data_text else "cy.log(`READ_TOOLTIP: ${actual}`)"
                return f"{selector_cmd}.then(($el) => {{ const actual = String($el.attr('title') || $el.attr('aria-label') || $el.attr('placeholder') || '').trim(); {assertion_js}; }})"

            elif action_type == "READ_LABEL":
                assertion_js = f"expect(actual).to.contain('{test_data_escaped}')" if test_data_text else "cy.log(`READ_LABEL: ${actual}`)"
                return f"{selector_cmd}.then(($el) => {{ const id = $el.attr('id'); const explicit = id ? Cypress.$(`label[for=\"${{id}}\"]`).text() : ''; const closest = $el.closest('label').text(); const actual = String(explicit || closest || '').replace(/\\\\s+/g, ' ').trim(); {assertion_js}; }})"

            elif action_type == "COPY":
                return (
                    f"{selector_cmd}.scrollIntoView().click({{ force: true, timeout: {timeout_ms} }}); "
                    "cy.focused().type('{ctrl}a{ctrl}c', { force: true, parseSpecialCharSequences: true })"
                )

            elif action_type == "PASTE":
                if test_data_text:
                    return f"{selector_cmd}.scrollIntoView().clear({{ force: true }}).type('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"
                return (
                    f"{selector_cmd}.scrollIntoView().click({{ force: true, timeout: {timeout_ms} }}); "
                    "cy.focused().type('{ctrl}v', { force: true, parseSpecialCharSequences: true })"
                )

            elif action_type == "UPLOAD_FILE":
                return f"{selector_cmd}.selectFile('{test_data_escaped}', {{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "DOWNLOAD_FILE":
                return f"{selector_cmd}.scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})"

            elif action_type == "VISUAL_ASSERTION":
                baseline_name = self.escape_string_for_js(str(test_data or element_name or 'visual_assertion').strip())
                return f"cy.screenshot('visual-{baseline_name}')"

            elif action_type == "ASSERTION":
                normalized_assertion = self.normalize_assertion_type(assertion_type)
                expected_escaped = self.escape_string_for_js(test_data)
                if normalized_assertion == "VERIFY_PAGE_TITLE":
                    return f"cy.title().should('eq', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_URL_CONTAINS":
                    return f"cy.url().should('include', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_URL_EQUALS":
                    return f"cy.url().should('eq', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_PAGE_LOADED":
                    return "cy.document().its('readyState').should('eq', 'complete')"
                if normalized_assertion == "ELEMENT_EXISTS":
                    return f"{selector_cmd}.should('exist')"
                if normalized_assertion == "ELEMENT_VISIBLE":
                    return f"{selector_cmd}.should('be.visible')"
                if normalized_assertion == "ELEMENT_ENABLED":
                    return f"{selector_cmd}.should('be.enabled')"
                if normalized_assertion == "ELEMENT_DISABLED":
                    return f"{selector_cmd}.should('be.disabled')"
                if normalized_assertion == "ELEMENT_CLICKABLE":
                    return f"{selector_cmd}.should('be.visible').and('be.enabled')"
                if normalized_assertion == "VERIFY_TEXT":
                    return f"{selector_cmd}.should('have.text', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_INPUT_VALUE":
                    return f"{selector_cmd}.should('have.value', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_PLACEHOLDER":
                    return f"{selector_cmd}.should('have.attr', 'placeholder', '{expected_escaped}')"
                if normalized_assertion == "VERIFY_ATTRIBUTE":
                    attribute_name = ""
                    attribute_value = ""
                    for separator in ['=', ':']:
                        if separator in str(test_data or ''):
                            attribute_name, attribute_value = [part.strip() for part in str(test_data).split(separator, 1)]
                            break
                    if not attribute_name:
                        return "// ASSERTION VERIFY_ATTRIBUTE requires Values as attribute=value"
                    return f"{selector_cmd}.should('have.attr', '{self.escape_string_for_js(attribute_name)}', '{self.escape_string_for_js(attribute_value)}')"
                if normalized_assertion == "WAIT_FOR_VISIBLE":
                    return f"{selector_cmd}.should('be.visible')"
                if normalized_assertion == "WAIT_FOR_CLICKABLE":
                    return f"{selector_cmd}.should('be.visible').and('be.enabled')"
                if normalized_assertion == "WAIT_FOR_LOADER_DISAPPEARS":
                    return f"{selector_cmd}.should('not.exist')"
                return f"// Unsupported assertion type: {normalized_assertion}"

            else:
                return f"// Unknown action type: {action_type}"

        except Exception as e:
            print(f"[ERROR] Failed to generate Cypress command for {action_type}: {str(e)}")
            return f"// Error generating command for {action_type}"

    def generate_generic_click_and_select_command(self, xpath, element_name, test_data, timeout_ms):
        """Generate control-aware CLICK_AND_SELECT command similar to Selenium fallback strategy."""
        selector_cmd = self._selector_command(xpath)
        value_text = str(test_data or "").strip()
        has_value = bool(value_text)
        desired_checked = value_text.lower() in ["true", "1", "yes", "on", "checked"]
        value_escaped = self.escape_string_for_js(value_text)
        element_name_escaped = self.escape_string_for_js(str(element_name or "").strip())

        return f"""{selector_cmd}.first().then(($target) => {{
      const _el = $target && $target.length ? $target[0] : null
      if (!_el) {{
        throw new Error('CLICK_AND_SELECT target element not found for {element_name_escaped}')
      }}

      const _tag = (_el.tagName || '').toLowerCase()
      const _type = ((_el.getAttribute && _el.getAttribute('type')) || '').toLowerCase()
      const _value = '{value_escaped}'
      const _hasValue = {str(has_value).lower()}

      if (_tag === 'select') {{
        if (!_hasValue) {{
          throw new Error('No selection value provided for select element')
        }}

        const _trimmed = _value.trim()
        const _normalized = _trimmed.toLowerCase()
        const _options = Array.from(_el.options || [])
        const _byText = _options.find((opt) => ((opt.text || '').trim().toLowerCase() === _normalized))
        const _byValue = _options.find((opt) => ((opt.value || '').trim().toLowerCase() === _normalized))
        const _byIndex = /^\\d+$/.test(_trimmed) ? _options[Number.parseInt(_trimmed, 10)] : null
        const _selectedOption = _byText || _byValue || _byIndex || null

        if (!_selectedOption) {{
          throw new Error(`Could not select '${{_value}}' from dropdown`)
        }}

        cy.wrap($target).scrollIntoView().select(_selectedOption.value, {{ force: true, timeout: {timeout_ms} }})
        return
      }}

      if (_type === 'checkbox' || _type === 'radio') {{
        const _desired = {str(desired_checked).lower()}
        const _current = Cypress.$(_el).prop('checked') === true
        if (_desired !== _current) {{
          cy.wrap($target).scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})
        }}
        return
      }}

      if (_hasValue) {{
        cy.wrap($target)
          .scrollIntoView()
          .click({{ force: true, timeout: {timeout_ms} }})
        cy.wrap($target).selectAutocompleteOption(_value).then(($suggestion) => {{
          if ($suggestion && $suggestion.length) {{
            cy.wrap($suggestion).scrollIntoView().click({{ force: true }})
          }}
        }})
        return
      }}

      cy.wrap($target).scrollIntoView().click({{ force: true, timeout: {timeout_ms} }})
    }})"""

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
        """Generate Cypress command for city selection.

        Use a direct input flow when the locator already targets an input.
        Otherwise click the trigger first, then type into the visible input.
        """
        selector_cmd = self._selector_command(xpath)
        locator_text = str(xpath or "").lower()
        targets_input_directly = "input" in locator_text or "textarea" in locator_text

        if targets_input_directly:
            return f"""
    {selector_cmd}.filter(':visible').first().scrollIntoView().click({{ force: true }})
    {selector_cmd}.filter(':visible').first().clear({{ force: true }}).type('{city_name}', {{ force: true, delay: 100 }})
    cy.wait(800)
    {selector_cmd}.filter(':visible').first().selectAutocompleteOption('{city_name}').then(($suggestion) => {{
      if ($suggestion && $suggestion.length) {{
        cy.wrap($suggestion).scrollIntoView().click({{ force: true }})
      }} else {{
        {selector_cmd}.filter(':visible').first().type('{{downarrow}}{{enter}}', {{ force: true }})
      }}
    }})
    cy.wait(2000)"""

        return f"""
    {selector_cmd}.filter(':visible').first().scrollIntoView().click({{ force: true }})
    cy.wait(500)
    cy.focused().then(($el) => {{
      if ($el.is('input, textarea')) {{
        cy.wrap($el)
          .click({{ force: true }})
          .clear({{ force: true }})
          .type('{city_name}', {{ force: true, delay: 100 }})
          .selectAutocompleteOption('{city_name}').then(($suggestion) => {{
            if ($suggestion && $suggestion.length) {{
              cy.wrap($suggestion).scrollIntoView().click({{ force: true }})
            }} else {{
              cy.wrap($el).type('{{downarrow}}{{enter}}', {{ force: true }})
            }}
          }})
      }} else {{
        {selector_cmd}.filter(':visible').first()
          .resolveAnchoredInput()
          .then(($input) => {{
            cy.wrap($input)
              .click({{ force: true }})
              .clear({{ force: true }})
              .type('{city_name}', {{ force: true, delay: 100 }})
              .selectAutocompleteOption('{city_name}').then(($suggestion) => {{
                if ($suggestion && $suggestion.length) {{
                  cy.wrap($suggestion).scrollIntoView().click({{ force: true }})
                }} else {{
                  cy.wrap($input).type('{{downarrow}}{{enter}}', {{ force: true }})
                }}
              }})
          }})
      }}
    }})
    cy.wait(2000)"""

    def generate_date_selection_command(self, xpath, element_name, date_string):
        """Generate Cypress command for date selection."""
        selector_cmd = self._selector_command(xpath)
        normalized_date = re.sub(r"\s+", " ", str(date_string or "").strip())
        current_year = datetime.now().year
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
        for fmt, has_year in parse_candidates:
            try:
                parsed_date = datetime.strptime(normalized_date, fmt)
                target_date = parsed_date if has_year else parsed_date.replace(year=current_year)
                break
            except ValueError:
                continue

        day_match = re.search(r"(\d{1,2})", normalized_date)
        day_number = day_match.group(1).lstrip("0") if day_match else ""
        full_date_label = target_date.strftime("%B %d, %Y") if target_date else ""
        normalized_date_escaped = self.escape_string_for_js(normalized_date)
        day_number_escaped = self.escape_string_for_js(day_number)
        full_date_label_escaped = self.escape_string_for_js(full_date_label)
        exact_date_selector = f'button[aria-label="{full_date_label_escaped}"]' if full_date_label_escaped else ""
        exact_date_selector_escaped = self.escape_string_for_js(exact_date_selector)
        locator_text = str(xpath or "").lower()
        should_click_parent = any(token in locator_text for token in ["contains(text()", "normalize-space("])
        open_calendar_cmd = (
            f"{selector_cmd}.first().parent().scrollIntoView().click({{ force: true }})"
            if should_click_parent
            else f"{selector_cmd}.first().scrollIntoView().click({{ force: true }})"
        )
        return f"""
    {open_calendar_cmd}
    cy.wait(800)
    {selector_cmd}.first().findActiveLayerRoot('calendar').then(($calendarRoot) => {{
      const _targetDate = '{normalized_date_escaped}'.toLowerCase()
      const _targetDay = '{day_number_escaped}'
      const _fullDateLabel = '{full_date_label_escaped}'.toLowerCase()
      const _exactDateSelector = '{exact_date_selector_escaped}'
      const _root = Cypress.$($calendarRoot)

      if (_exactDateSelector) {{
        const _exact = _root.find(_exactDateSelector).filter(':visible:not(:disabled)').first()
        if (_exact.length) {{
          cy.wrap(_exact).scrollIntoView().click({{ force: true }})
          return
        }}
      }}

      const _calendarSelectors = [
        'button[aria-label]',
        'abbr[aria-label]',
        'abbr',
        'button',
        'td',
        'div',
        'span'
      ]
      const _calendarCandidates = _root.find(_calendarSelectors.join(',')).filter(':visible')
      const _match = _calendarCandidates.filter((_, el) => {{
        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const aria = ((el.getAttribute && el.getAttribute('aria-label')) || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const cls = ((el.className || '') + ' ' + (el.getAttribute && el.getAttribute('data-testid') || '')).toLowerCase()

        if (!text && !aria) {{
          return false
        }}
        if (cls.includes('disabled') || cls.includes('inactive') || cls.includes('blocked')) {{
          return false
        }}
        if (_fullDateLabel && aria === _fullDateLabel) {{
          return true
        }}
        if (_targetDate && (aria.includes(_targetDate) || text === _targetDate)) {{
          return true
        }}
        if (_targetDay && text === _targetDay) {{
          return true
        }}
        return false
      }}).first()

      if (_match.length) {{
        cy.wrap(_match).scrollIntoView().click({{ force: true }})
      }} else {{
        cy.wrap(_root)
          .contains('{normalized_date_escaped}', {{ matchCase: false, timeout: 2000 }})
          .scrollIntoView()
          .click({{ force: true }})
      }}
    }})
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
    {selector_cmd}.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot)
      const _match = _root.find('button, [role=\"button\"], li, p, span').filter((_, el) => {{
        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        return text === '{self.escape_string_for_js(actual_class_name.lower().strip())}'
      }}).first()

      if (_match.length) {{
        cy.wrap(_match).scrollIntoView().click({{ force: true }})
      }} else {{
        cy.wrap(_root).contains('{actual_class_name}', {{ matchCase: false }}).scrollIntoView().click({{ force: true }})
      }}
    }})
    cy.wait(500)"""

    def generate_count_selection_command(self, count_str, xpath, element_name):
        """Generate Cypress command for count selection"""
        try:
            target_count = int(count_str.strip())
            element_type = self.resolve_count_element_type(element_name)
            if element_type:
                return self.generate_increment_decrement_command("SELECT_COUNT", str(target_count), xpath, element_name)
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
                "//p[contains(@data-testid,'room-increment')]",
                "//p[@data-testid='room-decrement']"
            )
        if element_type == "adult":
            return (
                "//p[@data-testid='adult-increment']",
                "//p[contains(@data-testid,'adult-decrement')]"
            )
        if element_type == "children":
            return (
                "//p[@data-testid='counter-increment-children']",
                "//p[@data-testid='counter-decrement-children']"
            )
        if element_type == "infant":
            return (
                "//p[@data-testid='counter-increment-infant'] | //p[contains(@data-testid,'infant-increment')]",
                "//p[@data-testid='counter-decrement-infant'] | //p[contains(@data-testid,'infant-decrement')]"
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

    def _get_default_count_value(self, element_type):
        default_map = {
            "room": 1,
            "adult": 2,
            "children": 0,
            "infant": 0,
        }
        return default_map.get((element_type or "").lower(), None)

    def _parse_step_count(self, test_data, default_value=1):
        """Parse requested click count with a safe fallback."""
        try:
            parsed = int(str(test_data).strip())
            return max(parsed, 1)
        except Exception:
            return default_value

    def _has_usable_locator(self, locator):
        text = str(locator or "").strip()
        return bool(text and text.upper() != "NA")

    def _locator_matches_count_direction(self, locator, direction):
        locator_text = str(locator or "").strip().lower()
        if not locator_text:
            return False
        if direction == "increment":
            return "increment" in locator_text
        if direction == "decrement":
            return "decrement" in locator_text
        return False

    def generate_increment_decrement_command(self, action_type, count_str, xpath, element_name):
        """Generate Cypress command for INCREMENT/DECREMENT/SELECT_COUNT."""
        try:
            parsed_target = None
            try:
                parsed_target = int(str(count_str).strip())
            except Exception:
                parsed_target = None
            if parsed_target is not None and parsed_target < 0:
                parsed_target = 0

            fallback_clicks = self._parse_step_count(count_str, default_value=1)

            element_type = self.resolve_count_element_type(element_name)
            locator_text = str(xpath or "").strip()
            has_locator = self._has_usable_locator(locator_text)
            selector_cmd = self._selector_command(xpath) if has_locator else None

            if element_type:
                inc_xpath, dec_xpath = self._get_count_control_xpaths(element_type)
                inc_cmd = self._selector_command(f"xpath={inc_xpath}") if inc_xpath else None
                dec_cmd = self._selector_command(f"xpath={dec_xpath}") if dec_xpath else None
                count_index = self._get_count_input_index(element_type)
                default_current = self._get_default_count_value(element_type)
                default_current_js = "null" if default_current is None else str(default_current)

                increment_click_cmd = selector_cmd or inc_cmd
                if inc_cmd and (not has_locator or not self._locator_matches_count_direction(locator_text, "increment")):
                    increment_click_cmd = inc_cmd

                decrement_click_cmd = selector_cmd or dec_cmd
                if dec_cmd and (not has_locator or not self._locator_matches_count_direction(locator_text, "decrement")):
                    decrement_click_cmd = dec_cmd

                if count_index is not None:
                    if action_type == "INCREMENT" and increment_click_cmd:
                        target_for_runtime = parsed_target if parsed_target is not None else fallback_clicks
                        return f"""{increment_click_cmd}.filter(':visible').first().should('exist')
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot);
      const _readCurrent = () => {{
        const _scopes = [_root, Cypress.$(document.body)];
        const _selectors = [
          "span[data-testid='counter-input']",
          "[data-testid='counter-input']",
          "input[data-testid='counter-input']",
          "[data-testid*='counter-input']"
        ];
        for (const _scope of _scopes) {{
          if (!_scope || !_scope.length) continue;
          for (const _sel of _selectors) {{
            const _visible = _scope.find(_sel).filter(':visible');
            if (_visible.length > {count_index}) {{
              const _node = _visible.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}

            const _all = _scope.find(_sel);
            if (_all.length > {count_index}) {{
              const _node = _all.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
          }}
        }}
        return null;
      }};
      const _target = {target_for_runtime};
      const _hasNumericTarget = {str(parsed_target is not None).lower()};
      const _fallbackSteps = {fallback_clicks};
      const _current = _readCurrent();
      const _defaultCurrent = {default_current_js};
      const _effectiveCurrent = _current !== null ? _current : _defaultCurrent;
      const _steps = (_hasNumericTarget && _effectiveCurrent !== null)
        ? Math.max(_target - _effectiveCurrent, 0)
        : (_hasNumericTarget ? 0 : _fallbackSteps);
      if (_hasNumericTarget && _current === null) {{
        console.warn('INCREMENT target mode used default current count:', _defaultCurrent);
      }}
      for (let i = 0; i < _steps; i += 1) {{ {increment_click_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
    }})"""
                    if action_type == "DECREMENT" and decrement_click_cmd:
                        target_for_runtime = parsed_target if parsed_target is not None else fallback_clicks
                        return f"""{decrement_click_cmd}.filter(':visible').first().should('exist')
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot);
      const _readCurrent = () => {{
        const _scopes = [_root, Cypress.$(document.body)];
        const _selectors = [
          "span[data-testid='counter-input']",
          "[data-testid='counter-input']",
          "input[data-testid='counter-input']",
          "[data-testid*='counter-input']"
        ];
        for (const _scope of _scopes) {{
          if (!_scope || !_scope.length) continue;
          for (const _sel of _selectors) {{
            const _visible = _scope.find(_sel).filter(':visible');
            if (_visible.length > {count_index}) {{
              const _node = _visible.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}

            const _all = _scope.find(_sel);
            if (_all.length > {count_index}) {{
              const _node = _all.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
          }}
        }}
        return null;
      }};
      const _target = {target_for_runtime};
      const _hasNumericTarget = {str(parsed_target is not None).lower()};
      const _fallbackSteps = {fallback_clicks};
      const _current = _readCurrent();
      const _defaultCurrent = {default_current_js};
      const _effectiveCurrent = _current !== null ? _current : _defaultCurrent;
      const _steps = (_hasNumericTarget && _effectiveCurrent !== null)
        ? Math.max(_effectiveCurrent - _target, 0)
        : (_hasNumericTarget ? 0 : _fallbackSteps);
      if (_hasNumericTarget && _current === null) {{
        console.warn('DECREMENT target mode used default current count:', _defaultCurrent);
      }}
      for (let i = 0; i < _steps; i += 1) {{ {decrement_click_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
    }})"""
                    if action_type == "SELECT_COUNT" and (inc_cmd or dec_cmd):
                        target_for_runtime = parsed_target if parsed_target is not None else fallback_clicks
                        if inc_cmd and dec_cmd:
                            probe_cmd = inc_cmd
                            return f"""{probe_cmd}.filter(':visible').first().should('exist')
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot);
      const _readCurrent = () => {{
        const _scopes = [_root, Cypress.$(document.body)];
        const _selectors = [
          "span[data-testid='counter-input']",
          "[data-testid='counter-input']",
          "input[data-testid='counter-input']",
          "[data-testid*='counter-input']"
        ];
        for (const _scope of _scopes) {{
          if (!_scope || !_scope.length) continue;
          for (const _sel of _selectors) {{
            const _visible = _scope.find(_sel).filter(':visible');
            if (_visible.length > {count_index}) {{
              const _node = _visible.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
            const _all = _scope.find(_sel);
            if (_all.length > {count_index}) {{
              const _node = _all.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
          }}
        }}
        return null;
      }};
      const _target = {target_for_runtime};
      const _current = _readCurrent();
      const _defaultCurrent = {default_current_js};
      const _effectiveCurrent = _current !== null ? _current : _defaultCurrent;
      if (_current === null) {{
        console.warn('SELECT_COUNT target mode used default current count:', _defaultCurrent);
      }}
      if (_effectiveCurrent === null) {{
        return;
      }}
      if (_target > _effectiveCurrent) {{
        for (let i = 0; i < (_target - _effectiveCurrent); i += 1) {{ {inc_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
      }} else if (_target < _effectiveCurrent) {{
        for (let i = 0; i < (_effectiveCurrent - _target); i += 1) {{ {dec_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
      }}
    }})"""
                        if inc_cmd:
                            return f"""{inc_cmd}.filter(':visible').first().should('exist')
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot);
      const _readCurrent = () => {{
        const _scopes = [_root, Cypress.$(document.body)];
        const _selectors = [
          "span[data-testid='counter-input']",
          "[data-testid='counter-input']",
          "input[data-testid='counter-input']",
          "[data-testid*='counter-input']"
        ];
        for (const _scope of _scopes) {{
          if (!_scope || !_scope.length) continue;
          for (const _sel of _selectors) {{
            const _visible = _scope.find(_sel).filter(':visible');
            if (_visible.length > {count_index}) {{
              const _node = _visible.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
            const _all = _scope.find(_sel);
            if (_all.length > {count_index}) {{
              const _node = _all.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
          }}
        }}
        return null;
      }};
      const _target = {target_for_runtime};
      const _current = _readCurrent();
      const _defaultCurrent = {default_current_js};
      const _effectiveCurrent = _current !== null ? _current : _defaultCurrent;
      const _steps = (_effectiveCurrent === null) ? 0 : Math.max(_target - _effectiveCurrent, 0);
      if (_current === null) {{
        console.warn('SELECT_COUNT increment-only mode used default current count:', _defaultCurrent);
      }}
      for (let i = 0; i < _steps; i += 1) {{ {inc_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
    }})"""
                        if dec_cmd:
                            return f"""{dec_cmd}.filter(':visible').first().should('exist')
    cy.findActiveLayerRoot('popup').then(($popupRoot) => {{
      const _root = Cypress.$($popupRoot);
      const _readCurrent = () => {{
        const _scopes = [_root, Cypress.$(document.body)];
        const _selectors = [
          "span[data-testid='counter-input']",
          "[data-testid='counter-input']",
          "input[data-testid='counter-input']",
          "[data-testid*='counter-input']"
        ];
        for (const _scope of _scopes) {{
          if (!_scope || !_scope.length) continue;
          for (const _sel of _selectors) {{
            const _visible = _scope.find(_sel).filter(':visible');
            if (_visible.length > {count_index}) {{
              const _node = _visible.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
            const _all = _scope.find(_sel);
            if (_all.length > {count_index}) {{
              const _node = _all.eq({count_index});
              const _raw = ((_node.text && _node.text()) || (_node.val && _node.val()) || (_node.attr && _node.attr('value')) || '').toString().trim();
              const _num = Number.parseInt(_raw.replace(/[^0-9-]/g, ''), 10);
              if (Number.isFinite(_num)) return _num;
            }}
          }}
        }}
        return null;
      }};
      const _target = {target_for_runtime};
      const _current = _readCurrent();
      const _defaultCurrent = {default_current_js};
      const _effectiveCurrent = _current !== null ? _current : _defaultCurrent;
      const _steps = (_effectiveCurrent === null) ? 0 : Math.max(_effectiveCurrent - _target, 0);
      if (_current === null) {{
        console.warn('SELECT_COUNT decrement-only mode used default current count:', _defaultCurrent);
      }}
      for (let i = 0; i < _steps; i += 1) {{ {dec_cmd}.filter(':visible').first().click({{ force: true }}); cy.wait(200); }}
    }})"""

            if selector_cmd:
                return f"for (let i = 0; i < {fallback_clicks}; i += 1) {{ {selector_cmd}.click({{ force: true }}); cy.wait(200); }}"
            return f"// {action_type} skipped: missing locator"
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
                stdout_preview = self._safe_log_preview(stdout)
                stderr_preview = self._safe_log_preview(stderr)
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
