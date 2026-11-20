import { HEAT_LAYERS, legendColor, type HeatLayer } from '../map/heatfield';

export function Legend({ layer }: { layer: HeatLayer }) {
  const { title, labels } = HEAT_LAYERS[layer];
  return (
    <div className="heat-legend" role="group" aria-label="Map legend">
      <strong>{title}</strong>
      {labels.map((label, level) => (
        <div className="heat-legend__row" key={label}>
          <span className="heat-legend__swatch" style={{ background: legendColor(layer, level) }} aria-hidden="true" />
          {label}
        </div>
      ))}
      {(layer === 'wind' || layer === 'gust') && <p>Moving lines: sustained wind direction; bolder and faster lines, stronger wind.</p>}
      <p>Background: weather at the slider hour. Lines and dots: risk at each checkpoint's ETA.</p>
    </div>
  );
}
