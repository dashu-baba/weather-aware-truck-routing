// Forecast-hour strings in real responses omit Z; they still represent UTC.
export function parseUtc(value: string): Date {
  return new Date(/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`);
}

export function localTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(parseUtc(value));
}

export function utcTime(value: string): string {
  return `${parseUtc(value).toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export function duration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`;
}

export function miles(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
