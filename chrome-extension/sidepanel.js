// Smart XPath Capture - Side Panel Script
// Handles the official Chrome side panel functionality

(function() {
    'use strict';

    console.log('Smart XPath Capture: Side panel script loading...');

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }

    function initialize() {
        console.log('Smart XPath Capture: Side panel initializing...');

        // Setup event listeners
        setupSidePanelEventListeners();

        // Load any existing state
        loadExistingState();

        // Check extension status
        checkExtensionStatus();

        console.log('Smart XPath Capture: Side panel initialized');
    }

    function checkExtensionStatus() {
        updateStatusIndicator('checking', '⏳', 'Checking...');

        chrome.runtime.sendMessage({ action: 'PING_CONTENT_SCRIPT' }, (response) => {
            if (response && response.available) {
                updateStatusIndicator('ready', '✅', 'Ready');
                console.log('Extension status: Content script available');
            } else {
                updateStatusIndicator('not-ready', '❌', 'Not Ready');
                console.log('Extension status: Content script not available');
            }
        });
    }

    function updateStatusIndicator(statusClass, indicator, text) {
        const statusDiv = document.getElementById('extension-status');
        const indicatorSpan = document.getElementById('status-indicator');
        const textSpan = document.getElementById('status-text');

        if (statusDiv) {
            // Remove existing status classes
            statusDiv.classList.remove('ready', 'not-ready', 'checking');
            // Add new status class
            statusDiv.classList.add(statusClass);
        }

        if (indicatorSpan) indicatorSpan.textContent = indicator;
        if (textSpan) textSpan.textContent = text;
    }

    function setupSidePanelEventListeners() {
        // Close button
        const closeBtn = document.querySelector('.xpath-panel-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                chrome.sidePanel.setOptions({ enabled: false });
            });
        }

        // Minimize button - remove for side panel
        const minimizeBtn = document.querySelector('.xpath-panel-minimize');
        if (minimizeBtn) {
            minimizeBtn.style.display = 'none';
        }

        // Start Capture button
        const startCaptureBtn = document.getElementById('start-capture-btn');
        console.log('Start capture button found:', !!startCaptureBtn);
        if (startCaptureBtn) {
            startCaptureBtn.addEventListener('click', function() {
                console.log('Start capture button clicked');
                startCaptureBtn.disabled = true;
                startCaptureBtn.textContent = 'Checking...';

                // First ping to check if content script is available
                chrome.runtime.sendMessage({ action: 'PING_CONTENT_SCRIPT' }, (pingResponse) => {
                    console.log('Content script ping response:', pingResponse);

                    if (pingResponse && pingResponse.available) {
                        // Content script is available, proceed with start capture
                        updateStatusIndicator('ready', '✅', 'Ready');
                        startCaptureBtn.textContent = 'Starting...';
                        chrome.runtime.sendMessage({ action: 'START_CAPTURE' }, (response) => {
                            console.log('START_CAPTURE response:', response);
                            startCaptureBtn.disabled = false;
                            startCaptureBtn.textContent = '🎯 Start Capture';
                            if (response && response.success) {
                                updateCaptureControls(true);
                                console.log('Capture started successfully');
                            } else {
                                console.error('Failed to start capture:', response);
                                alert('Failed to start capture: ' + (response ? response.error : 'Unknown error'));
                            }
                        });
                    } else {
                        // Content script not available
                        updateStatusIndicator('not-ready', '❌', 'Not Ready');
                        startCaptureBtn.disabled = false;
                        startCaptureBtn.textContent = '🎯 Start Capture';
                        console.error('Content script not available:', pingResponse);
                        alert('Extension not ready on this page.\n\nPlease reload the page and try again.');
                    }
                });
            });
        }

        // Stop Capture button
        const stopCaptureBtn = document.getElementById('stop-capture-btn');
        console.log('Stop capture button found:', !!stopCaptureBtn);
        if (stopCaptureBtn) {
            stopCaptureBtn.addEventListener('click', function() {
                console.log('Stop capture button clicked');
                chrome.runtime.sendMessage({ action: 'STOP_CAPTURE' }, (response) => {
                    console.log('STOP_CAPTURE response:', response);
                    if (response && response.success) {
                        updateCaptureControls(false);
                    } else {
                        alert('Failed to stop capture: ' + (response ? response.error : 'Unknown error'));
                    }
                });
            });
        }

        // Add to TestSteps button
        const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');
        if (addToTestStepsBtn) {
            addToTestStepsBtn.addEventListener('click', function() {
                console.log('Add to TestSteps button clicked');
                // Collect XPaths from the list
                const xpathItems = document.querySelectorAll('#selected-xpaths-list li[data-xpath]');
                const xpaths = Array.from(xpathItems).map(item => ({
                    xpath: item.getAttribute('data-xpath'),
                    elementName: item.textContent.split(':')[0].trim(),
                    page_name: item.getAttribute('data-page-name') || document.title || 'Unknown Page',
                    page_url: item.getAttribute('data-page-url') || window.location.href || 'Unknown URL',
                    page_domain: item.getAttribute('data-page-domain') || window.location.hostname || 'Unknown Domain'
                }));

                console.log('Collected XPaths:', xpaths);

                // Send XPaths directly to backend database only
                chrome.runtime.sendMessage({
                    action: 'SAVE_XPATHS_TO_BACKEND',
                    xpaths: xpaths,
                    session_id: 'sidepanel_session_' + Date.now()
                }, (response) => {
                    console.log('SAVE_XPATHS_TO_BACKEND response:', response);
                    if (response && response.success) {
                        // Clear the list after successful save to database
                        const list = document.getElementById('selected-xpaths-list');
                        if (list) {
                            list.innerHTML = '<li class="empty-section-b">No XPaths selected yet</li>';
                            updateXPathCount();
                        }
                        console.log('✅ XPaths saved to database successfully');
                    } else {
                        console.error('❌ Failed to save XPaths to database:', response ? response.error : 'Unknown error');
                        alert('Failed to save XPaths to database: ' + (response ? response.error : 'Unknown error'));
                    }
                });
            });
        }
    }

    function updateCaptureControls(isCapturing) {
        const startBtn = document.getElementById('start-capture-btn');
        const stopBtn = document.getElementById('stop-capture-btn');

        if (isCapturing) {
            if (startBtn) startBtn.style.display = 'none';
            if (stopBtn) stopBtn.style.display = 'inline-flex';
        } else {
            if (startBtn) startBtn.style.display = 'inline-flex';
            if (stopBtn) stopBtn.style.display = 'none';
        }
    }

    function loadExistingState() {
        // Load any existing XPath data from storage
        chrome.storage.local.get(['xpathData'], (result) => {
            if (result.xpathData) {
                updateXPathDisplay(result.xpathData);
            }
        });
    }

    function updateXPathDisplay(data) {
        // Update the side panel with XPath data
        const sectionAContent = document.getElementById('section-a-content');
        if (sectionAContent && data.finalXPath) {
            sectionAContent.innerHTML = `
                <div class="xpath-display-section">
                    <div class="xpath-display-title">
                        🎯 Best XPath (Score: ${data.score || 0}/100)
                    </div>
                    <div class="xpath-display">${data.finalXPath}</div>
                    <div style="margin-top: 12px;">
                        <button class="copy-btn" data-xpath="${data.finalXPath}">
                            📋 Copy
                        </button>
                        <button class="add-btn" data-xpath="${data.finalXPath}">
                            ➕ Add to Panel
                        </button>
                    </div>
                </div>
            `;

            // Add event listeners for buttons
            setupXPathButtons();
        }
    }

    function updateSelectedXPaths(xpaths) {
        const list = document.getElementById('selected-xpaths-list');
        const countSpan = document.getElementById('selected-count');
        const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');

        if (countSpan) {
            countSpan.textContent = xpaths ? xpaths.length : 0;
        }

        if (addToTestStepsBtn) {
            const shouldDisable = !xpaths || xpaths.length === 0;
            addToTestStepsBtn.disabled = shouldDisable;
            addToTestStepsBtn.textContent = shouldDisable ? '📌 Add to TestSteps' : `📌 Add to TestSteps (${xpaths.length})`;
        }

        if (list) {
            if (!xpaths || xpaths.length === 0) {
                list.innerHTML = '<li class="empty-section-b">No XPaths selected yet</li>';
            } else {
                list.innerHTML = xpaths.map(item => `
                    <li class="selected-xpath-item">
                        <div class="selected-xpath-text">${item.xpath}</div>
                        <button class="remove-xpath-btn" data-xpath="${encodeURIComponent(item.xpath)}">
                            ×
                        </button>
                    </li>
                `).join('');

                // Add remove event listeners
                const removeBtns = list.querySelectorAll('.remove-xpath-btn');
                removeBtns.forEach(btn => {
                    btn.addEventListener('click', function() {
                        const encodedXpath = this.getAttribute('data-xpath');
                        if (encodedXpath) {
                            const xpath = decodeURIComponent(encodedXpath);
                            removeXPath(xpath);
                        }
                    });
                });
            }
        }
    }

    function setupXPathButtons() {
        // Copy buttons
        const copyBtns = document.querySelectorAll('.copy-btn');
        copyBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const xpath = this.getAttribute('data-xpath');
                if (xpath) {
                    navigator.clipboard.writeText(xpath).then(() => {
                        showNotification('✅ XPath copied to clipboard!');
                    });
                }
            });
        });

        // Add buttons
        const addBtns = document.querySelectorAll('.add-btn');
        addBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const xpath = this.getAttribute('data-xpath');
                if (xpath) {
                    addXPathToSelection(xpath);
                }
            });
        });
    }

    function addXPathToSelection(xpath) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0] && tabs[0].id) {
                chrome.tabs.sendMessage(tabs[0].id, {
                    action: 'ADD_XPATH_TO_SELECTION',
                    xpath: xpath
                });
            }
        });
    }

    function removeXPath(xpath) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0] && tabs[0].id) {
                chrome.tabs.sendMessage(tabs[0].id, {
                    action: 'REMOVE_XPATH_FROM_SELECTION',
                    xpath: xpath
                });
            }
        });
    }

    function addCapturedXPathToPanel(xpathData) {
        if (!xpathData || !xpathData.xpath) return;

        const list = document.getElementById('selected-xpaths-list');
        const countSpan = document.getElementById('selected-count');
        const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');

        if (!list) return;

        // Check if XPath already exists - use querySelectorAll to avoid CSS selector issues
        const existingItems = list.querySelectorAll('li[data-xpath]');
        for (let item of existingItems) {
            if (item.getAttribute('data-xpath') === xpathData.xpath) {
                return; // Already exists
            }
        }

        // Remove empty message if present
        const emptySection = list.querySelector('.empty-section-b');
        if (emptySection) {
            list.removeChild(emptySection);
        }

        // Create new list item
        const li = document.createElement('li');
        li.className = 'selected-xpath-item';
        li.setAttribute('data-xpath', xpathData.xpath);
        li.setAttribute('data-page-name', xpathData.page_name || 'Unknown Page');
        li.setAttribute('data-page-url', xpathData.page_url || 'Unknown URL');
        li.setAttribute('data-page-domain', xpathData.page_domain || 'Unknown Domain');
        li.innerHTML = `
            <div class="selected-xpath-text">
                <span class="element-name">${xpathData.elementName || 'Element'}</span>
                <span class="page-info">[${xpathData.page_name || 'Unknown Page'}]</span>
                <div class="xpath-value">${xpathData.xpath}</div>
            </div>
            <button class="remove-xpath-btn" data-xpath="${encodeURIComponent(xpathData.xpath)}">
                ×
            </button>
        `;

        // Add remove event listener
        const removeBtn = li.querySelector('.remove-xpath-btn');
        removeBtn.addEventListener('click', function() {
            const encodedXpath = this.getAttribute('data-xpath');
            if (encodedXpath) {
                const xpath = decodeURIComponent(encodedXpath);
                removeXPath(xpath);
                li.remove();
                updateXPathCount();
            }
        });

        list.appendChild(li);
        updateXPathCount();
    }

    function updateXPathCount() {
        const countSpan = document.getElementById('selected-count');
        const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');
        const list = document.getElementById('selected-xpaths-list');

        const itemCount = list.querySelectorAll('li[data-xpath]').length;
        if (countSpan) {
            countSpan.textContent = itemCount;
        }

        if (addToTestStepsBtn) {
            const shouldDisable = itemCount === 0;
            addToTestStepsBtn.disabled = shouldDisable;
            addToTestStepsBtn.textContent = shouldDisable ? '📌 Add to TestSteps' : `📌 Add to TestSteps (${itemCount})`;
        }
    }

    function showNotification(message) {
        const notification = document.createElement('div');
        notification.className = 'xpath-notification success';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #38a169;
            color: white;
            padding: 12px 16px;
            border-radius: 6px;
            z-index: 10000;
            font-family: Arial, sans-serif;
        `;
        document.body.appendChild(notification);
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 2500);
    }

    // Listen for messages from content script
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'SHOW_XPATH_RESULT') {
        updateXPathDisplay(request.xpathData);
      } else if (request.action === 'UPDATE_SELECTED_XPATHS') {
        updateSelectedXPaths(request.xpaths);
      } else if (request.action === 'ELEMENT_CAPTURED') {
        // Handle captured element from content script
        addCapturedXPathToPanel(request.xpathData);
      }
    });

    // Listen for tab updates to refresh status
    chrome.tabs.onActivated.addListener((activeInfo) => {
      console.log('Tab activated, checking extension status');
      checkExtensionStatus();
    });

    chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
      if (changeInfo.status === 'complete') {
        console.log('Tab updated, checking extension status');
        checkExtensionStatus();
      }
    });

})();