import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { PlaceInput } from './PlaceInput';
import { TripForm } from './TripForm';
import { initialTripPlaces } from '../hooks/tripPlacesReducer';
const WARNING = 'Check this location';

it('shows the picked label, pressed picker and a warning associated with the input', () => {
  const html = renderToStaticMarkup(<PlaceInput label="Origin" value={{ label: 'Picked address', lat: 50, lon: -100 }}
    onChange={() => {}} picking={true} onPick={() => {}} warning={WARNING} />);
  expect(html).toContain('value="Picked address"');
  expect(html).toContain('aria-label="Pick origin on map" aria-pressed="true"');
  expect(html).toContain('aria-describedby=');
  expect(html).toContain(WARNING);
  expect(html).toContain('Clear origin');
  expect(html).toContain('stroke="currentColor"');
});

it('allows coordinate-only places to be submitted without waiting for naming', () => {
  const html = renderToStaticMarkup(<TripForm busy={false} hasPlan={true} onSubmit={() => {}}
    places={{
      origin: { place: { label: '0.0000, 0.0000', lat: 0, lon: 0 }, warning: WARNING },
      destination: { place: { label: 'Dallas', lat: 32, lon: -96 }, warning: null },
    }} pickTarget={null} onPlaceChange={() => {}} onPick={() => {}} onSwap={() => {}} />);
  expect(html).toContain('Re-plan');
  expect(html).not.toContain('disabled=""');
  expect(renderToStaticMarkup(<TripForm busy={false} hasPlan={false} onSubmit={() => {}}
    places={initialTripPlaces} pickTarget={null} onPlaceChange={() => {}} onPick={() => {}} onSwap={() => {}} />)).toContain('disabled=""');
});
