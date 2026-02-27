(function() {
  'use strict';

  let selectedXPaths = [];
  let isCaptureMode = false;
  let isMinimized = false;
  let panelElement = null;
  let dragStartX = 0;
  let dragStartY = 0;
  let panelStartX = 0;
  let panelStartY = 0;
  let isDragging = false;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }

  function initialize() {
    console.log('Smart XPath Recorder: Panel initializing...');

    panelElement = document.getElementById('xpath-recorder-panel');
    if (!panelElement) {
      console.error('Panel element not found');
      return;
    }

    setupEventListeners();
    setupDragability();
    loadInitialState();

    console.log('Smart XPath Recorder: Panel initialized');
  }

  function setupEventListeners() {
    const startBtn = document.getElementById('start-capture-btn');
    const stopBtn = document.getElementById('stop-capture-btn');
    const addBtn = document.getElementById('add-to-teststeps-btn');
    const closeBtn = document.getElementById('close-btn');
    const minimizeBtn = document.getElementById('minimize-btn');

    if (startBtn) {
      startBtn.addEventListener('click', () => {
        isCaptureMode = true;
        updateCaptureUI();
        chrome.runtime.sendMessage({ action: 'START_CAPTURE' });
      });
    }

    if (stopBtn) {
      stopBtn.addEventListener('click', () => {
        isCaptureMode = false;
        updateCaptureUI();
        chrome.runtime.sendMessage({ action: 'STOP_CAPTURE' });
      });
    }

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        if (selectedXPaths.length > 0) {
          sendXPathsToFrontend(selectedXPaths);
          selectedXPaths = [];
          updateXPathList();
          updateRecordingStatus('✓ XPaths sent to TestSteps - ready to record again');
        }
      });
    }

    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        if (panelElement) {
          panelElement.remove();
        }
      });
    }

    if (minimizeBtn) {
      minimizeBtn.addEventListener('click', toggleMinimize);
    }
  }

  function setupDragability() {
    const header = document.getElementById('panel-header');
    if (!header) return;

    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('.header-btn')) return;
      
      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      
      if (panelElement) {
        const rect = panelElement.getBoundingClientRect();
        panelStartX = rect.left;
        panelStartY = rect.top;
        panelElement.classList.add('dragging');
      }
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging || !panelElement) return;

      const deltaX = e.clientX - dragStartX;
      const deltaY = e.clientY - dragStartY;

      const newX = panelStartX + deltaX;
      const newY = panelStartY + deltaY;

      panelElement.style.left = newX + 'px';
      panelElement.style.top = newY + 'px';
      panelElement.style.right = 'auto';
    });

    document.addEventListener('mouseup', () => {
      if (isDragging && panelElement) {
        isDragging = false;
        panelElement.classList.remove('dragging');
      }
    });
  }

  function toggleMinimize() {
    isMinimized = !isMinimized;
    
    if (isMinimized) {
      panelElement.style.width = '60px';
      panelElement.style.height = '60px';
      panelElement.style.borderRadius = '50%';
      const body = panelElement.querySelector('.recorder-body');
      if (body) body.style.display = 'none';
    } else {
      panelElement.style.width = '380px';
      panelElement.style.height = 'auto';
      panelElement.style.borderRadius = '12px';
      const body = panelElement.querySelector('.recorder-body');
      if (body) body.style.display = 'flex';
    }
  }

  function updateCaptureUI() {
    const startBtn = document.getElementById('start-capture-btn');
    const stopBtn = document.getElementById('stop-capture-btn');
    const status = document.getElementById('recording-status');

    if (isCaptureMode) {
      if (startBtn) startBtn.style.display = 'none';
      if (stopBtn) stopBtn.style.display = 'block';
      if (status) {
        status.textContent = '🔴 Recording... Click elements to capture XPath';
        status.classList.add('active');
      }
    } else {
      if (startBtn) startBtn.style.display = 'block';
      if (stopBtn) stopBtn.style.display = 'none';
      if (status) {
        status.textContent = 'Recording stopped. Click "Start Recording" to continue.';
        status.classList.remove('active');
      }
    }
  }

  function addCapturedXPath(xpathData) {
    if (!xpathData || !xpathData.xpath) return;

    const exists = selectedXPaths.some(item => item.xpath === xpathData.xpath);
    if (!exists) {
      selectedXPaths.push(xpathData);
      updateXPathList();
    }
  }

  function removeCapturedXPath(xpath) {
    selectedXPaths = selectedXPaths.filter(item => item.xpath !== xpath);
    updateXPathList();
  }

  function updateXPathList() {
    const list = document.getElementById('selected-xpaths-list');
    const count = document.getElementById('selected-count');
    const addBtn = document.getElementById('add-to-teststeps-btn');

    if (!list) return;

    if (selectedXPaths.length === 0) {
      list.innerHTML = '<li class="empty-section">No XPaths captured yet</li>';
      if (count) count.textContent = '0';
      if (addBtn) addBtn.disabled = true;
      return;
    }

    list.innerHTML = selectedXPaths.map((item, index) => `
      <li>
        <div class="xpath-item-content">
          <div class="xpath-item-name">${item.elementName || 'Element'}</div>
          <div class="xpath-item-xpath">${item.xpath}</div>
        </div>
        <button class="xpath-item-delete" data-index="${index}" title="Delete">×</button>
      </li>
    `).join('');

    if (count) count.textContent = selectedXPaths.length;
    if (addBtn) addBtn.disabled = false;

    list.querySelectorAll('.xpath-item-delete').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const index = parseInt(e.target.dataset.index);
        if (index >= 0 && index < selectedXPaths.length) {
          removeCapturedXPath(selectedXPaths[index].xpath);
        }
      });
    });
  }

  function updateRecordingStatus(message) {
    const status = document.getElementById('recording-status');
    if (status) {
      status.textContent = message;
    }
  }

  function sendXPathsToFrontend(xpaths) {
    console.log('Sending XPaths to frontend:', xpaths);

    chrome.runtime.sendMessage({
      action: 'ADD_XPATH_TO_FRONTEND',
      xpaths: xpaths,
      timestamp: new Date().toISOString()
    }).then(response => {
      console.log('XPaths sent to frontend successfully:', response);
    }).catch(error => {
      console.error('Failed to send XPaths to frontend:', error);
    });
  }

  function loadInitialState() {
    chrome.runtime.sendMessage({ type: 'getState' }).then(state => {
      if (state && state.selectedXPaths) {
        selectedXPaths = state.selectedXPaths;
        isCaptureMode = state.captureMode || false;
        updateXPathList();
        updateCaptureUI();
      }
    }).catch(err => {
      console.log('Could not load state:', err);
    });
  }

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log('Panel received message:', request.action);

    switch (request.action) {
      case 'ELEMENT_CAPTURED':
        if (request.xpathData && isCaptureMode) {
          addCapturedXPath(request.xpathData);
        }
        break;

      case 'CAPTURE_MODE_CHANGED':
        isCaptureMode = request.active || false;
        updateCaptureUI();
        break;
    }
  });
})();
