import { describe, expect, it } from 'vitest';
import { initialPlaybackState, playbackReducer } from './playbackReducer';

const timeline = { hours: 48 };
const started = () => playbackReducer(initialPlaybackState, { type: 'toggle', timeline });

describe('playback clock', () => {
  it('plays, advances one hour per tick, pauses and resumes from the same hour', () => {
    let state = started();
    expect(state).toMatchObject({ hour: 0, playing: true });
    state = playbackReducer(state, { type: 'tick', timeline });
    expect(state.hour).toBe(1);
    state = playbackReducer(state, { type: 'pause', timeline });
    expect(state.playing).toBe(false);
    expect(playbackReducer(state, { type: 'pause', timeline })).toBe(state);
    expect(playbackReducer(state, { type: 'tick', timeline })).toBe(state);
    state = playbackReducer(state, { type: 'toggle', timeline });
    expect(playbackReducer(state, { type: 'tick', timeline }).hour).toBe(2);
  });

  it('loops from the last forecast hour back to zero', () => {
    expect(playbackReducer({ ...started(), hour: 47 }, { type: 'tick', timeline }).hour).toBe(0);
  });

  it('pauses on a seek and clamps or rounds the chosen hour', () => {
    expect(playbackReducer(started(), { type: 'seek', timeline, hour: 14 })).toMatchObject({ hour: 14, playing: false });
    expect(playbackReducer(started(), { type: 'seek', timeline, hour: 100 }).hour).toBe(47);
    expect(playbackReducer(started(), { type: 'seek', timeline, hour: -1 }).hour).toBe(0);
    expect(playbackReducer(started(), { type: 'seek', timeline, hour: 3.6 }).hour).toBe(4);
    expect(playbackReducer(started(), { type: 'seek', timeline, hour: NaN }).hour).toBe(0);
  });

  it('resets old playback state when the heatmap is replaced', () => {
    const replacement = { hours: 24 };
    expect(playbackReducer({ ...started(), hour: 20 }, { type: 'pause', timeline: replacement }))
      .toEqual({ timeline: replacement, hour: 0, playing: false });
    expect(playbackReducer(started(), { type: 'toggle', timeline: null })).toMatchObject({ hour: 0, playing: false });
  });

  it.each([0, 1])('does not play a %i-hour timeline', hours => {
    expect(playbackReducer(initialPlaybackState, { type: 'toggle', timeline: { hours } }).playing).toBe(false);
  });
});
