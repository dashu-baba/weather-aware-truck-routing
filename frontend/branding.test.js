import { readFileSync } from 'node:fs';
import { URL } from 'node:url';
import { describe, expect, it } from 'vitest';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const css = read('./src/styles.css');
const loader = read('./src/assets/truck-loader.svg');

describe('section 15 visual contracts', () => {
  it('uses the supplied PNG for the header and favicon and sets the page title', () => {
    const logo = readFileSync(new URL('./src/assets/truck-logo.png', import.meta.url));
    expect(logo.equals(readFileSync(new URL('./public/favicon.png', import.meta.url)))).toBe(true);
    const html = read('./index.html');
    expect(html).toContain('<link rel="icon" type="image/png" href="/favicon.png"');
    expect(html).toContain('<title>Weather-Aware Truck Routing</title>');
  });

  it('reserves brand accent tokens for declarations and the header, with no accent-coloured interaction styles', () => {
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
    for (const [, selector, declarations] of rules) {
      if (/c81513|fa9c05|--brand-red|--brand-amber/i.test(declarations)) {
        expect([':root', '.app-header']).toContain(selector.trim());
      }
    }
    expect(css).toContain('border-bottom: 3px solid var(--brand-red)');
    expect(css).toContain('height:calc(100dvh - 59px)');
    expect(css).toContain('outline: 2px solid var(--focus)');
  });

  it('keeps all fixed risk and route palette values unchanged', () => {
    const palette = read('./src/map/palette.ts');
    for (const hex of ['#2e7d32', '#f2b705', '#ef6c00', '#c62828', '#6a1b9a', '#1f5eff', '#0f9d8a', '#b04fd1']) {
      expect(palette).toContain(hex);
      expect(css).toContain(hex);
    }
  });

  it('keeps reduced-motion rules in the self-contained SVG and adds no wrapper animation', () => {
    expect(loader).toContain('@media (prefers-reduced-motion: reduce)');
    expect(loader).toContain('animation: none !important');
    expect(loader).toContain('.fx, .puff, .speed, .sweep { display: none; }');
    expect(loader).not.toMatch(/(?:href|src)=["']https?:/);
    expect(css.match(/\.truck-loader\s*\{([^}]+)\}/)?.[1]).not.toContain('animation');
  });
});

it('meets AA contrast for primary buttons, body text and muted labels', () => {
  const luminance = name => {
    const hex = css.match(new RegExp(`--${name}:\\s*(#[a-f0-9]{6})`, 'i'))[1];
    const rgb = [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255)
      .map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  for (const [foreground, background] of [['brand-navy', 'surface'], ['brand-navy-700', 'surface'], ['text', 'bg'], ['muted', 'surface'], ['muted', 'bg']]) {
    const a = luminance(foreground), b = luminance(background);
    expect((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toBeGreaterThanOrEqual(4.5);
  }
});
