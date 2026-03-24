console.log('QFast Extension: Background script loading at', new Date().toISOString());

let panelState = {
  selectedXPaths: [],
  captureMode: false
};

chrome.runtime.onInstalled.addListener((details) => {
   console.log('QFast Extension: Installed', details);
  
  try {
    chrome.storage.local.get(['captureCount']).then(result => {
      if (result.captureCount === undefined) {
        chrome.storage.local.set({ captureCount: 0 }).catch(error => {
          console.log('Error initializing storage:', error);
        });
      }
    }).catch(error => {
      console.log('Error initializing storage:', error);
    });
  } catch (error) {
    console.log('Error initializing storage:', error);
  }
});

chrome.runtime.onStartup.addListener(() => {
   console.log('QFast Extension: Started');
 });

// Handle keyboard commands
chrome.commands.onCommand.addListener((command) => {
  console.log('Command received:', command);

  if (command === 'open_side_panel') {
    openSidePanel();
  }
});

// Handle browser action click
chrome.action.onClicked.addListener((tab) => {
  console.log('Browser action clicked');
  openSidePanel(tab);
});

function openSidePanel(tabFromGesture = null) {
  const openForTab = (activeTab) => {
    if (!activeTab || !activeTab.id) return;

    const tabId = activeTab.id;
    const windowId = activeTab.windowId;

    // Configure side panel without awaiting to preserve user gesture context for open().
    chrome.sidePanel.setOptions({
      tabId,
      path: 'sidepanel.html',
      enabled: true
    }).catch((setOptionsError) => {
      console.warn('Failed to set tab side panel options:', setOptionsError);
    });

    chrome.sidePanel.open({ tabId }).then(() => {
      console.log('Side panel opened successfully for tab', tabId);
    }).catch((error) => {
      console.warn('Tab-scoped side panel open failed:', error);
      chrome.sidePanel.open({ windowId }).then(() => {
        console.log('Side panel opened successfully for window', windowId);
      }).catch((fallbackError) => {
        console.error('Failed to open side panel:', fallbackError);
      });
    });
  };

  if (tabFromGesture && tabFromGesture.id) {
    openForTab(tabFromGesture);
    return;
  }

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    openForTab(tabs[0]);
  });
}

function isInjectableUrl(url) {
  if (!url) return false;
  const blockedPrefixes = [
    'chrome://',
    'chrome-extension://',
    'edge://',
    'about:',
    'view-source:'
  ];
  return !blockedPrefixes.some(prefix => url.startsWith(prefix));
}

