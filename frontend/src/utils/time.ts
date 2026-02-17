/**
 * Time related utility functions
 */

/**
 * Convert ISO 8601 datetime string to timestamp number
 * @param isoString ISO 8601 datetime string (e.g., "2025-06-22T04:42:11.842000")
 * @returns Timestamp number in seconds
 */
export const parseISODateTime = (isoString: string): number => {
  try {
    const date = new Date(isoString);

    if (isNaN(date.getTime())) {
      throw new Error('Invalid ISO datetime string');
    }

    return Math.floor(date.getTime() / 1000);
  } catch {
    throw new Error(`Failed to parse ISO datetime string: ${isoString}`);
  }
};

/**
 * Pure function: convert a Unix-seconds timestamp to a compact relative time label.
 * No Vue composable dependencies — safe to call anywhere.
 *
 * @param timestamp Unix timestamp in **seconds**
 */
export const formatRelativeTime = (timestamp: number): string => {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 'Just now';

  const now = Math.floor(Date.now() / 1000);
  const diffSec = now - timestamp;

  if (!Number.isFinite(diffSec) || diffSec < 0) return 'Just now';
  if (diffSec < 60) return 'Just now';

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return diffMin === 1 ? '1m ago' : `${diffMin}m ago`;

  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return diffHour === 1 ? '1h ago' : `${diffHour}h ago`;

  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return diffDay === 1 ? '1d ago' : `${diffDay}d ago`;

  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return diffMonth === 1 ? '1mo ago' : `${diffMonth}mo ago`;

  const diffYear = Math.floor(diffMonth / 12);
  return diffYear === 1 ? '1y ago' : `${diffYear}y ago`;
};

/**
 * Format timestamp according to custom requirements:
 * - Today: show time (HH:MM)
 * - This week: show day of week (e.g., Mon)
 * - This year: show date (MM/DD)
 * - Other years: show year/month (YYYY/MM)
 * @param timestamp Timestamp (seconds)
 * @param t Translation function from i18n
 * @param locale Current locale (for date formatting)
 * @returns Formatted time string
 */
export const formatCustomTime = (timestamp: number, t?: (key: string) => string, locale?: string): string => {
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return t ? t('Just now') : 'Just now';
  }

  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) {
    return t ? t('Just now') : 'Just now';
  }

  const now = new Date();
  
  // Check if it's today
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) {
    // Use locale-appropriate time format
    const timeFormat = locale?.startsWith('zh') ? 'zh-CN' : 'en-US';
    return date.toLocaleTimeString(timeFormat, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  }
  
  // Check if it's this week
  const startOfWeek = new Date(now);
  startOfWeek.setDate(now.getDate() - now.getDay() + 1); // Monday as start of week
  startOfWeek.setHours(0, 0, 0, 0);
  
  const endOfWeek = new Date(startOfWeek);
  endOfWeek.setDate(startOfWeek.getDate() + 6);
  endOfWeek.setHours(23, 59, 59, 999);
  
  if (date >= startOfWeek && date <= endOfWeek) {
    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    if (t) {
      return t(weekdays[date.getDay()]);
    } else {
      return weekdays[date.getDay()];
    }
  }
  
  // Check if it's this year
  const isThisYear = date.getFullYear() === now.getFullYear();
  if (isThisYear) {
    // Use locale-appropriate date format
    if (locale?.startsWith('zh')) {
      return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`;
    } else {
      // For English and other locales, use MM/DD format
      return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`;
    }
  }
  
  // Other years: show year/month
  return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, '0')}`;
}; 
