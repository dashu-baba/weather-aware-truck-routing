import { afterEach, expect, it, vi } from 'vitest';
import { BASEMAP_URL, blankStyle, loadBasemap } from './basemap';

afterEach(() => vi.unstubAllGlobals());

it('loads the OpenFreeMap style with a cancellable request', async () => {
  const style = { version: 8, sources: { basemap: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' } }, layers: [] };
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(style)));
  vi.stubGlobal('fetch', fetch);
  const controller = new AbortController();
  expect(await loadBasemap(controller.signal)).toEqual(style);
  expect(fetch).toHaveBeenCalledWith(BASEMAP_URL, { signal: expect.any(AbortSignal) });
  controller.abort();
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
});

it.each([new Response('', { status: 503 }), new Error('Offline')])('falls back to a blank style when unreachable (%s)', async response => {
  vi.stubGlobal('fetch', response instanceof Error
    ? vi.fn().mockRejectedValue(response)
    : vi.fn().mockResolvedValue(response));
  expect(await loadBasemap(new AbortController().signal)).toEqual(blankStyle());
});