async function ensureContentScriptReady(tab) {
  if (!tab || !tab.id) {
    return { success: false, error: 'No active tab' };
  }

  if (!isInjectableUrl(tab.url)) {
    return { success: false, error: 'Content script not available on this page' };
  }

  try {
    await chrome.tabs.sendMessage(tab.id, { action: 'PING' });
    return { success: true, available: true };
  } catch (pingError) {
    console.log('Initial content script ping failed, attempting injection:', pingError?.message || pingError);
  }

  try {
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ['content.css']
    });
  } catch (cssError) {
    console.log('Content CSS injection skipped/failed:', cssError?.message || cssError);
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });
  } catch (scriptError) {
    return {
      success: false,
      error: scriptError?.message || 'Failed to inject content script'
    };
  }

  try {
    await chrome.tabs.sendMessage(tab.id, { action: 'PING' });
    return { success: true, available: true };
  } catch (retryError) {
    return {
      success: false,
      error: retryError?.message || 'Content script not responding after injection'
    };
  }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Background received:', request.action);

  try {
    // State management
    if (request.type === 'saveState') {
      panelState = { ...panelState, ...request.data };
      console.log('Panel state saved:', panelState);
      if (sendResponse) sendResponse({ success: true, panelState: panelState });
      return;
    }

    if (request.type === 'getState') {
      console.log('Panel state retrieved:', panelState);
      if (sendResponse) sendResponse(panelState);
      return;
    }

    // PING_CONTENT_SCRIPT
    if (request.action === 'PING_CONTENT_SCRIPT') {
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        if (tabs[0] && tabs[0].id) {
          console.log('Pinging content script on tab:', tabs[0].id, 'URL:', tabs[0].url);
          const result = await ensureContentScriptReady(tabs[0]);
          if (!result.success) {
            console.error('Content script ping failed:', result.error);
            if (sendResponse) sendResponse({ success: false, available: false, error: result.error });
            return;
          }
          console.log('Content script ping successful');
          if (sendResponse) sendResponse({ success: true, available: true });
        } else {
          if (sendResponse) sendResponse({ success: false, available: false, error: 'No active tab' });
        }
      });
      return true;
    }

    // START_CAPTURE
    if (request.action === 'START_CAPTURE') {
      panelState.captureMode = true;
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        if (tabs[0] && tabs[0].id) {
          console.log('Sending START_CAPTURE to tab:', tabs[0].url);
          const ready = await ensureContentScriptReady(tabs[0]);
          if (!ready.success) {
            console.error('Failed to prepare content script:', ready.error);
            if (sendResponse) sendResponse({ success: false, error: ready.error });
            return;
          }

          chrome.tabs.sendMessage(tabs[0].id, { action: 'START_CAPTURE' })
            .then(() => {
              console.log('START_CAPTURE sent successfully to tab', tabs[0].id, 'URL:', tabs[0].url);
              if (sendResponse) sendResponse({ success: true });
            })
            .catch(err => {
              console.error('Failed to send START_CAPTURE to tab', tabs[0].id, 'URL:', tabs[0].url, 'Error:', err);
              console.log('Content script not available. Please reload the page or the extension.');
              if (sendResponse) sendResponse({
                success: false,
                error: 'Content script not loaded. Please reload the page and try again.'
              });
            });
        } else {
          console.log('No active tab found');
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
        }
      });
      return true;
    }

    // STOP_CAPTURE
    if (request.action === 'STOP_CAPTURE') {
      panelState.captureMode = false;
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0] && tabs[0].id) {
          console.log('Sending STOP_CAPTURE to tab:', tabs[0].url);
          chrome.tabs.sendMessage(tabs[0].id, { action: 'STOP_CAPTURE' })
            .then(() => {
              console.log('STOP_CAPTURE sent successfully');
              if (sendResponse) sendResponse({ success: true });
            })
            .catch(err => {
              console.error('Failed to send STOP_CAPTURE:', err);
              if (sendResponse) sendResponse({ success: false, error: err.message });
            });
        } else {
          console.log('No active tab found for STOP_CAPTURE');
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
        }
      });
      return true;
    }

    // ELEMENT_CAPTURED - forward to side panel
    if (request.action === 'ELEMENT_CAPTURED') {
      console.log('Element captured, forwarding to side panel');

      if (request.xpathData && request.xpathData.xpath) {
        const captureId = request.xpathData.id || `${request.xpathData.elementName || request.xpathData.element_name || 'Captured Element'}|${request.xpathData.xpath}`;
        const exists = panelState.selectedXPaths.some((item) => {
          const itemId = item.id || `${item.elementName || item.element_name || 'Captured Element'}|${item.xpath || ''}`;
          return itemId === captureId;
        });

        if (!exists) {
          panelState.selectedXPaths = [request.xpathData, ...panelState.selectedXPaths];
        }
      }

      // Send to side panel via runtime message
      chrome.runtime.sendMessage({
        action: 'ELEMENT_CAPTURED',
        xpathData: request.xpathData
      }).catch(err => {
        console.log('Side panel not available:', err);
      });

      if (sendResponse) sendResponse({ success: true });
      return;
    }


    // GET_CAPTURE_STATUS
    if (request.action === 'GET_CAPTURE_STATUS') {
      if (sendResponse) sendResponse({ active: panelState.captureMode });
      return;
    }

    // CAPTURE_MODE_CHANGED
    if (request.action === 'CAPTURE_MODE_CHANGED') {
      panelState.captureMode = request.active || false;
      if (sendResponse) sendResponse({ success: true });
      return;
    }

    // SAVE_XPATHS_TO_BACKEND
    if (request.action === 'SAVE_XPATHS_TO_BACKEND') {
      console.log('Saving XPaths to backend API:', request.xpaths);
      const userEmail = (request.user_email || request.userEmail || 'extension_user').toString().trim() || 'extension_user';

      const enrichedXpaths = (request.xpaths || [])
        .map((xpath) => ({
          element_name: xpath.element_name || xpath.elementName || xpath.object_name || 'Captured Element',
          xpath: xpath.xpath || '',
          page_name: xpath.page_name || 'Unknown Page',
          page_url: xpath.page_url || 'Unknown URL',
          page_domain: xpath.page_domain || 'Unknown Domain'
        }))
        .filter((xpath) => xpath.element_name && xpath.xpath);

      const apiUrl = 'http://10.30.3.85:5000/api/extension-xpaths';
      const requestData = {
        xpaths: enrichedXpaths,
        session_id: request.session_id,
        user_email: userEmail
      };

      fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Email': userEmail
        },
        body: JSON.stringify(requestData)
      })
      .then(response => {
        console.log('API Response status:', response.status);
        if (response.ok) {
          return response.json().then(result => {
            console.log('XPaths saved successfully:', result);

            chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
              const activeTab = tabs && tabs[0];
              if (activeTab && activeTab.id) {
                const ready = await ensureContentScriptReady(activeTab);
                if (ready.success) {
                  chrome.tabs.sendMessage(activeTab.id, {
                    action: 'XPATH_BATCH_SAVED_TO_DATABASE',
                    session_id: result.session_id || request.session_id,
                    count: result.stored_count || enrichedXpaths.length,
                    stored_xpaths: result.stored_xpaths || [],
                    user_email: result.user_email || userEmail,
                    timestamp: new Date().toISOString()
                  }).catch((relayError) => {
                    console.warn('Failed to relay saved XPaths to page:', relayError);
                  });
                } else {
                  console.warn('Skipping page relay because content script is unavailable:', ready.error);
                }
              }
            });

            if (sendResponse) {
              sendResponse({
                success: true,
                session_id: result.session_id || request.session_id,
                stored_count: result.stored_count || enrichedXpaths.length,
                stored_xpaths: result.stored_xpaths || []
              });
            }
          });
        } else {
          return response.text().then(errorText => {
            console.error('Failed to save XPaths:', response.status, errorText);
            if (sendResponse) sendResponse({ success: false, error: `HTTP ${response.status}: ${errorText}` });
          });
        }
      })
      .catch(error => {
        console.error('Error saving XPaths:', error);
        if (sendResponse) sendResponse({ success: false, error: error.message });
      });

      return true; // Keep message channel open for async response
    }

    // BULK_VALIDATE_SELECTORS
    if (request.action === 'BULK_VALIDATE_SELECTORS') {
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs && tabs[0];
        if (!tab || !tab.id) {
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        const ready = await ensureContentScriptReady(tab);
        if (!ready.success) {
          if (sendResponse) sendResponse({ success: false, error: ready.error });
          return;
        }

        chrome.tabs.sendMessage(tab.id, {
          action: 'BULK_VALIDATE_SELECTORS',
          items: request.items || []
        }).then((response) => {
          if (sendResponse) sendResponse(response || { success: false, error: 'No response from content script' });
        }).catch((error) => {
          if (sendResponse) sendResponse({ success: false, error: error.message });
        });
      });
      return true;
    }

    // START_DOM_WATCHER
    if (request.action === 'START_DOM_WATCHER') {
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs && tabs[0];
        if (!tab || !tab.id) {
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        const ready = await ensureContentScriptReady(tab);
        if (!ready.success) {
          if (sendResponse) sendResponse({ success: false, error: ready.error });
          return;
        }

        chrome.tabs.sendMessage(tab.id, {
          action: 'START_DOM_WATCHER',
          items: request.items || []
        }).then((response) => {
          if (sendResponse) sendResponse(response || { success: true });
        }).catch((error) => {
          if (sendResponse) sendResponse({ success: false, error: error.message });
        });
      });
      return true;
    }

    // STOP_DOM_WATCHER
    if (request.action === 'STOP_DOM_WATCHER') {
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs && tabs[0];
        if (!tab || !tab.id) {
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        const ready = await ensureContentScriptReady(tab);
        if (!ready.success) {
          if (sendResponse) sendResponse({ success: false, error: ready.error });
          return;
        }

        chrome.tabs.sendMessage(tab.id, { action: 'STOP_DOM_WATCHER' })
          .then((response) => {
            if (sendResponse) sendResponse(response || { success: true });
          })
          .catch((error) => {
            if (sendResponse) sendResponse({ success: false, error: error.message });
          });
      });
      return true;
    }

    // SCRAPE_PATTERNS
    if (request.action === 'SCRAPE_PATTERNS') {
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs && tabs[0];
        if (!tab || !tab.id) {
          if (sendResponse) sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        const ready = await ensureContentScriptReady(tab);
        if (!ready.success) {
          if (sendResponse) sendResponse({ success: false, error: ready.error });
          return;
        }

        chrome.tabs.sendMessage(tab.id, { action: 'SCRAPE_PATTERNS' })
          .then((response) => {
            if (sendResponse) sendResponse(response || { success: false, error: 'No response from content script' });
          })
          .catch((error) => {
            if (sendResponse) sendResponse({ success: false, error: error.message });
          });
      });
      return true;
    }

    // DOM_WATCH_ALERT - forward to sidepanel
    if (request.action === 'DOM_WATCH_ALERT') {
      chrome.runtime.sendMessage({
        action: 'DOM_WATCH_ALERT',
        payload: request.payload
      }).catch(() => {
        // side panel may not be open
      });

      if (sendResponse) sendResponse({ success: true });
      return;
    }

  } catch (error) {
    console.error('Error handling message:', error);
    if (sendResponse) sendResponse({ success: false, error: error.message });
  }
});

console.log('QFast Extension Background Script: Loaded successfully');
