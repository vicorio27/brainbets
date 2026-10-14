// Prediction status as shown to the user. The API keeps the codes.
const LABELS = {
  PENDING: 'Pendiente',
  LOW_CONFIDENCE: 'Baja confianza',
  VALIDATED: 'Acertada',
  FAILED: 'Fallida',
  CANCELLED: 'Anulada'
}

export function statusLabel(status) {
  return LABELS[status] || status || '–'
}
