import { localTime, parseUtc } from '../lib/format';
import { HEAT_LAYER_KEYS, type HeatLayer } from '../map/heatfield';

type Props = {
  start: string | null; // the UTC time of forecast hour 0
  hours: number;
  hour: number;
  layer: HeatLayer;
  disabled: boolean;
  note: string; // shown in place of the time while the heatmap is not ready
  playing: boolean;
  onTogglePlay: () => void;
  onPause: () => void;
  onHour: (hour: number) => void;
  onLayer: (layer: HeatLayer) => void;
};

// "+14h · Fri, Nov 20, 10:00 PM (22:00 UTC)": hour 0 is the heatmap's start, not the departure.
export function hourLabel(start: string, hour: number): string {
  const at = new Date(parseUtc(start).getTime() + hour * 3_600_000).toISOString();
  return `+${hour}h · ${localTime(at)} (${at.slice(11, 16)} UTC)`;
}

export function TimeBar({ start, hours, hour, layer, disabled, note, playing, onTogglePlay, onPause, onHour, onLayer }: Props) {
  const label = start && !disabled ? hourLabel(start, hour) : note;
  return (
    <div className="time-bar" role="group" aria-label="Forecast time and map layer">
      <div className="time-bar__row">
        <button type="button" className="time-bar__play" disabled={disabled || hours < 2}
          aria-label={playing ? 'Pause playback' : 'Play forecast'} aria-pressed={playing} onClick={onTogglePlay}>
          <span aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</span>
        </button>
        <input className="time-bar__slider" type="range" min={0} max={Math.max(0, hours - 1)} step={1} value={hour}
          disabled={disabled} aria-label="Forecast hour" aria-valuetext={label}
          onPointerDown={onPause} onKeyDown={event => {
            if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) onPause();
          }}
          onChange={event => onHour(Number(event.target.value))} />
        <span className="time-bar__label">{label}</span>
      </div>
      <div className="time-bar__layers" role="group" aria-label="Map layer">
        {HEAT_LAYER_KEYS.map(key => (
          <button key={key} type="button" aria-pressed={key === layer} disabled={disabled} onClick={() => onLayer(key)}>
            {key[0].toUpperCase() + key.slice(1)}
          </button>
        ))}
      </div>
    </div>
  );
}
