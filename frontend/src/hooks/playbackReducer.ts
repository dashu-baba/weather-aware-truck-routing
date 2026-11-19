export type Timeline = { hours: number };
export type PlaybackState = { timeline: Timeline | null; hour: number; playing: boolean };
export const initialPlaybackState: PlaybackState = { timeline: null, hour: 0, playing: false };
export type PlaybackAction =
  | { type: 'toggle' | 'pause' | 'tick'; timeline: Timeline | null }
  | { type: 'seek'; timeline: Timeline | null; hour: number };

export function playbackReducer(state: PlaybackState, action: PlaybackAction): PlaybackState {
  const current = state.timeline === action.timeline
    ? state
    : { timeline: action.timeline, hour: 0, playing: false };
  const hours = action.timeline?.hours ?? 0;
  if (hours < 1) return { ...current, hour: 0, playing: false };
  switch (action.type) {
    case 'toggle': return { ...current, playing: hours > 1 && !current.playing };
    case 'pause': return current.playing ? { ...current, playing: false } : current;
    case 'tick': return current.playing ? { ...current, hour: (current.hour + 1) % hours } : current;
    case 'seek': return {
      ...current,
      hour: Math.min(hours - 1, Math.max(0, Number.isFinite(action.hour) ? Math.round(action.hour) : 0)),
      playing: false,
    };
  }
}
