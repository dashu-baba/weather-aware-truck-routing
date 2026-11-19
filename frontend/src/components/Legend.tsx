import { HEAT_LAYERS, type HeatLayer } from '../map/heatfield';
import { RISK_COLORS } from '../map/palette';

export function Legend({ layer }: { layer: HeatLayer }) {
  const { title, labels } = HEAT_LAYERS[layer];
  return (
    <div className="heat-legend" role="group" aria-label="Map legend">
      <strong>{title}</strong>
      {labels.map((label, level) => (
        <div className="heat-legend__row" key={label}>
          <span className="heat-legend__swatch" style={{ background: RISK_COLORS[level] }} aria-hidden="true" />
          {label}
        </div>
      ))}
      <p>Background: weather at the slider hour. Lines and dots: risk at each checkpoint's ETA.</p>
    </div>
  );
}
