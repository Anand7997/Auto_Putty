# Web Automation Healer

The Web Automation Healer is a comprehensive healing module designed to make Selenium and Playwright-based web automation tests more robust and resilient to common web application issues.

## Overview

The healer implements 6 different healing mechanisms and supports **both Selenium WebDriver and Playwright** frameworks:

### Healing Mechanisms:
1. **Stale Element Reference Healer** - Automatically re-locates elements when they become stale
2. **Element Obscured Healer** - Handles elements obscured by overlays, popups, or other elements
3. **Dynamic Wait Healer** - Implements intelligent polling for dynamic content
4. **Navigation and Page Load Healer** - Handles navigation timeouts and retries
5. **Selector Fallback Healer** - Provides fallback selectors when primary selectors fail
6. **Iframe Healer** - Automatically handles iframe context switching

### Framework Support:
- **Selenium WebDriver**: Full support with WebElement-based operations
- **Playwright**: Full support with Locator-based operations
- **Unified API**: Same healing methods work across both frameworks

## Key Features

- **Framework Agnostic**: Works with both Selenium WebDriver and Playwright
- **Non-Invasive Integration**: Can be integrated without modifying existing executor code
- **Configurable**: Healing can be enabled/disabled, retry counts customized
- **Comprehensive**: Covers the most common causes of web automation test failures
- **Logging**: Detailed logging for debugging and monitoring

## Installation

The healer is included in the `new_backend` directory. No additional installation required.

## Basic Usage

### Selenium Integration

```python
from healer import SeleniumHealer

# After launching browser in your executor
healer = SeleniumHealer(driver=executor.driver)

# Use healed methods instead of direct driver calls
element = healer.find_element_with_healing(By.XPATH, "//button[@id='submit']")
healer.click_with_healing(element=element)
```

### Playwright Integration

```python
from healer import PlaywrightHealer

# After launching browser in your executor
healer = PlaywrightHealer(page=executor.page)

# Use healed methods instead of direct page calls
locator = healer.find_locator_with_healing("xpath=//button[@id='submit']")
healer.click_with_healing(locator=locator)
```

## Integration Patterns

### Pattern 1: Direct Method Replacement

Replace executor methods with healed versions:

```python
# In your executor initialization
self.healer = SeleniumHealer(self.driver)

# Replace methods
original_find_element = self.find_element_with_advanced_wait
self.find_element_with_advanced_wait = lambda xpath: self.healer.find_element_with_healing(By.XPATH, xpath)
```

### Pattern 2: Wrapper Functions

Create wrapper functions that use the healer:

```python
def healed_click(self, xpath, element_name):
    if not hasattr(self, 'healer'):
        self.healer = SeleniumHealer(self.driver)

    element = self.healer.find_element_with_healing(By.XPATH, xpath)
    self.healer.click_with_healing(element=element)

# Use in executor
healed_click(self, xpath, element_name)
```

### Pattern 3: Decorator Pattern

Use the `@with_healing` decorator:

```python
from healer import with_healing

healer = SeleniumHealer(driver)

@with_healing(healer)
def click_element(driver, xpath):
    element = driver.find_element(By.XPATH, xpath)
    element.click()

# The decorator automatically adds healing
click_element(driver, xpath)
```

### Pattern 4: Inheritance Pattern

Create a healed version of your executor:

```python
class HealedSeleniumExecutor(SeleniumTestExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.healer = None

    def launch_browser(self):
        result = super().launch_browser()
        if result:
            self.healer = SeleniumHealer(self.driver)
        return result

    def execute_action_with_isolation(self, action_type, test_data, xpath, element_name):
        # Use healer for element finding
        if self.healer:
            try:
                element = self.healer.find_element_with_healing(By.XPATH, xpath)
                # Continue with healed element...
            except Exception as e:
                logger.warning(f"Healing failed, falling back to original method: {e}")
                # Fallback to original method
                element = self.find_element_with_advanced_wait(xpath)
        else:
            # Original implementation
            element = self.find_element_with_advanced_wait(xpath)
```

