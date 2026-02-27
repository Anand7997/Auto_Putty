import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

// Updated: 2024-12-19 - Fixed microseconds date parsing issue

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formats a date string or Date object for display
 * @param dateValue - The date value to format (string, Date, or null/undefined)
 * @param options - Formatting options
 * @returns Formatted date string or fallback message
 */
export function formatExecutionDate(
  dateValue: string | Date | null | undefined,
  options: {
    fallback?: string;
    includeTime?: boolean;
    locale?: string;
  } = {}
): string {
  const {
    fallback = 'No Date Available',
    includeTime = true,
    locale = 'en-US'
  } = options;

  // Handle null/undefined values
  if (!dateValue) {
    return fallback;
  }

  try {
    let dateToFormat = dateValue;
    
    // Handle microseconds in ISO string format (e.g., "2025-08-01T14:23:12.830000")
    // JavaScript Date constructor can handle microseconds, but for consistency we truncate to milliseconds
    if (typeof dateValue === 'string' && dateValue.includes('.')) {
      const parts = dateValue.split('.');
      if (parts.length === 2 && parts[1].length > 3) {
        // Keep only first 3 digits after decimal (milliseconds) and preserve timezone if present
        const fractionalPart = parts[1];
        const hasTimezone = fractionalPart.includes('Z') || fractionalPart.includes('+') || fractionalPart.includes('-');
        if (hasTimezone) {
          const timezoneMatch = fractionalPart.match(/[Z+\-].*/);
          const timezone = timezoneMatch ? timezoneMatch[0] : '';
          dateToFormat = parts[0] + '.' + fractionalPart.substring(0, 3) + timezone;
        } else {
          dateToFormat = parts[0] + '.' + fractionalPart.substring(0, 3);
        }
      }
    }
    
    const date = new Date(dateToFormat);
    
    // Check if the date is valid
    if (isNaN(date.getTime())) {
      console.warn('❌ Invalid date detected:', dateValue, 'Processed as:', dateToFormat);
      return 'Invalid Date';
    }

    const dateStr = date.toLocaleDateString(locale);
    
    if (includeTime) {
      const timeStr = date.toLocaleTimeString(locale);
      return `${dateStr} ${timeStr}`;
    }
    
    return dateStr;
  } catch (error) {
    console.error('❌ Error formatting date:', error, 'Input:', dateValue);
    return 'Invalid Date';
  }
}
