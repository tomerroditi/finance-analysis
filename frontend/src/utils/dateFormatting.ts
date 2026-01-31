import { format } from "date-fns";

/**
 * Standard date format used across the application: dd/MM/yyyy
 * Example: 30/01/2026
 */
export const DATE_FORMAT = "dd/MM/yyyy";

/**
 * Format a date string or Date object to the standard display format (dd/MM/yyyy)
 * @param date - Date string (ISO format) or Date object
 * @returns Formatted date string in dd/MM/yyyy format
 */
export function formatDate(date: string | Date): string {
  const dateObj = typeof date === "string" ? new Date(date) : date;
  return format(dateObj, DATE_FORMAT);
}

/**
 * Format a date for display with short month name (e.g., "30 Jan")
 * @param date - Date string (ISO format) or Date object
 * @returns Formatted date string
 */
export function formatShortDate(date: string | Date): string {
  const dateObj = typeof date === "string" ? new Date(date) : date;
  return format(dateObj, "d MMM");
}
