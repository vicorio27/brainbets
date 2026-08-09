/**
 * Formatting utilities for dates, times, and numbers.
 */

function isPlaceholderTime(timeStr) {
  if (!timeStr) return true
  const trimmed = timeStr.trim()
  return trimmed === '' || trimmed === '00:00' || trimmed === '00:00:00'
}

export function formatDateTime(dateStr, timeStr) {
  if (!dateStr) return 'N/A'
  let text = formatDate(dateStr)
  if (timeStr && !isPlaceholderTime(timeStr)) {
    text += ` · ${formatTime(timeStr)}`
  }
  return text
}

export function formatDate(dateStr) {
  if (!dateStr) return 'N/A'
  const date = new Date(`${dateStr}T00:00:00Z`)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleDateString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'UTC'
  })
}

export function formatTime(timeStr) {
  if (!timeStr) return ''
  // If timeStr already looks like HH:MM or HH:MM:SS, return HH:MM.
  const parts = timeStr.split(':')
  if (parts.length >= 2) {
    return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}`
  }
  return timeStr
}

export function formatDateTimeIso(isoStr) {
  if (!isoStr) return 'N/A'
  const date = new Date(isoStr)
  if (isNaN(date.getTime())) return isoStr
  return date.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC'
  })
}
