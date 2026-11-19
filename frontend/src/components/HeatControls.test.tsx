import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Legend } from './Legend';
import { TimeBar, hourLabel } from './TimeBar';

const START = '2026-11-20T08:00:00Z';
const noop = () => undefined;
const bar = (props: Partial<Parameters<typeof TimeBar>[0]> = {}) => renderToStaticMarkup(
  <TimeBar start={START} hours={48} hour={14} layer="wind" disabled={false} note="Loading weather map…" playing={false} onTogglePlay={noop} onPause={noop} onHour={noop} onLayer={noop} {...props} />,
);

describe('hourLabel', () => {
  it('shows the offset, the local time and the UTC time of the forecast hour', () => {
    const label = hourLabel(START, 14);
    expect(label).toMatch(/^\+14h · /);
    expect(label).toContain('(22:00 UTC)'); // 08:00Z plus 14 hours
  });
  it('treats hour 0 as the first forecast hour', () => {
    expect(hourLabel(START, 0)).toContain('(08:00 UTC)');
  });
});

describe('TimeBar', () => {
  it('shows an accessible Play/Pause button and disables playback for a single hour', () => {
    expect(bar()).toContain('aria-label="Play forecast"');
    expect(bar({ playing: true })).toContain('aria-label="Pause playback" aria-pressed="true"');
    expect(bar({ hours: 1 })).toContain('disabled="" aria-label="Play forecast"');
  });

  it('has a slider for hours 0 to 47 and shows the label of the chosen hour', () => {
    const html = bar();
    expect(html).toContain('type="range"');
    expect(html).toContain('min="0"');
    expect(html).toContain('max="47"');
    expect(html).toContain('value="14"');
    expect(html).toContain('+14h');
    expect(html).not.toContain('disabled=""');
  });

  it('marks only the chosen layer as pressed', () => {
    const html = bar({ layer: 'rain' });
    for (const name of ['Risk', 'Wind', 'Gust', 'Rain', 'Snow']) expect(html).toContain(`>${name}</button>`);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-pressed="true"[^>]*>Rain</);
  });

  it('is disabled with a note until the heatmap is loaded', () => {
    const html = bar({ disabled: true, start: null });
    expect(html).toContain('Loading weather map…');
    expect(html).not.toContain('+14h');
    expect((html.match(/disabled=""/g) ?? []).length).toBe(7); // Play, the slider and five layer buttons
  });
});

describe('Legend', () => {
  it('shows the title, five levels and the note for the layer', () => {
    const html = renderToStaticMarkup(<Legend layer="rain" />);
    expect(html).toContain('Rain (in/hr)');
    for (const label of ['&lt;0.10', '0.10–&lt;0.25', '0.25–&lt;0.50', '0.50–1.00', '&gt;1.00']) expect(html).toContain(label);
    expect(html).toContain('Lines and dots');
  });

  it('uses the level names for the risk layer', () => {
    const html = renderToStaticMarkup(<Legend layer="risk" />);
    for (const name of ['Low', 'Moderate', 'High', 'Severe', 'No Travel']) expect(html).toContain(name);
  });
});
