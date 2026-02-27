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
  openSidePanel();
});

function openSidePanel() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0] && tabs[0].id) {
      chrome.sidePanel.open({ tabId: tabs[0].id }).then(() => {
        console.log('Side panel opened successfully');
      }).catch((error) => {
        console.error('Failed to open side panel:', error);
      });
    }
  });
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
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0] && tabs[0].id) {
          console.log('Pinging content script on tab:', tabs[0].id, 'URL:', tabs[0].url);
          chrome.tabs.sendMessage(tabs[0].id, { action: 'PING' })
            .then(response => {
              console.log('Content script ping successful:', response);
              if (sendResponse) sendResponse({ success: true, available: true });
            })
            .catch(err => {
              console.error('Content script ping failed:', err);
              if (sendResponse) sendResponse({ success: false, available: false, error: err.message });
            });
        } else {
          if (sendResponse) sendResponse({ success: false, available: false, error: 'No active tab' });
        }
      });
      return true;
    }

    // START_CAPTURE
    if (request.action === 'START_CAPTURE') {
      panelState.captureMode = true;
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0] && tabs[0].id) {
          console.log('Sending START_CAPTURE to tab:', tabs[0].url);
          // Check if content script should be available
          if (tabs[0].url && (tabs[0].url.startsWith('chrome://') || tabs[0].url.startsWith('chrome-extension://'))) {
            console.log('Cannot inject on chrome:// or chrome-extension:// pages');
            if (sendResponse) sendResponse({ success: false, error: 'Content script not available on this page' });
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

      // Ensure page information is included in XPath data
      const enrichedXpaths = request.xpaths.map(xpath => ({
        ...xpath,
        page_name: xpath.page_name || 'Unknown Page',
        page_url: xpath.page_url || 'Unknown URL',
        page_domain: xpath.page_domain || 'Unknown Domain'
      }));

      const apiUrl = 'http://10.30.3.85:5000/api/extension-xpaths';
      const requestData = {
        xpaths: enrichedXpaths,
        session_id: request.session_id
      };

      fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Email': 'extension_user'
        },
        body: JSON.stringify(requestData)
      })
      .then(response => {
        console.log('API Response status:', response.status);
        if (response.ok) {
          return response.json().then(result => {
            console.log('XPaths saved successfully:', result);
            if (sendResponse) sendResponse({ success: true, session_id: request.session_id });
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

  } catch (error) {
    console.error('Error handling message:', error);
    if (sendResponse) sendResponse({ success: false, error: error.message });
  }
});

console.log('QFast Extension Background Script: Loaded successfully');