## Healing Mechanisms Explained

### 1. Stale Element Reference Healer

**Problem**: Elements become stale when the page structure changes after location but before action.

**Solution**: Automatically re-locates the element using the original selector when a `StaleElementReferenceException` occurs.

```python
# Automatic healing
element = healer.find_element_with_healing(By.XPATH, "//button")
# If element becomes stale during click, it will be re-located automatically
healer.click_with_healing(element=element)
```

### 2. Element Obscured Healer

**Problem**: Elements cannot be clicked because they're covered by overlays, popups, or other elements.

**Solution**: Attempts multiple strategies:
- Press Escape to dismiss dialogs
- Search for and click common close buttons
- Use JavaScript click as fallback

```python
# Automatic healing for obscured elements
healer.click_with_healing(selector="//button[@id='submit']")
```

### 3. Dynamic Wait Healer

**Problem**: Elements appear after delays or dynamic content loading.

**Solution**: Implements retry logic with exponential backoff for all element operations.

```python
# Configurable retry attempts
healer = SeleniumHealer(driver, max_retries=5)
element = healer.find_element_with_healing(By.XPATH, "//dynamic-element")
```

### 4. Navigation and Page Load Healer

**Problem**: Page navigation fails due to network issues or slow loading.

**Solution**: Wraps navigation commands with retry logic and page load verification.

```python
# Automatic retry on navigation failure
success = healer.navigate_with_healing("https://example.com")
```

### 5. Selector Fallback Healer

**Problem**: Primary selectors become invalid due to UI changes.

**Solution**: Automatically tries fallback selectors when primary selector fails.

```python
# Automatic fallback selector usage
element = healer.heal_with_fallback_selectors("//*[@id='submit-button']")
# Will try: //*[@name='submit-button'], //*[contains(@class, 'submit-button')], etc.
```

### 6. Iframe Healer

**Problem**: Elements are inside iframes but tests don't switch context.

**Solution**: Automatically scans iframes when element is not found in main context.

```python
# Automatic iframe context switching
element = healer.find_element_with_healing(By.XPATH, "//input[@id='iframe-input']")
```

## Configuration Options

```python
# Create healer with custom settings
healer = SeleniumHealer(
    driver=driver,
    max_retries=3,        # Number of healing attempts
    healing_enabled=True  # Enable/disable all healing
)
```

## Logging

The healer provides detailed logging for debugging:

```
INFO: Healing attempt 1 for selector: //button[@id='submit']
WARNING: Stale element detected, re-locating: //button[@id='submit']
INFO: Element found in iframe: //button[@id='submit']
```

## Testing

Run the integration test to verify healer functionality:

```bash
cd new_backend
python test_healer_integration.py
```

## Best Practices

1. **Enable healing selectively**: Use healing for problematic areas rather than all operations
2. **Monitor healing usage**: Check logs to identify patterns of failures
3. **Test with healing disabled**: Ensure your tests work without healing as baseline
4. **Use appropriate timeouts**: Balance between reliability and test execution time
5. **Handle healing failures**: Have fallback strategies when healing cannot resolve issues

## Troubleshooting

### Common Issues

1. **Healing taking too long**: Reduce `max_retries` or increase timeouts
2. **False positive healing**: Some exceptions might not need healing - check logs
3. **Iframe healing not working**: Ensure iframes are fully loaded before element search

### Debug Mode

Enable debug logging to see detailed healing operations:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Examples

See `test_healer_integration.py` for comprehensive examples of healer integration patterns.

## Contributing

When adding new healing mechanisms:

1. Implement the healing logic in the appropriate method
2. Add the mechanism to `_apply_element_healing` or `_apply_locator_healing`
3. Update tests and documentation
4. Ensure backward compatibility

## License

This healer module is part of the automation testing framework and follows the same license terms.