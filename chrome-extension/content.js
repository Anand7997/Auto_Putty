(function() {
  'use strict';

  let isCaptureMode = false;
  let highlightedElement = null;
  let lastClickedDropdown = null;

  const initialize = () => {
    console.log('QFast Extension: Content script initialized at', new Date().toISOString(), 'on page:', window.location.href);
    setupMessageListener();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
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
          console.log('QFast Extension: Ping received, content script is available');
          if (sendResponse) sendResponse({ success: true, available: true });
          break;

        case 'START_CAPTURE':
          console.log('QFast Extension: Starting capture mode');
          enableCaptureMode();
          if (sendResponse) sendResponse({ success: true });
          break;

        case 'STOP_CAPTURE':
          console.log('QFast Extension: Stopping capture mode');
          disableCaptureMode();
          if (sendResponse) sendResponse({ success: true });
          break;


        default:
          console.log('QFast Extension: Unknown action:', request.action);
          if (sendResponse) sendResponse({ success: false, error: 'Unknown action' });
      }
    } catch (error) {
      console.error('Content script error handling message:', error);
      if (sendResponse) sendResponse({ success: false, error: error.message });
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


    if (highlightedElement && highlightedElement.style) {
      highlightedElement.style.outline = '';
    }

    console.log('QFast Extension: Capture mode disabled');
  }

  /* -----------------------------
     1) Handle dropdown click
  ------------------------------*/
  function captureDropdownClick(element) {
    try {
      const xpathData = generateXPath(element);
      lastClickedDropdown = element;

      chrome.runtime.sendMessage({
        action: 'ELEMENT_CAPTURED',
        xpathData: {
          ...xpathData,
          elementName: `${xpathData.elementName} (Dropdown)`
        }
      });

      console.log("📌 Captured DROPDOWN CLICK:", xpathData.xpath);
    } catch (e) {
      console.error("Dropdown click capture error:", e);
    }
  }

  /* -----------------------------
     2) Handle dropdown value select
  ------------------------------*/
  function captureDropdownValue(element, selectedText) {
    try {
      const xpathData = generateXPath(element);

      chrome.runtime.sendMessage({
        action: 'ELEMENT_CAPTURED',
        xpathData: {
          ...xpathData,
          elementName: `${xpathData.elementName} (${selectedText})`
        }
      });

      console.log("📌 Captured DROPDOWN VALUE:", xpathData.xpath, selectedText);
    } catch (e) {
      console.error("Dropdown value capture error:", e);
    }
  }

  function handleElementClick(event) {
    if (!isCaptureMode) return;

    const element = event.target;
    console.log('QFast Extension: Click detected on element:', element.tagName, element.id || element.name || element.className, element.textContent?.trim().substring(0, 50));
    if (!element || !element.tagName || isExtensionElement(element)) return;

    /* ---------------------------------------
       1) Detect dropdown trigger click
    ----------------------------------------*/
    if (
        element.getAttribute("role") === "combobox" ||
        element.className.toLowerCase().includes("select") ||
        element.className.toLowerCase().includes("dropdown") ||
        element.tagName.toLowerCase() === "select"
    ) {
        captureDropdownClick(element);
        return;   // allow dropdown to open normally
    }

    /* ---------------------------------------
       2) Detect dropdown option click
    ----------------------------------------*/
    if (
        element.tagName.toLowerCase() === "option" ||
        element.classList.contains("select2-results__option")
    ) {
        const text = element.textContent.trim();
        const parent = lastClickedDropdown || element.closest("select");

        captureDropdownValue(parent, text);
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    try {
      const xpathData = generateXPath(element);
      console.log('QFast Extension: Generated XPath for', element.tagName, ':', xpathData.xpath);

      // Send to side panel
      chrome.runtime.sendMessage({
        action: 'ELEMENT_CAPTURED',
        xpathData: xpathData
      }).catch(err => {
        console.log('QFast Extension: Error sending to background:', err);
      });
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
      element.style.outline = '2px solid #FFD700';
    }
  }

  function handleElementMouseOut(event) {
    if (!isCaptureMode) return;
    if (event.target === highlightedElement && highlightedElement && highlightedElement.style) {
      highlightedElement.style.outline = '';
    }
  }

  function handleElementChange(event) {
    if (!isCaptureMode) return;

    const el = event.target;

    if (el.tagName.toLowerCase() !== "select") return;

    const selectedOption = el.options[el.selectedIndex];
    const selectedText = selectedOption.textContent.trim();

    captureDropdownValue(el, selectedText);
  }

  function handleElementInput(event) {
    if (!isCaptureMode) return;

    const element = event.target;
    console.log('QFast Extension: Input detected on element:', element.tagName, element.id || element.name || element.className, 'value:', element.value);
    if (!element || !element.tagName) return;

    // Handle input elements that might be part of custom dropdowns
    const tagName = element.tagName.toLowerCase();
    if (tagName !== 'input' && tagName !== 'textarea') return;

    // Check if this input might be a dropdown input (has value and is readonly or has dropdown-like attributes)
    const isDropdownInput = element.value && (
      element.readOnly ||
      element.getAttribute('role') === 'combobox' ||
      element.getAttribute('aria-expanded') !== null ||
      element.className.toLowerCase().includes('dropdown') ||
      element.className.toLowerCase().includes('select') ||
      element.placeholder?.toLowerCase().includes('select')
    );

    if (!isDropdownInput) return;

    try {
      const xpathData = generateXPath(element);
      xpathData.elementName = `${xpathData.elementName} (${element.value})`;

      console.log('QFast Extension: Generated XPath for dropdown input:', xpathData.xpath, 'value:', element.value);

      // Send the input element's XPath
      chrome.runtime.sendMessage({
        action: 'ELEMENT_CAPTURED',
        xpathData: xpathData
      }).catch(err => {
        console.log('QFast Extension: Error sending input XPath to background:', err);
      });
    } catch (error) {
      console.error('Error capturing input:', error);
    }
  }

  function setupSelect2Observers() {
    // Find Select2 container elements
    const select2Containers = document.querySelectorAll('[id^="select2-"][id$="-container"]');

    select2Containers.forEach(container => {
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === 'childList' || mutation.type === 'characterData') {
            const text = container.textContent?.trim();
            if (text && text !== 'Select' && text !== 'Select Role' && text !== 'Years' && text !== 'Months' && !text.toLowerCase().includes('select')) {
              console.log('QFast Extension: Select2 selection detected:', container.id, 'value:', text);

              try {
                const xpathData = generateXPath(container);
                xpathData.elementName = `${xpathData.elementName} (${text})`;

                console.log('QFast Extension: Generated XPath for Select2 selection:', xpathData.xpath);

                // Send the container element's XPath
                chrome.runtime.sendMessage({
                  action: 'ELEMENT_CAPTURED',
                  xpathData: xpathData
                }).catch(err => {
                  console.log('QFast Extension: Error sending Select2 XPath to background:', err);
                });
              } catch (error) {
                console.error('Error capturing Select2 selection:', error);
              }
            }
          }
        });
      });

      observer.observe(container, {
        childList: true,
        characterData: true,
        subtree: true
      });

      mutationObservers.push(observer);
    });

    console.log('QFast Extension: Set up', select2Containers.length, 'Select2 observers');
  }

  function cleanupSelect2Observers() {
    mutationObservers.forEach(observer => {
      observer.disconnect();
    });
    mutationObservers = [];
    console.log('QFast Extension: Cleaned up Select2 observers');
  }

  function isExtensionElement(element) {
    // Check if element is part of the side panel (though it shouldn't be in the content)
    return false;
  }

  function escapeXPathString(value) {
    if (value === null || value === undefined) return '""';
    const str = String(value);
    if (!str.includes('"')) return `"${str}"`;
    if (!str.includes("'")) return `'${str}'`;
    const parts = str.split('"');
    const escaped = parts.map(part => `"${part}"`).join(", '\"', ");
    return `concat(${escaped})`;
  }

  function isXPathUnique(xpath) {
    try {
      const result = document.evaluate(
        `count(${xpath})`,
        document,
        null,
        XPathResult.NUMBER_TYPE,
        null
      );
      return result.numberValue === 1;
    } catch (error) {
      return false;
    }
  }

  function getNodeIndexInSiblings(node) {
    if (!node || !node.parentElement) return 1;
    const tagName = node.tagName.toLowerCase();
    let index = 1;
    let sibling = node.previousElementSibling;
    while (sibling) {
      if (sibling.tagName.toLowerCase() === tagName) index++;
      sibling = sibling.previousElementSibling;
    }
    return index;
  }

  function buildAbsoluteXPath(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return '';
    const segments = [];
    let current = element;

    while (current && current.nodeType === Node.ELEMENT_NODE) {
      const tagName = current.tagName.toLowerCase();
      if (current.id && current.id.trim()) {
        segments.unshift(`*[@id=${escapeXPathString(current.id.trim())}]`);
        return `//${segments.join('/')}`;
      }

      const index = getNodeIndexInSiblings(current);
      segments.unshift(`${tagName}[${index}]`);
      current = current.parentElement;
    }

    return `/${segments.join('/')}`;
  }

  function getPreferredElementName(element, tagName) {
    const id = element.id && element.id.trim();
    if (id) return id;

    const preferredAttrs = [
      'name',
      'data-testid',
      'data-test',
      'data-qa',
      'aria-label',
      'placeholder',
      'title'
    ];

    for (const attr of preferredAttrs) {
      const value = element.getAttribute(attr);
      if (value && value.trim()) return value.trim();
    }

    const text = (element.textContent || element.innerText || '').replace(/\s+/g, ' ').trim();
    if (text) return text.substring(0, 40);

    return tagName;
  }

  function generateXPath(element) {
    const tagName = element.tagName.toLowerCase();
    let xpath = '';

    const idValue = element.id && element.id.trim();
    if (idValue) {
      const idXPath = `//*[@id=${escapeXPathString(idValue)}]`;
      if (isXPathUnique(idXPath)) {
        xpath = idXPath;
      } else {
        xpath = `(${idXPath})[1]`;
      }
    }

    if (!xpath) {
      const attrPriority = [
        'name',
        'data-testid',
        'data-test',
        'data-qa',
        'aria-label',
        'placeholder',
        'title',
        'role'
      ];

      for (const attr of attrPriority) {
        const value = element.getAttribute(attr);
        if (!value || !value.trim()) continue;
        const candidate = `//${tagName}[@${attr}=${escapeXPathString(value.trim())}]`;
        if (isXPathUnique(candidate)) {
          xpath = candidate;
          break;
        }
      }
    }

    if (!xpath) {
      const classNames = (element.className || '')
        .toString()
        .split(/\s+/)
        .map(cls => cls.trim())
        .filter(cls => cls && !/\d{4,}/.test(cls) && cls.length > 2)
        .slice(0, 2);

      if (classNames.length > 0) {
        const classPredicate = classNames
          .map(cls => `contains(concat(" ", normalize-space(@class), " "), " ${cls} ")`)
          .join(' and ');
        const classXPath = `//${tagName}[${classPredicate}]`;
        if (isXPathUnique(classXPath)) {
          xpath = classXPath;
        }
      }
    }

    if (!xpath) {
      const text = (element.textContent || element.innerText || '').replace(/\s+/g, ' ').trim();
      if (text) {
        const shortText = text.substring(0, 60);
        const textXPath = `//${tagName}[contains(normalize-space(.), ${escapeXPathString(shortText)})]`;
        if (isXPathUnique(textXPath)) {
          xpath = textXPath;
        }
      }
    }

    if (!xpath) {
      let ancestor = element.parentElement;
      while (ancestor) {
        if (ancestor.id && ancestor.id.trim()) {
          const anchor = `//*[@id=${escapeXPathString(ancestor.id.trim())}]`;
          const index = getNodeIndexInSiblings(element);
          xpath = `${anchor}//${tagName}[${index}]`;
          break;
        }
        ancestor = ancestor.parentElement;
      }
    }

    if (!xpath) {
      xpath = buildAbsoluteXPath(element) || `//${tagName}`;
    }

    const pageTitle = document.title || 'Unknown Page';
    const pageUrl = window.location.href;
    const pageDomain = window.location.hostname;

    return {
      xpath: xpath,
      elementName: getPreferredElementName(element, tagName),
      tagName: tagName,
      page_name: pageTitle,
      page_url: pageUrl,
      page_domain: pageDomain
    };
  }



})();
