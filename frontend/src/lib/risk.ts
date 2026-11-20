// A TypeScript copy of backend/routing/risk.py, used to classify heatmap pixels in the browser.
// Keep the two in step: the boundaries are tested in risk.test.ts.

export type Hazard = 'wind' | 'gust' | 'rain' | 'snow';
export type WindMetric = 'sustained' | 'gust' | 'max';
export type Level = 0 | 1 | 2 | 3 | 4;

// Lowest value of Moderate, High and Severe, then the No Travel threshold and whether it is inclusive.
// A value equal to a lower bound belongs to the higher level. Wind No Travel is >= 55; rain and snow are strictly above.
type Table = readonly [number, number, number, number, boolean];
const TABLES: Record<Hazard, Table> = {
  wind: [25, 35, 45, 55, true],
  gust: [40, 50, 60, 70, true], // display scale for the Gust layer only; risk never classifies gusts with it
  rain: [0.1, 0.25, 0.5, 1, false],
  snow: [0.5, 1, 2, 3, false],
};

export function levelFor(hazard: Hazard, value: number | null | undefined): Level | null {
  if (value == null) return null;
  const [moderate, high, severe, noTravel, inclusive] = TABLES[hazard];
  if (inclusive ? value >= noTravel : value > noTravel) return 4;
  if (value >= severe) return 3;
  if (value >= high) return 2;
  if (value >= moderate) return 1;
  return 0;
}

function windSpeed(wind: number | null, gust: number | null, metric: WindMetric): number | null {
  if (metric === 'gust') return gust ?? wind;
  if (metric === 'max') return wind == null ? gust : gust == null ? wind : Math.max(wind, gust);
  return wind;
}

// The risk level for one place and hour, with the load rules applied to wind. Null when there is no data at all.
export function classifyPixel(
  wind: number | null, gust: number | null, rain: number | null, snow: number | null,
  loadLb: number, metric: WindMetric = 'sustained',
): Level | null {
  const speed = windSpeed(wind, gust, metric);
  if (speed == null && rain == null && snow == null) return null;
  let windLevel: number = levelFor('wind', speed) ?? 0;
  if (windLevel === 3 && loadLb > 30000) windLevel = 4;
  else if (windLevel === 2 && loadLb > 40000) windLevel = 3;
  return Math.max(windLevel, levelFor('rain', rain) ?? 0, levelFor('snow', snow) ?? 0) as Level;
}
