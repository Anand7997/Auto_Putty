/**
 * Smart XPath Capture - Popup Script
 * Handles popup UI interactions and communication with content script
 */

let isCapturing = false;
let currentMode = 'capture';

// Initialize popup when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Smart XPath Capture popup loaded');
    setupEventListeners();
    updateAPIStatus();
    updateModeUI();
});

function setupEventListeners() {
    // Mode selection
    const captureMode = document.getElementById('captureMode');
    const testMode = document.getElementById('testMode');
    
    if (captureMode) {
        captureMode.addEventListener('click', () => setMode('capture'));
    }
    if (testMode) {
        testMode.addEventListener('click', () => setMode('test'));
    }
    
    // Start Capture button
    const startBtn = document.getElementById('startBtn');
    if (startBtn) {
        startBtn.addEventListener('click', handleStartCapture);
        console.log('Start capture button listener added');
    }
    
    // Stop Capture button
    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.addEventListener('click', handleStopCapture);
        console.log('Stop capture button listener added');
    }
    
    // Test XPath button
    const testBtn = document.getElementById('testXPathBtn');
    if (testBtn) {
        testBtn.addEventListener('click', handleTestXPath);
        console.log('Test XPath button listener added');
    }
}

function setMode(mode) {
    currentMode = mode;
    updateModeUI();
    console.log('Mode set to:', mode);
}

function updateModeUI() {
    const captureMode = document.getElementById('captureMode');
    const testMode = document.getElementById('testMode');
    const testSection = document.getElementById('testSection');
    
    // Update mode button states
    if (captureMode) {
        captureMode.classList.toggle('active', currentMode === 'capture');
    }
    if (testMode) {
        testMode.classList.toggle('active', currentMode === 'test');
    }
    
    // Show/hide test section
    if (testSection) {
        testSection.classList.toggle('active', currentMode === 'test');
    }
    
    // Update button visibility based on mode
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    if (currentMode === 'capture') {
        if (startBtn) startBtn.textContent = isCapturing ? 'Stop Capture' : 'Start Capture';
        if (stopBtn) stopBtn.textContent = isCapturing ? 'Stop Capture' : 'Start Capture';
        if (stopBtn) stopBtn.style.display = 'inline-block';
        if (startBtn) startBtn.style.display = 'inline-block';
    } else {
        if (startBtn) startBtn.textContent = 'Back to Capture';
        if (stopBtn) stopBtn.style.display = 'none';
        if (startBtn) startBtn.style.display = 'inline-block';
    }
}

async function handleStartCapture() {
    console.log('Start capture clicked');
    
    try {
        if (currentMode === 'test') {
            // Switch to capture mode
            setMode('capture');
            return;
        }

        // Send message to background script
        const response = await chrome.runtime.sendMessage({
            action: 'START_CAPTURE'
        });
        
        if (response && response.success) {
            console.log('Capture mode started successfully');
            isCapturing = true;
            updateUIMode(true);
            updateStatus('Capture mode active - Click elements on the page', 'active');
        } else {
            console.error('Failed to start capture mode:', response?.error || response?.message);
            updateStatus('Failed to start capture mode: ' + (response?.error || response?.message || 'Unknown error'), 'error');
        }
        
    } catch (error) {
        console.error('Error starting capture:', error);
        updateStatus('Error starting capture: ' + error.message, 'error');
    }
}

async function handleStopCapture() {
    console.log('Stop capture clicked');
    
    try {
        const response = await chrome.runtime.sendMessage({
            action: 'STOP_CAPTURE'
        });
        
        if (response && response.success) {
            console.log('Capture mode stopped successfully');
            isCapturing = false;
            updateUIMode(false);
            updateStatus('Ready to capture XPath expressions', 'inactive');
        } else {
            console.error('Failed to stop capture mode:', response?.error || response?.message);
            updateStatus('Failed to stop capture mode: ' + (response?.error || response?.message || 'Unknown error'), 'error');
        }
        
    } catch (error) {
        console.error('Error stopping capture:', error);
        updateStatus('Error stopping capture: ' + error.message, 'error');
    }
}

async function handleTestXPath() {
    console.log('Test XPath clicked');
    
    const xpathInput = document.getElementById('xpathInput');
    if (!xpathInput) {
        updateStatus('XPath input field not found', 'error');
        return;
    }
    
    const xpath = xpathInput.value.trim();
    if (!xpath) {
        updateStatus('Please enter an XPath expression to test', 'error');
        return;
    }
    
    console.log('Testing XPath:', xpath);
    
    try {
        const response = await chrome.runtime.sendMessage({
            action: 'TEST_XPATH',
            xpath: xpath
        });
        
        if (response && response.success) {
            console.log('XPath test successful:', response.element);
            updateStatus('XPath test successful! Element found and highlighted.', 'active');
        } else {
            console.error('XPath test failed:', response?.message);
            updateStatus('XPath test failed: ' + (response?.message || 'Element not found'), 'error');
        }
        
    } catch (error) {
        console.error('Error testing XPath:', error);
        updateStatus('Error testing XPath: ' + error.message + '\n\nMake sure you are on a valid webpage.', 'error');
    }
}

function updateUIMode(capturing) {
    updateModeUI(); // Use the updated mode UI function
    
    if (capturing) {
        updateStatus('Capture mode active - Click elements on the page', 'active');
    } else {
        updateStatus('Ready to capture XPath expressions', 'inactive');
    }
}

function updateStatus(message, type) {
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.textContent = message;
        statusEl.className = `status ${type}`;
    }
}

async function updateAPIStatus() {
    const apiStatusEl = document.getElementById('apiStatus');
    if (!apiStatusEl) return;
    
    // Try server first, then localhost fallback
    const healthUrls = [
        'http://15.134.56.119:5000/api/health'
    ];
    
    let response;
    let connected = false;
    
    for (const url of healthUrls) {
        try {
            response = await fetch(url, {
                method: 'GET',
                mode: 'no-cors'
            });
            if (response) {
                connected = true;
                break; // Success, exit loop
            }
        } catch (error) {
            console.log(`Failed to connect to ${url}:`, error.message);
            continue; // Try next URL
        }
    }
    
    if (connected) {
        apiStatusEl.textContent = 'Connected';
        apiStatusEl.className = 'status status-connected';
    } else {
        console.log('API not available: All endpoints failed');
        apiStatusEl.textContent = 'Not Connected';
        apiStatusEl.className = 'status status-disconnected';
    }
}
