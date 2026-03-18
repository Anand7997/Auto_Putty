(function () {
  'use strict';

  let capturedItems = [];
  let latestCaptured = null;
  let lastScrapePayload = null;
  const DEFAULT_SCRAPE_MESSAGE = 'Run scrape mode to extract list/table patterns as JSON.';

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }

  function initialize() {
    bindEvents();
    checkExtensionStatus();
    renderAll();
  }

  function bindEvents() {
    const startCaptureBtn = document.getElementById('start-capture-btn');
    const stopCaptureBtn = document.getElementById('stop-capture-btn');

    if (startCaptureBtn) {
      startCaptureBtn.addEventListener('click', () => {
        startCaptureBtn.disabled = true;
        chrome.runtime.sendMessage({ action: 'PING_CONTENT_SCRIPT' }, (pingResponse) => {
          if (pingResponse && pingResponse.available) {
            chrome.runtime.sendMessage({ action: 'START_CAPTURE' }, (response) => {
              startCaptureBtn.disabled = false;
              if (response && response.success) {
                updateCaptureControls(true);
                showNotification('Capture mode enabled', 'success');
              } else {
                showNotification(response?.error || 'Failed to start capture', 'error');
              }
            });
          } else {
            startCaptureBtn.disabled = false;
            showNotification('Page is not ready for capture. Reload and retry.', 'error');
          }
        });
      });
    }

    if (stopCaptureBtn) {
      stopCaptureBtn.addEventListener('click', () => {
        chrome.runtime.sendMessage({ action: 'STOP_CAPTURE' }, (response) => {
          if (response && response.success) {
            updateCaptureControls(false);
            showNotification('Capture mode stopped', 'success');
          } else {
            showNotification(response?.error || 'Failed to stop capture', 'error');
          }
        });
      });
    }

    const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');
    if (addToTestStepsBtn) {
      addToTestStepsBtn.addEventListener('click', async () => {
        if (!capturedItems.length) return;
        const userEmail = await getCurrentUserEmailFromActiveTab();
        chrome.runtime.sendMessage({
          action: 'SAVE_XPATHS_TO_BACKEND',
          xpaths: capturedItems,
          session_id: `sidepanel_session_${Date.now()}`,
          user_email: userEmail
        }, (response) => {
          if (response && response.success) {
            showNotification('Saved selectors to backend', 'success');
          } else {
            showNotification(response?.error || 'Failed to save selectors', 'error');
          }
        });
      });
    }

    const bulkValidateBtn = document.getElementById('bulk-validate-btn');
    if (bulkValidateBtn) {
      bulkValidateBtn.addEventListener('click', runBulkValidation);
    }

    const startWatcherBtn = document.getElementById('start-watcher-btn');
    const stopWatcherBtn = document.getElementById('stop-watcher-btn');

    if (startWatcherBtn) {
      startWatcherBtn.addEventListener('click', () => {
        chrome.runtime.sendMessage({ action: 'START_DOM_WATCHER', items: capturedItems }, (response) => {
          if (response && response.success) {
            startWatcherBtn.disabled = true;
            if (stopWatcherBtn) stopWatcherBtn.disabled = false;
            showNotification('DOM watcher started', 'success');
          } else {
            showNotification(response?.error || 'Failed to start watcher', 'error');
          }
        });
      });
    }

    if (stopWatcherBtn) {
      stopWatcherBtn.addEventListener('click', () => {
        chrome.runtime.sendMessage({ action: 'STOP_DOM_WATCHER' }, (response) => {
          if (response && response.success) {
            stopWatcherBtn.disabled = true;
            if (startWatcherBtn) startWatcherBtn.disabled = false;
            showNotification('DOM watcher stopped', 'success');
          } else {
            showNotification(response?.error || 'Failed to stop watcher', 'error');
          }
        });
      });
    }

    const scrapeBtn = document.getElementById('scrape-btn');
    if (scrapeBtn) {
      scrapeBtn.addEventListener('click', runScrape);
    }

    const resetPanelBtn = document.getElementById('reset-panel-btn');
    if (resetPanelBtn) {
      resetPanelBtn.addEventListener('click', resetPanelState);
    }

    const exportJsonBtn = document.getElementById('export-json-btn');
    if (exportJsonBtn) {
      exportJsonBtn.addEventListener('click', () => {
        if (!lastScrapePayload) {
          showNotification('Run scrape first', 'error');
          return;
        }
        downloadFile(`qfast-scrape-${todayStamp()}.json`, JSON.stringify(lastScrapePayload, null, 2), 'application/json');
      });
    }

    const exportCsvBtn = document.getElementById('export-csv-btn');
    if (exportCsvBtn) {
      exportCsvBtn.addEventListener('click', () => {
        if (!lastScrapePayload) {
          showNotification('Run scrape first', 'error');
          return;
        }
        const csv = buildCsvFromScrape(lastScrapePayload);
        downloadFile(`qfast-scrape-${todayStamp()}.csv`, csv, 'text/csv');
      });
    }

    chrome.runtime.onMessage.addListener((request) => {
      if (request.action === 'ELEMENT_CAPTURED') {
        addCapturedItem(request.xpathData);
      }

      if (request.action === 'DOM_WATCH_ALERT') {
        handleWatchAlert(request.payload);
      }
    });
  }

  async function getCurrentUserEmailFromActiveTab() {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const activeTab = tabs && tabs[0];
      if (!activeTab || !activeTab.id) return 'extension_user';

      const result = await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        func: () => {
          try {
            const raw = window.localStorage.getItem('qfast_user');
            if (!raw) return 'extension_user';
            const parsed = JSON.parse(raw);
            return parsed?.email || 'extension_user';
          } catch (e) {
            return 'extension_user';
          }
        }
      });

      const value = result && result[0] ? result[0].result : 'extension_user';
      return (value || 'extension_user').toString();
    } catch (error) {
      console.warn('Failed to read qfast_user from active tab localStorage:', error);
      return 'extension_user';
    }
  }

  function runBulkValidation() {
    if (!capturedItems.length) {
      showNotification('Capture selectors first', 'error');
      return;
    }

    chrome.runtime.sendMessage({ action: 'BULK_VALIDATE_SELECTORS', items: capturedItems }, (response) => {
      if (response && response.success) {
        applyValidationResults(response.results || []);
        updateValidationSummary(response.summary || { total: 0, passed: 0, failed: 0, pass_rate: 0 });
        showNotification('Bulk validation completed', 'success');
      } else {
        showNotification(response?.error || 'Bulk validation failed', 'error');
      }
    });
  }

  function runScrape() {
    chrome.runtime.sendMessage({ action: 'SCRAPE_PATTERNS' }, (response) => {
      if (response && response.success) {
        lastScrapePayload = response;
        const output = document.getElementById('scrape-output');
        if (output) output.textContent = JSON.stringify(response, null, 2);
        showNotification('Scrape completed', 'success');
      } else {
        showNotification(response?.error || 'Scrape failed', 'error');
      }
    });
  }

  function resetPanelState() {
    chrome.runtime.sendMessage({ action: 'STOP_CAPTURE' }, () => {
      chrome.runtime.sendMessage({ action: 'STOP_DOM_WATCHER' }, () => {
        applyFreshPanelState();
        showNotification('Panel reset completed', 'success');
      });
    });
  }

  function applyFreshPanelState() {
    capturedItems = [];
    latestCaptured = null;
    lastScrapePayload = null;

    updateCaptureControls(false);
    updateWatcherControls(false);
    updateValidationSummary({ total: 0, passed: 0, failed: 0, pass_rate: 0 });

    const output = document.getElementById('scrape-output');
    if (output) output.textContent = DEFAULT_SCRAPE_MESSAGE;

    renderAll();
    checkExtensionStatus();
  }

  function handleWatchAlert(payload) {
    if (!payload || !payload.summary) return;
    updateValidationSummary(payload.summary);
    applyValidationResults(payload.results || []);

    if (payload.summary.failed > 0) {
      showNotification(`Watcher alert: ${payload.summary.failed} selector(s) invalid`, 'error');
    }
  }

  function applyValidationResults(results) {
    const map = new Map(results.map(r => [r.id, r]));

    capturedItems = capturedItems.map((item) => {
      const id = getItemId(item);
      const found = map.get(id) || map.get(item.xpath) || map.get(item.elementName);
      if (!found) return item;
      return {
        ...item,
        validation: {
          passed: !!found.passed,
          matched_by: found.matched_by || null,
          selector: found.selector || null,
          checked_at: found.checked_at || new Date().toISOString()
        }
      };
    });

    renderList();
  }

  function updateValidationSummary(summary) {
    const el = document.getElementById('validation-summary');
    if (!el) return;
    el.innerHTML = `
      <span>Total: ${summary.total || 0}</span>
      <span>Pass: ${summary.passed || 0}</span>
      <span>Fail: ${summary.failed || 0}</span>
      <span>Pass Rate: ${summary.pass_rate || 0}%</span>
    `;
  }

  function addCapturedItem(rawItem) {
    if (!rawItem || !rawItem.xpath) return;

    const item = {
      ...rawItem,
      id: rawItem.id || getItemId(rawItem),
      elementName: rawItem.elementName || rawItem.element_name || 'Captured Element'
    };

    const exists = capturedItems.some(it => it.xpath === item.xpath);
    if (exists) return;

    capturedItems.unshift(item);
    latestCaptured = item;
    renderAll();
  }

  function removeCapturedItem(itemId) {
    capturedItems = capturedItems.filter(item => getItemId(item) !== itemId);
    if (latestCaptured && getItemId(latestCaptured) === itemId) {
      latestCaptured = capturedItems[0] || null;
    }
    renderAll();
  }

  function renderAll() {
    renderStrategyPanel();
    renderList();
    updateCounter();
  }

  function renderStrategyPanel() {
    const strategyContent = document.getElementById('strategy-content');
    const chip = document.getElementById('reliability-chip');

    if (!strategyContent || !chip) return;

    if (!latestCaptured) {
      strategyContent.classList.add('empty');
      strategyContent.textContent = 'Capture an element to see XPath, CSS, Playwright selectors and reliability scoring.';
      updateScoreChip(chip, 0);
      return;
    }

    strategyContent.classList.remove('empty');
    const score = latestCaptured.reliability_score || latestCaptured.primary_selector?.score || 0;
    updateScoreChip(chip, score);

    const xpathItems = (latestCaptured.strategies && latestCaptured.strategies.xpath) || [latestCaptured.xpath].filter(Boolean);
    const cssItems = (latestCaptured.strategies && latestCaptured.strategies.css) || [latestCaptured.css].filter(Boolean);
    const playItems = (latestCaptured.strategies && latestCaptured.strategies.playwright) || [latestCaptured.playwright].filter(Boolean);

    strategyContent.innerHTML = `
      <div class="strategy-group">
        <p class="strategy-label">Element: ${escapeHtml(latestCaptured.elementName || 'Captured Element')}</p>
        <p class="strategy-label">Primary: ${escapeHtml(latestCaptured.primary_selector?.type || 'xpath')} (${score})</p>
      </div>
      ${renderStrategyGroup('XPath', xpathItems)}
      ${renderStrategyGroup('CSS', cssItems)}
      ${renderStrategyGroup('Playwright', playItems)}
      <div class="strategy-group">
        <p class="strategy-label">Context</p>
        <span class="selector-code">Frame: ${escapeHtml(JSON.stringify(latestCaptured.frame_context || {}))}</span>
        <span class="selector-code">Shadow: ${escapeHtml(JSON.stringify(latestCaptured.shadow_context || {}))}</span>
      </div>
    `;
  }

  function renderStrategyGroup(label, values) {
    const top = (values || []).slice(0, 3);
    if (!top.length) return '';

    return `
      <div class="strategy-group">
        <p class="strategy-label">${label}</p>
        ${top.map(v => `<span class="selector-code">${escapeHtml(v)}</span>`).join('')}
      </div>
    `;
  }

  function renderList() {
    const list = document.getElementById('selected-xpaths-list');
    const addToTestStepsBtn = document.getElementById('add-to-teststeps-btn');

    if (!list) return;

    if (!capturedItems.length) {
      list.innerHTML = '<li class="empty-state">No selectors captured yet.</li>';
      if (addToTestStepsBtn) addToTestStepsBtn.disabled = true;
      return;
    }

    list.innerHTML = capturedItems.map((item) => {
      const score = item.reliability_score || item.primary_selector?.score || 0;
      const status = item.validation
        ? (item.validation.passed ? 'PASS' : 'FAIL')
        : 'UNTESTED';

      return `
        <li class="selector-item" data-id="${escapeHtml(getItemId(item))}">
          <div class="selector-item-head">
            <span class="selector-name">${escapeHtml(item.elementName || 'Captured Element')}</span>
            <span class="score-chip ${scoreClass(score)}">${score}</span>
          </div>
          <div class="selector-meta">${escapeHtml(status)}${item.validation?.matched_by ? ` | ${escapeHtml(item.validation.matched_by)}` : ''}</div>
          <div class="selector-main">${escapeHtml(item.xpath || '')}</div>
          <div class="selector-actions">
            <button class="btn btn-soft" data-action="copy" data-id="${escapeHtml(getItemId(item))}">Copy</button>
            <button class="btn btn-soft" data-action="focus" data-id="${escapeHtml(getItemId(item))}">Focus</button>
            <button class="btn btn-danger" data-action="remove" data-id="${escapeHtml(getItemId(item))}">Remove</button>
          </div>
        </li>
      `;
    }).join('');

    if (addToTestStepsBtn) addToTestStepsBtn.disabled = false;

    list.querySelectorAll('button[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');
        const item = capturedItems.find(it => getItemId(it) === id);
        if (!item) return;

        if (action === 'copy') {
          navigator.clipboard.writeText(item.xpath || '').then(() => {
            showNotification('XPath copied', 'success');
          });
        }

        if (action === 'focus') {
          latestCaptured = item;
          renderStrategyPanel();
        }

        if (action === 'remove') {
          removeCapturedItem(id);
        }
      });
    });
  }

  function updateCounter() {
    const count = document.getElementById('selected-count');
    if (count) count.textContent = String(capturedItems.length);
  }

  function updateCaptureControls(isCapturing) {
    const startBtn = document.getElementById('start-capture-btn');
    const stopBtn = document.getElementById('stop-capture-btn');

    if (startBtn) startBtn.style.display = isCapturing ? 'none' : 'inline-block';
    if (stopBtn) stopBtn.style.display = isCapturing ? 'inline-block' : 'none';
  }

  function updateWatcherControls(isWatching) {
    const startWatcherBtn = document.getElementById('start-watcher-btn');
    const stopWatcherBtn = document.getElementById('stop-watcher-btn');

    if (startWatcherBtn) startWatcherBtn.disabled = !!isWatching;
    if (stopWatcherBtn) stopWatcherBtn.disabled = !isWatching;
  }

  function checkExtensionStatus() {
    updateStatusIndicator('checking', '...', 'Checking');

    chrome.runtime.sendMessage({ action: 'PING_CONTENT_SCRIPT' }, (response) => {
      if (response && response.available) {
        updateStatusIndicator('ready', 'OK', 'Ready');
      } else {
        updateStatusIndicator('not-ready', 'ERR', 'Not Ready');
      }
    });
  }

  function updateStatusIndicator(statusClass, indicator, text) {
    const statusDiv = document.getElementById('extension-status');
    const indicatorSpan = document.getElementById('status-indicator');
    const textSpan = document.getElementById('status-text');

    if (statusDiv) {
      statusDiv.classList.remove('ready', 'not-ready', 'checking');
      statusDiv.classList.add(statusClass);
    }

    if (indicatorSpan) indicatorSpan.textContent = indicator;
    if (textSpan) textSpan.textContent = text;
  }

  function getItemId(item) {
    return item.id || `${item.elementName || 'el'}|${item.xpath || ''}`;
  }

  function scoreClass(score) {
    if (score >= 80) return 'score-high';
    if (score >= 60) return 'score-mid';
    return 'score-low';
  }

  function updateScoreChip(chip, score) {
    chip.textContent = `Score ${score}`;
    chip.classList.remove('score-low', 'score-mid', 'score-high');
    chip.classList.add(scoreClass(score));
  }

  function buildCsvFromScrape(payload) {
    const rows = [['block_type', 'block_id', 'row_index', 'col_index', 'key', 'value']];

    const tables = payload.tables || [];
    tables.forEach((table) => {
      (table.headers || []).forEach((header, i) => {
        rows.push(['table_header', table.id, '', i, '', header]);
      });

      (table.rows || []).forEach((row, rowIndex) => {
        row.forEach((value, colIndex) => {
          rows.push(['table_row', table.id, rowIndex, colIndex, '', value]);
        });
      });
    });

    const lists = payload.lists || [];
    lists.forEach((list) => {
      (list.items || []).forEach((item, idx) => {
        rows.push(['list_item', list.id, idx, '', 'text', item.text || '']);
        (item.links || []).forEach((link, linkIndex) => {
          rows.push(['list_link', list.id, idx, linkIndex, link.text || '', link.href || '']);
        });
      });
    });

    return rows.map(cols => cols.map(csvEscape).join(',')).join('\n');
  }

  function csvEscape(value) {
    const text = String(value ?? '');
    if (/[",\n]/.test(text)) {
      return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
  }

  function downloadFile(name, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function todayStamp() {
    return new Date().toISOString().split('T')[0];
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `xpath-notification ${type === 'error' ? 'error' : 'success'}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
      notification.remove();
    }, 2800);
  }
})();
