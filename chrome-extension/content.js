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

  function generateXPath(element) {
    const tagName = element.tagName.toLowerCase();
    let xpath = '';
    let elementName = tagName;

    if (element.id && element.id.trim()) {
      xpath = `//*[@id="${element.id}"]`;
      elementName = `#${element.id}`;
    } else if (element.name && element.name.trim()) {
      xpath = `//${tagName}[@name="${element.name}"]`;
      elementName = element.name;
    } else {
      const text = (element.textContent || element.innerText || '').trim();
      if (text && text.length < 100) {
        // For option elements, include parent select context for uniqueness
        if (tagName === 'option' && element.parentElement && element.parentElement.tagName.toLowerCase() === 'select') {
          const selectElement = element.parentElement;
          const selectId = selectElement.id;
          const selectName = selectElement.name;
          let selectXpath = '';
          if (selectId) {
            selectXpath = `//*[@id="${selectId}"]`;
          } else if (selectName) {
            selectXpath = `//select[@name="${selectName}"]`;
          } else {
            selectXpath = '//select';
          }
          xpath = `${selectXpath}/option[contains(text(), "${text.substring(0, 30)}")]`;
        } else {
          xpath = `//${tagName}[contains(text(), "${text.substring(0, 30)}")]`;
        }
        elementName = text.substring(0, 30);
      } else {
        xpath = `//${tagName}`;
      }
    }

    // Get page information
    const pageTitle = document.title || 'Unknown Page';
    const pageUrl = window.location.href;
    const pageDomain = window.location.hostname;

    return {
      xpath: xpath,
      elementName: elementName || tagName,
      tagName: tagName,
      page_name: pageTitle,
      page_url: pageUrl,
      page_domain: pageDomain
    };
  }



})();

