import type { Checkpoint } from '../api/types';
import { localTime, utcTime } from '../lib/format';
import { LEVELS, RISK_COLORS } from './palette';

// Use textContent for every API string, including reasons and route names.
export function checkpointPopup(routeLabel: string, checkpoint: Checkpoint): HTMLElement {
  const root = document.createElement('div');
  root.className = 'checkpoint-popup';
  const heading = document.createElement('h3');
  heading.textContent = `${routeLabel} · mile ${checkpoint.mile.toFixed(0)}`;
  root.append(heading);

  const line = (text: string) => {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    root.append(paragraph);
  };
  line(`ETA ${localTime(checkpoint.eta)}`);
  const weather = checkpoint.weather;
  if (weather) {
    line(`Wind ${weather.wind_mph.toFixed(1)} mph (gust ${weather.gust_mph.toFixed(1)} mph)`);
    line(`Rain ${weather.rain_in.toFixed(3)} in/hr · Snow ${weather.snow_in.toFixed(3)} in/hr`);
    line(`Forecast hour ${utcTime(weather.time)}`);
  } else {
    line('No forecast for this hour.');
  }

  const level = document.createElement('strong');
  level.style.color = RISK_COLORS[checkpoint.risk];
  level.textContent = LEVELS[checkpoint.risk];
  root.append(level);
  if (checkpoint.reasons.length) {
    const list = document.createElement('ul');
    checkpoint.reasons.forEach(reason => {
      const item = document.createElement('li');
      item.textContent = reason;
      list.append(item);
    });
    root.append(list);
  }
  return root;
}
