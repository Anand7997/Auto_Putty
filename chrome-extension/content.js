(function () {
  'use strict';

  let isCaptureMode = false;
  let highlightedElement = null;
  let lastClickedDropdown = null;

  let domWatcherObserver = null;
  let domWatcherTimer = null;
  let domWatcherEntries = [];
  let lastWatcherAlertAt = 0;

  const SMART_ATTRS = [
    'data-testid',
    'data-testid',
    'data-test',
    'aria-label',
    'name',
    'placeholder',
    'title',
    'role',
    'type'
  ];

  initialize();

  function initialize() {
    console.log('QFast Extension: Content script initialized on', window.location.href);
    setupMessageListener();
  }

  function setupMessageListener() {
    try {
      if (chrome.runtime && chrome.runtime.onMessage) {
        chrome.runtime.onMessage.addListener(handleMessage);
      }
    } catch (error) {
      console.log('QFast Extension: Error setting up message listener:', error);
    }
  }

  function handleMessage(request, sender, sendResponse) {
    console.log('Content script received:', request.action, 'from sender:', sender);

    try {
      switch (request.action) {
        case 'PING':
          sendResponseSafe(sendResponse, { success: true, available: true });
          break;

        case 'START_CAPTURE':
          enableCaptureMode();
          sendResponseSafe(sendResponse, { success: true });
          break;

        case 'STOP_CAPTURE':
          disableCaptureMode();
          sendResponseSafe(sendResponse, { success: true });
          break;

        case 'BULK_VALIDATE_SELECTORS': {
          const validation = bulkValidateSelectors(request.items || []);
          sendResponseSafe(sendResponse, { success: true, ...validation });
          break;
        }

        case 'START_DOM_WATCHER': {
          startDomWatcher(request.items || []);
          sendResponseSafe(sendResponse, { success: true, watching: true, count: domWatcherEntries.length });
          break;
        }

        case 'STOP_DOM_WATCHER':
          stopDomWatcher();
          sendResponseSafe(sendResponse, { success: true, watching: false });
          break;

        case 'SCRAPE_PATTERNS': {
          resetTransientCaptureStyles();
          const payload = scrapePatterns();
          sendResponseSafe(sendResponse, { success: true, ...payload });
          break;
        }

        default:
          sendResponseSafe(sendResponse, { success: false, error: `Unknown action: ${request.action}` });
      }
    } catch (error) {
      console.error('Content script error handling message:', error);
      sendResponseSafe(sendResponse, { success: false, error: error.message });
    }
  }

  function sendResponseSafe(sendResponse, payload) {
    if (typeof sendResponse === 'function') {
      sendResponse(payload);
    }
  }

  function enableCaptureMode() {
    if (isCaptureMode) return;

    isCaptureMode = true;
    document.body.style.cursor = 'crosshair';
    document.addEventListener('click', handleElementClick, true);
    document.addEventListener('mouseover', handleElementHover, true);
    document.addEventListener('mouseout', handleElementMouseOut, true);
    document.addEventListener('change', handleElementChange, true);
    document.addEventListener('input', handleElementInput, true);

    console.log('QFast Extension: Capture mode enabled');
  }

  function disableCaptureMode() {
    if (!isCaptureMode) return;

    isCaptureMode = false;
    document.body.style.cursor = '';
    document.removeEventListener('click', handleElementClick, true);
    document.removeEventListener('mouseover', handleElementHover, true);
    document.removeEventListener('mouseout', handleElementMouseOut, true);
    document.removeEventListener('change', handleElementChange, true);
    document.removeEventListener('input', handleElementInput, true);

    resetTransientCaptureStyles();

    console.log('QFast Extension: Capture mode disabled');
  }

  function resetTransientCaptureStyles() {
    try {
      if (document.body && document.body.style) {
        document.body.style.cursor = '';
      }
    } catch (_) {
      // Ignore style reset errors on restricted pages
    }

    if (highlightedElement && highlightedElement.style) {
      highlightedElement.style.outline = '';
      highlightedElement.style.outlineOffset = '';
    }

    highlightedElement = null;
  }

  function captureDropdownClick(element) {
    try {
      const selectorData = generateSelectorBundle(element);
      lastClickedDropdown = element;

      postCapturedElement({
        ...selectorData,
        elementName: `${selectorData.elementName} (Dropdown)`
      });
    } catch (e) {
      console.error('Dropdown click capture error:', e);
    }
  }

  function captureDropdownValue(element, selectedText) {
    try {
      const selectorData = generateSelectorBundle(element);
      postCapturedElement({
        ...selectorData,
        elementName: `${selectorData.elementName} (${selectedText})`
      });
    } catch (e) {
      console.error('Dropdown value capture error:', e);
    }
  }

  function postCapturedElement(selectorData) {
    chrome.runtime.sendMessage({
      action: 'ELEMENT_CAPTURED',
      xpathData: selectorData
    }).catch(err => {
      console.log('QFast Extension: Error sending capture to background:', err);
    });
  }

  function handleElementClick(event) {
    if (!isCaptureMode) return;

    const element = event.target;
    if (!element || !element.tagName || isExtensionElement(element)) return;

    const classText = typeof element.className === 'string' ? element.className.toLowerCase() : '';
    if (
      element.getAttribute('role') === 'combobox' ||
      classText.includes('select') ||
      classText.includes('dropdown') ||
      element.tagName.toLowerCase() === 'select'
    ) {
      captureDropdownClick(element);
      return;
    }

    if (
      element.tagName.toLowerCase() === 'option' ||
      element.classList.contains('select2-results__option')
    ) {
      const text = normalizeText(element.textContent);
      const parent = lastClickedDropdown || element.closest('select');
      if (parent) captureDropdownValue(parent, text);
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    try {
      const selectorData = generateSelectorBundle(element);
      postCapturedElement(selectorData);
    } catch (error) {
      console.error('Error capturing element:', error);
    }
  }

  function handleElementHover(event) {
    if (!isCaptureMode) return;

    const element = event.target;
    if (!element || !element.tagName || isExtensionElement(element)) return;

    if (highlightedElement && highlightedElement !== element && highlightedElement.style) {
      highlightedElement.style.outline = '';
    }

    highlightedElement = element;
    if (element.style) {
      element.style.outline = '2px solid #14b8a6';
      element.style.outlineOffset = '2px';
    }
  }

  function handleElementMouseOut(event) {
    if (!isCaptureMode) return;
    if (event.target === highlightedElement && highlightedElement && highlightedElement.style) {
      highlightedElement.style.outline = '';
      highlightedElement.style.outlineOffset = '';
    }
  }

  function handleElementChange(event) {
    if (!isCaptureMode) return;
    const el = event.target;
    if (!el || el.tagName.toLowerCase() !== 'select') return;

    const selectedOption = el.options[el.selectedIndex];
    const selectedText = normalizeText(selectedOption ? selectedOption.textContent : '');
    captureDropdownValue(el, selectedText);
  }

  function handleElementInput(event) {
    if (!isCaptureMode) return;

    const element = event.target;
    if (!element || !element.tagName) return;

    const tagName = element.tagName.toLowerCase();
    if (tagName !== 'input' && tagName !== 'textarea') return;

    const classText = typeof element.className === 'string' ? element.className.toLowerCase() : '';
    const isDropdownInput = element.value && (
      element.readOnly ||
      element.getAttribute('role') === 'combobox' ||
      element.getAttribute('aria-expanded') !== null ||
      classText.includes('dropdown') ||
      classText.includes('select') ||
      (element.placeholder || '').toLowerCase().includes('select')
    );

    if (!isDropdownInput) return;

    try {
      const selectorData = generateSelectorBundle(element);
      selectorData.elementName = `${selectorData.elementName} (${element.value})`;
      postCapturedElement(selectorData);
    } catch (error) {
      console.error('Error capturing input:', error);
    }
  }

  function isExtensionElement(element) {
    if (!element || !element.closest) return false;
    return !!element.closest('#xpath-side-panel, #xpath-recorder-panel, #xpath-result-modal');
  }

  function normalizeText(value) {
    return (value || '').replace(/\s+/g, ' ').trim();
  }

  function isLikelyDynamicValue(value) {
    if (!value) return true;
    const token = String(value).trim();
    if (!token) return true;

    if (/^ng-/.test(token) || /ng-/.test(token)) return true;
    if (/react-select-\d+/i.test(token)) return true;
    if (/^[a-f0-9]{8,}$/i.test(token)) return true;
    if (/[a-f0-9]{6,}-[a-f0-9]{4,}/i.test(token)) return true;
    if (/\d{4,}/.test(token)) return true;

    return false;
  }

  function getStableClassTokens(element) {
    if (!element || !element.classList) return [];
    return Array.from(element.classList)
      .map(c => c.trim())
      .filter(c => c && !isLikelyDynamicValue(c) && c.length < 40)
      .slice(0, 3);
  }

  function toXPathLiteral(value) {
    if (value.indexOf('"') === -1) return `"${value}"`;
    if (value.indexOf("'") === -1) return `'${value}'`;
    return `concat("${value.split('"').join('", \'"\', "')}")`;
  }

  function getSiblingIndex(element) {
    let index = 1;
    let sibling = element.previousElementSibling;
    while (sibling) {
      if (sibling.tagName === element.tagName) index += 1;
      sibling = sibling.previousElementSibling;
    }
    return index;
  }

  function evaluateXPath(xpath) {
    try {
      return document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    } catch (e) {
      return null;
    }
  }

  function evaluateCss(selector, root) {
    try {
      return (root || document).querySelectorAll(selector);
    } catch (e) {
      return null;
    }
  }

  function isUniqueXPathForElement(xpath, element) {
    const result = evaluateXPath(xpath);
    return !!result && result.snapshotLength === 1 && result.snapshotItem(0) === element;
  }

  function isUniqueCssForElement(selector, element) {
    const result = evaluateCss(selector);
    return !!result && result.length === 1 && result[0] === element;
  }

  function buildAbsoluteXPath(element) {
    const parts = [];
    let current = element;

    while (current && current.nodeType === Node.ELEMENT_NODE) {
      const tag = current.tagName.toLowerCase();
      const index = getSiblingIndex(current);
      parts.unshift(`${tag}[${index}]`);
      if (tag === 'html') break;
      current = current.parentElement;
    }

    return `/${parts.join('/')}`;
  }

  function buildAbsoluteCssPath(element) {
    const parts = [];
    let current = element;

    while (current && current.nodeType === Node.ELEMENT_NODE) {
      let part = current.tagName.toLowerCase();
      const classes = getStableClassTokens(current);
      if (classes.length) {
        part += `.${classes.join('.')}`;
      } else {
        part += `:nth-of-type(${getSiblingIndex(current)})`;
      }
      parts.unshift(part);
      if (part.startsWith('html')) break;
      current = current.parentElement;
    }

    return parts.join(' > ');
  }

  function getAnchoredXPath(element) {
    let anchor = element;
    let depth = 0;

    while (anchor && depth < 6) {
      const tag = anchor.tagName.toLowerCase();

      if (anchor.id && !isLikelyDynamicValue(anchor.id)) {
        const idXPath = `//*[@id=${toXPathLiteral(anchor.id)}]`;
        if (isUniqueXPathForElement(idXPath, anchor)) {
          return appendRelativeXPath(idXPath, anchor, element);
        }
      }

      for (let i = 0; i < SMART_ATTRS.length; i += 1) {
        const attr = SMART_ATTRS[i];
        const value = anchor.getAttribute && anchor.getAttribute(attr);
        if (!value || isLikelyDynamicValue(value)) continue;

        const anchorXPath = `//${tag}[@${attr}=${toXPathLiteral(value)}]`;
        if (isUniqueXPathForElement(anchorXPath, anchor)) {
          return appendRelativeXPath(anchorXPath, anchor, element);
        }
      }

      anchor = anchor.parentElement;
      depth += 1;
    }

    return '';
  }

  function appendRelativeXPath(anchorXPath, anchorElement, targetElement) {
    if (anchorElement === targetElement) return anchorXPath;

    const steps = [];
    let current = targetElement;

    while (current && current !== anchorElement) {
      const tag = current.tagName.toLowerCase();
      const index = getSiblingIndex(current);
      steps.unshift(`${tag}[${index}]`);
      current = current.parentElement;
    }

    const built = `${anchorXPath}/${steps.join('/')}`;
    return isUniqueXPathForElement(built, targetElement) ? built : '';
  }

  function getAnchoredCssSelector(element) {
    let current = element;
    const segments = [];

    while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
      if (current.id && !isLikelyDynamicValue(current.id)) {
        const idSel = `#${cssEscape(current.id)}`;
        if (evaluateCss(idSel) && evaluateCss(idSel).length === 1) {
          const full = [idSel].concat(segments.reverse()).join(' > ');
          if (isUniqueCssForElement(full, element)) return full;
        }
      }

      const tag = current.tagName.toLowerCase();
      const stableClasses = getStableClassTokens(current);
      let segment = tag;
      if (stableClasses.length) {
        segment += `.${stableClasses.map(cssEscape).join('.')}`;
      } else {
        segment += `:nth-of-type(${getSiblingIndex(current)})`;
      }

      segments.push(segment);
      current = current.parentElement;
    }

    const fallback = segments.reverse().join(' > ');
    return fallback;
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function frameContextInfo() {
    const isInsideFrame = window.self !== window.top;
    return {
      is_iframe: isInsideFrame,
      frame_url: window.location.href
    };
  }

  function getShadowContext(element) {
    const chain = [];
    let currentRoot = element && element.getRootNode ? element.getRootNode() : null;

    while (currentRoot && currentRoot.host) {
      const host = currentRoot.host;
      chain.unshift(getElementShortLabel(host));
      currentRoot = host.getRootNode ? host.getRootNode() : null;
    }

    return {
      in_shadow_dom: chain.length > 0,
      shadow_host_chain: chain
    };
  }

  function getElementShortLabel(element) {
    if (!element || !element.tagName) return 'unknown';
    const tag = element.tagName.toLowerCase();
    if (element.id) return `${tag}#${element.id}`;
    const stable = getStableClassTokens(element);
    if (stable.length) return `${tag}.${stable[0]}`;
    return `${tag}:nth-of-type(${getSiblingIndex(element)})`;
  }

  function buildPlaywrightLocators(element, xpath, cssSelector, textSnippet) {
    const tag = element.tagName.toLowerCase();
    const locators = [];

    const testId = element.getAttribute('data-testid') || element.getAttribute('data-testid');
    if (testId && !isLikelyDynamicValue(testId)) {
      locators.push(`page.getByTestId('${escapeSingle(testId)}')`);
    }

    const role = element.getAttribute('role');
    const label = element.getAttribute('aria-label') || textSnippet;
    if (role && label && label.length <= 70) {
      locators.push(`page.getByRole('${escapeSingle(role)}', { name: '${escapeSingle(label)}' })`);
    }

    if (cssSelector) {
      locators.push(`page.locator('${escapeSingle(cssSelector)}')`);
    }

    if (xpath) {
      locators.push(`page.locator('xpath=${escapeSingle(xpath)}')`);
    }

    if (!locators.length) {
      locators.push(`page.locator('${escapeSingle(tag)}')`);
    }

    return locators;
  }

  function escapeSingle(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  }

  function buildAttributeCandidates(element, tagName) {
    const candidates = [];

    if (element.id && !isLikelyDynamicValue(element.id)) {
      candidates.push({
        type: 'xpath',
        value: `//*[@id=${toXPathLiteral(element.id)}]`,
        reason: 'Stable ID'
      });
      candidates.push({
        type: 'css',
        value: `#${cssEscape(element.id)}`,
        reason: 'Stable ID'
      });
    }

    for (let i = 0; i < SMART_ATTRS.length; i += 1) {
      const attr = SMART_ATTRS[i];
      const value = element.getAttribute && element.getAttribute(attr);
      if (!value || isLikelyDynamicValue(value)) continue;

      candidates.push({
        type: 'xpath',
        value: `//${tagName}[@${attr}=${toXPathLiteral(value)}]`,
        reason: `Stable @${attr}`
      });

      if (attr !== 'role') {
        candidates.push({
          type: 'css',
          value: `${tagName}[${attr}="${value.replace(/"/g, '\\"')}"]`,
          reason: `Stable @${attr}`
        });
      }
    }

    return candidates;
  }

  function scoreCandidate(candidate, isUnique, strategyPriority) {
    let score = 45 + strategyPriority;

    if (isUnique) score += 35;
    if (candidate.reason && candidate.reason.includes('ID')) score += 10;
    if (candidate.value && candidate.value.includes('nth-of-type')) score -= 8;
    if (candidate.value && candidate.value.length > 140) score -= 6;

    if (score > 99) score = 99;
    if (score < 15) score = 15;

    return score;
  }

  function choosePrimaryStrategy(strategies) {
    if (!strategies.length) return null;
    const sorted = [...strategies].sort((a, b) => b.score - a.score);
    return sorted[0];
  }

  function generateSelectorBundle(element) {
    const tagName = element.tagName.toLowerCase();
    const normalizedText = normalizeText(element.textContent || element.innerText || '');
    const textSnippet = normalizedText.substring(0, 80);

    const elementName =
      (element.id && `#${element.id}`) ||
      (element.getAttribute && (element.getAttribute('aria-label') || element.getAttribute('name') || element.getAttribute('placeholder'))) ||
      (textSnippet && textSnippet.substring(0, 30)) ||
      tagName;

    const baseCandidates = buildAttributeCandidates(element, tagName);

    if (textSnippet && textSnippet.length <= 80) {
      baseCandidates.push({
        type: 'xpath',
        value: `//${tagName}[normalize-space()=${toXPathLiteral(textSnippet)}]`,
        reason: 'Visible text'
      });
      baseCandidates.push({
        type: 'xpath',
        value: `//${tagName}[contains(normalize-space(), ${toXPathLiteral(textSnippet.substring(0, 40))})]`,
        reason: 'Partial text'
      });
    }

    const anchoredXPath = getAnchoredXPath(element);
    if (anchoredXPath) {
      baseCandidates.push({ type: 'xpath', value: anchoredXPath, reason: 'Anchored parent-child path' });
    }

    const absoluteXPath = buildAbsoluteXPath(element);
    baseCandidates.push({ type: 'xpath', value: absoluteXPath, reason: 'Absolute fallback' });

    const anchoredCss = getAnchoredCssSelector(element);
    if (anchoredCss) {
      baseCandidates.push({ type: 'css', value: anchoredCss, reason: 'Anchored CSS path' });
    }

    const absoluteCss = buildAbsoluteCssPath(element);
    baseCandidates.push({ type: 'css', value: absoluteCss, reason: 'Absolute CSS fallback' });

    const strategies = [];
    const seen = new Set();

    baseCandidates.forEach((candidate) => {
      const dedupeKey = `${candidate.type}:${candidate.value}`;
      if (seen.has(dedupeKey) || !candidate.value) return;
      seen.add(dedupeKey);

      let unique = false;
      if (candidate.type === 'xpath') unique = isUniqueXPathForElement(candidate.value, element);
      if (candidate.type === 'css') unique = isUniqueCssForElement(candidate.value, element);

      const priority = candidate.type === 'xpath' ? 8 : 6;
      strategies.push({
        ...candidate,
        unique,
        score: scoreCandidate(candidate, unique, priority)
      });
    });

    const primary = choosePrimaryStrategy(strategies) || {
      type: 'xpath',
      value: absoluteXPath,
      score: 50,
      unique: true,
      reason: 'Fallback absolute path'
    };

    const xpathTop = strategies
      .filter(s => s.type === 'xpath')
      .sort((a, b) => b.score - a.score)
      .map(s => s.value);

    const cssTop = strategies
      .filter(s => s.type === 'css')
      .sort((a, b) => b.score - a.score)
      .map(s => s.value);

    const playwrightTop = buildPlaywrightLocators(element, xpathTop[0] || absoluteXPath, cssTop[0] || absoluteCss, textSnippet);

    const fallbackSelectors = strategies
      .filter(s => `${s.type}:${s.value}` !== `${primary.type}:${primary.value}`)
      .sort((a, b) => b.score - a.score)
      .slice(0, 7)
      .map(s => ({ type: s.type, value: s.value, score: s.score, reason: s.reason }));

    const frameInfo = frameContextInfo();
    const shadowInfo = getShadowContext(element);

    const pageTitle = document.title || 'Unknown Page';
    const pageUrl = window.location.href;
    const pageDomain = window.location.hostname;

    return {
      xpath: xpathTop[0] || absoluteXPath,
      css: cssTop[0] || absoluteCss,
      playwright: playwrightTop[0],
      alternatives: xpathTop.slice(0, 5),
      strategies: {
        xpath: xpathTop.slice(0, 5),
        css: cssTop.slice(0, 5),
        playwright: playwrightTop.slice(0, 5)
      },
      strategy_scores: strategies.slice(0, 10),
      reliability_score: primary.score,
      primary_selector: { type: primary.type, value: primary.value, score: primary.score },
      auto_heal: {
        primary: { type: primary.type, value: primary.value },
        retry_order: [
          `${primary.type}:${primary.value}`,
          ...fallbackSelectors.map(s => `${s.type}:${s.value}`)
        ],
        fallback_selectors: fallbackSelectors
      },
      frame_context: frameInfo,
      shadow_context: shadowInfo,
      elementName: elementName || tagName,
      tagName,
      page_name: pageTitle,
      page_url: pageUrl,
      page_domain: pageDomain,
      captured_at: new Date().toISOString()
    };
  }

  function resolveSelector(item) {
    if (!item) return null;

    const candidates = [];

    if (item.primary_selector && item.primary_selector.value) {
      candidates.push(item.primary_selector);
    }

    if (item.xpath) candidates.push({ type: 'xpath', value: item.xpath });
    if (item.css) candidates.push({ type: 'css', value: item.css });

    if (item.auto_heal && Array.isArray(item.auto_heal.fallback_selectors)) {
      item.auto_heal.fallback_selectors.forEach(sel => {
        if (sel && sel.type && sel.value) candidates.push(sel);
      });
    }

    const dedupe = new Set();

    for (let i = 0; i < candidates.length; i += 1) {
      const c = candidates[i];
      const key = `${c.type}:${c.value}`;
      if (dedupe.has(key)) continue;
      dedupe.add(key);

      let matchedElement = null;

      if (c.type === 'xpath') {
        const result = evaluateXPath(c.value);
        if (result && result.snapshotLength > 0) matchedElement = result.snapshotItem(0);
      } else if (c.type === 'css') {
        const result = evaluateCss(c.value);
        if (result && result.length > 0) matchedElement = result[0];
      } else if (c.type === 'playwright') {
        continue;
      }

      if (matchedElement) {
        return {
          success: true,
          matched_by: c.type,
          selector: c.value,
          element: matchedElement
        };
      }
    }

    return { success: false };
  }

  function bulkValidateSelectors(items) {
    const results = items.map((item) => {
      const resolved = resolveSelector(item);
      return {
        id: item.id || item.xpath || item.elementName || `item-${Math.random().toString(36).slice(2, 8)}`,
        elementName: item.elementName || item.element_name || 'Captured Element',
        passed: resolved.success,
        matched_by: resolved.matched_by || null,
        selector: resolved.selector || null,
        page_url: window.location.href,
        checked_at: new Date().toISOString()
      };
    });

    const passedCount = results.filter(r => r.passed).length;
    const failedCount = results.length - passedCount;

    return {
      results,
      summary: {
        total: results.length,
        passed: passedCount,
        failed: failedCount,
        pass_rate: results.length ? Math.round((passedCount / results.length) * 100) : 0
      }
    };
  }

  function startDomWatcher(items) {
    stopDomWatcher();

    domWatcherEntries = Array.isArray(items) ? items : [];

    if (!domWatcherEntries.length) {
      return;
    }

    const triggerCheck = () => {
      const now = Date.now();
      if (now - lastWatcherAlertAt < 2000) return;
      lastWatcherAlertAt = now;

      const validation = bulkValidateSelectors(domWatcherEntries);
      if (validation.summary.failed > 0) {
        chrome.runtime.sendMessage({
          action: 'DOM_WATCH_ALERT',
          payload: validation
        }).catch(() => {
          // Side panel might be closed.
        });
      }
    };

    domWatcherObserver = new MutationObserver(() => triggerCheck());
    domWatcherObserver.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: false
    });

    domWatcherTimer = setInterval(triggerCheck, 5000);
  }

  function stopDomWatcher() {
    if (domWatcherObserver) {
      domWatcherObserver.disconnect();
      domWatcherObserver = null;
    }

    if (domWatcherTimer) {
      clearInterval(domWatcherTimer);
      domWatcherTimer = null;
    }

    domWatcherEntries = [];
  }

  function scrapePatterns() {
    const tables = scrapeTables();
    const lists = scrapeRepeatedLists();

    return {
      summary: {
        table_count: tables.length,
        list_pattern_count: lists.length,
        extracted_blocks: tables.length + lists.length
      },
      tables,
      lists,
      scraped_at: new Date().toISOString(),
      page_url: window.location.href,
      page_title: document.title || 'Unknown Page'
    };
  }

  function scrapeTables() {
    const tables = Array.from(document.querySelectorAll('table'))
      .filter(table => !isExtensionElement(table));

    return tables.slice(0, 20).map((table, index) => {
      const headers = Array.from(table.querySelectorAll('thead th, tr th'))
        .map(th => normalizeText(th.textContent))
        .filter(Boolean);

      const rows = Array.from(table.querySelectorAll('tbody tr, tr'))
        .slice(0, 200)
        .map((tr) => {
          const cols = Array.from(tr.querySelectorAll('td, th')).map(td => normalizeText(td.textContent));
          return cols;
        })
        .filter(r => r.length > 0);

      return {
        id: `table-${index + 1}`,
        selector: buildAbsoluteCssPath(table),
        headers,
        rows
      };
    }).filter(t => t.rows.length > 0);
  }

  function scrapeRepeatedLists() {
    const parentMap = new Map();

    const scanTargets = Array.from(document.querySelectorAll('ul, ol, div, section, article'));
    scanTargets.forEach((parent) => {
      if (isExtensionElement(parent)) return;
      if (!parent.children || parent.children.length < 3) return;

      const tagCounts = {};
      Array.from(parent.children).forEach((child) => {
        const key = child.tagName.toLowerCase();
        tagCounts[key] = (tagCounts[key] || 0) + 1;
      });

      const dominantEntry = Object.entries(tagCounts).sort((a, b) => b[1] - a[1])[0];
      if (!dominantEntry || dominantEntry[1] < 3) return;

      const [dominantTag, count] = dominantEntry;
      const key = `${buildAbsoluteCssPath(parent)}|${dominantTag}`;
      if (parentMap.has(key)) return;

      const items = Array.from(parent.children)
        .filter(child => child.tagName.toLowerCase() === dominantTag)
        .slice(0, 200)
        .map((child) => {
          const text = normalizeText(child.textContent).substring(0, 600);
          const links = Array.from(child.querySelectorAll('a[href]')).map(a => ({
            text: normalizeText(a.textContent),
            href: a.href
          }));
          return { text, links };
        });

      parentMap.set(key, {
        id: `list-${parentMap.size + 1}`,
        parent_selector: buildAbsoluteCssPath(parent),
        item_tag: dominantTag,
        count,
        items
      });
    });

    return Array.from(parentMap.values());
  }
})();
