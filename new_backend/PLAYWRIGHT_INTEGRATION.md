# Playwright Integration Documentation

## Overview

The Flask application now supports both Selenium and Playwright test executors, allowing users to choose between different browser automation frameworks for test execution.

## New Endpoints Added

### 1. Playwright-Specific Execution
- **Endpoint**: `POST /api/playwright/execute/<testcase_name>`
- **Description**: Execute a test case specifically using Playwright executor
- **Request Body**: 
  ```json
  {
    "suite_type": "smoke|sanity|regression",
    "project_name": "Optional project name",
    "module_name": "Optional module name"
  }
  ```

### 2. Selenium-Specific Execution
- **Endpoint**: `POST /api/selenium/execute/<testcase_name>`
- **Description**: Execute a test case specifically using Selenium executor
- **Request Body**: Same as Playwright endpoint

### 3. Available Executors
- **Endpoint**: `GET /api/executors/available`
- **Description**: Get list of available test executors and their capabilities
- **Response**:
  ```json
  {
    "success": true,
    "executors": [
      {
        "name": "selenium",
        "display_name": "Selenium WebDriver",
        "description": "Traditional Selenium WebDriver for cross-browser testing",
        "available": true,
        "browser_support": ["Chrome", "Firefox", "Edge", "Safari"],
        "features": ["Cross-browser", "Mature ecosystem", "Wide language support"]
      },
      {
        "name": "playwright",
        "display_name": "Playwright",
        "description": "Modern browser automation with faster execution and better reliability",
        "available": true,
        "browser_support": ["Chromium", "Firefox", "WebKit"],
        "features": ["Fast execution", "Auto-wait", "Network interception", "Mobile testing"]
      }
    ],
    "default_executor": "selenium"
  }
  ```

### 4. Test Executor Connection
- **Endpoint**: `POST /api/executors/test-connection`
- **Description**: Test connection to a specific executor
- **Request Body**:
  ```json
  {
    "executor_type": "selenium|playwright"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "executor_type": "playwright",
    "message": "Playwright executor connection successful",
    "browser_info": "Chromium browser launched and closed successfully"
  }
  ```

## Enhanced Existing Endpoints

### 1. Main Test Execution Endpoint
- **Endpoint**: `POST /api/execute/<testcase_name>`
- **Enhancement**: Now supports `executor_type` parameter to choose between Selenium and Playwright
- **Request Body**:
  ```json
  {
    "executor_type": "selenium|playwright",
    "suite_type": "smoke|sanity|regression",
    "suite_types": ["smoke", "sanity"],  // For multi-suite execution
    "project_name": "Optional project name",
    "module_name": "Optional module name"
  }
  ```

### 2. Test Suites
- **Enhancement**: TestSuites table now includes `executor_type` column with default 'selenium'
- **Supports**: Creating test suites with specific executor preferences

## Key Features

### 1. Executor Selection
- **Default**: Selenium (for backward compatibility)
- **Options**: 'selenium' or 'playwright'
- **Flexibility**: Can be specified per test execution or per test suite

### 2. Unified Results Storage
- Both Selenium and Playwright results are stored in the same `selenium_results` table
- `browser_info` field distinguishes between executors:
  - Selenium: "Chrome" or specific browser
  - Playwright: "Playwright/Chromium"

### 3. Allure Reporting
- Both executors generate Allure-compatible reports
- Results are stored in `allure-results-new` directory
- Same report generation endpoints work for both executors

## Usage Examples

### 1. Execute Test with Playwright
```bash
curl -X POST http://localhost:5000/api/execute/MyTestCase \
  -H "Content-Type: application/json" \
  -d '{"executor_type": "playwright", "suite_type": "smoke"}'
```

### 2. Force Playwright Execution
```bash
curl -X POST http://localhost:5000/api/playwright/execute/MyTestCase \
  -H "Content-Type: application/json" \
  -d '{"suite_type": "regression"}'
```

