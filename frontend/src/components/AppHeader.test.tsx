import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { AppHeader } from './AppHeader';

it('shows the supplied logo on a badge and the complete application title', () => {
  const html = renderToStaticMarkup(<AppHeader />);
  expect(html).toContain('class="app-header"');
  expect(html).toContain('class="app-header__badge"');
  expect(html).toContain('alt="Weather-Aware Truck Routing logo" height="40"');
  expect(html).toContain('<h1>Weather-Aware Truck Routing</h1>');
  expect(html).toContain('truck-logo.png');
});
