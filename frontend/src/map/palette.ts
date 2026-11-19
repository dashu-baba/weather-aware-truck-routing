export const ROUTE_COLORS: Record<string, string> = {
  A: '#1f5eff', B: '#0f9d8a', C: '#b04fd1',
};
export const RISK_COLORS = ['#2e7d32', '#f2b705', '#ef6c00', '#c62828', '#6a1b9a'] as const;
export const LEVELS = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'] as const;

export function routeColor(id: string): string {
  return ROUTE_COLORS[id] ?? '#888';
}