### 3. Check Available Executors
```bash
curl -X GET http://localhost:5000/api/executors/available
```

### 4. Test Playwright Connection
```bash
curl -X POST http://localhost:5000/api/executors/test-connection \
  -H "Content-Type: application/json" \
  -d '{"executor_type": "playwright"}'
```

## Frontend Integration

### 1. Executor Selection UI
The frontend can now include executor selection in test execution forms:
```javascript
// Get available executors
const executors = await fetch('/api/executors/available').then(r => r.json());

// Execute with selected executor
const result = await fetch(`/api/execute/${testcaseName}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    executor_type: selectedExecutor, // 'selenium' or 'playwright'
    suite_type: selectedSuite
  })
});
```

### 2. Test Suite Configuration
When creating test suites, include executor preference:
```javascript
const suiteData = {
  module_id: moduleId,
  suite_name: suiteName,
  suite_type: suiteType,
  description: description,
  executor_type: 'playwright' // or 'selenium'
};
```

## Playwright Executor Features

### 1. Enhanced Browser Support
- **Chromium**: Default browser for Playwright
- **Firefox**: Available for cross-browser testing
- **WebKit**: Safari engine for Mac compatibility

### 2. Improved Reliability
- **Auto-wait**: Automatically waits for elements to be ready
- **Network interception**: Can intercept and modify network requests
- **Mobile testing**: Built-in mobile device emulation

### 3. Better Performance
- **Faster execution**: Generally faster than Selenium
- **Parallel execution**: Better support for parallel test runs
- **Resource efficiency**: Lower resource consumption

## Migration Guide

### 1. Existing Test Cases
- All existing test cases work with both executors
- No changes needed to test steps or data
- Simply specify `executor_type` in execution requests

### 2. Test Suites
- Existing test suites default to Selenium
- Can be updated to use Playwright via the update endpoint
- New test suites can specify executor preference

### 3. Results and Reporting
- Results from both executors appear in the same dashboard
- Allure reports include results from both executors
- Historical data is preserved

## Troubleshooting

### 1. Playwright Installation
If Playwright is not available, install it:
```bash
pip install playwright
playwright install chromium
```

### 2. Connection Issues
Use the test connection endpoint to verify executor availability:
```bash
curl -X POST http://localhost:5000/api/executors/test-connection \
  -H "Content-Type: application/json" \
  -d '{"executor_type": "playwright"}'
```

### 3. Browser Launch Failures
- Ensure Playwright browsers are installed
- Check system permissions for browser execution
- Verify no conflicting browser processes

## Best Practices

### 1. Executor Selection
- **Use Selenium for**: Cross-browser compatibility testing, legacy system support
- **Use Playwright for**: Modern web applications, faster execution, better reliability

### 2. Test Design
- Design tests to be executor-agnostic
- Use standard XPath/CSS selectors that work with both
- Avoid executor-specific features in test steps

### 3. Performance
- Playwright generally executes faster
- Consider Playwright for large test suites
- Use Selenium for specific browser requirements

## Configuration

### 1. Default Executor
The default executor is Selenium for backward compatibility. To change:
```python
# In app.py, modify the default_executor in get_available_executors()
'default_executor': 'playwright'  # Change from 'selenium'
```

### 2. Executor Preferences
Test suites can have executor preferences stored in the database:
```sql
UPDATE TestSuites SET executor_type = 'playwright' WHERE id = <suite_id>;
```

## Testing the Integration

Run the test script to verify all endpoints:
```bash
cd new_backend
python test_playwright_endpoints.py
```

This will test:
- Health check
- Available executors endpoint
- Selenium connection test
- Playwright connection test

## Support

For issues with Playwright integration:
1. Check the Flask server logs for detailed error messages
2. Verify Playwright installation and browser setup
3. Test individual executor connections using the test endpoints
4. Ensure database connectivity for result storage
