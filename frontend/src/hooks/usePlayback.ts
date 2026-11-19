import { useCallback, useEffect, useReducer, useRef } from 'react';
import { initialPlaybackState, playbackReducer, type Timeline } from './playbackReducer';

export function usePlayback(timeline: Timeline | null) {
  const [state, dispatch] = useReducer(playbackReducer, initialPlaybackState);
  const frame = useRef<number | null>(null);
  const pendingHour = useRef(0);
  // A replacement heatmap is a new clock: no old hour or Play state leaks into it.
  const current = state.timeline === timeline;
  const hour = current ? state.hour : 0;
  const playing = current && state.playing;

  useEffect(() => {
    if (!playing || !timeline) return;
    const timer = setTimeout(() => {
      dispatch({ type: 'tick', timeline });
    }, 600);
    return () => clearTimeout(timer);
  }, [playing, hour, timeline]);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
  }, [timeline]);

  const pause = useCallback(() => {
    dispatch({ type: 'pause', timeline });
  }, [timeline]);

  const seek = useCallback((value: number) => {
    pause();
    pendingHour.current = value;
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      dispatch({ type: 'seek', timeline, hour: pendingHour.current });
    });
  }, [pause, timeline]);

  const toggle = useCallback(() => {
    // Preserve a last slider input if Play is clicked before its animation frame.
    if (frame.current !== null) {
      cancelAnimationFrame(frame.current);
      frame.current = null;
      dispatch({ type: 'seek', timeline, hour: pendingHour.current });
    }
    dispatch({ type: 'toggle', timeline });
  }, [timeline]);

  return { hour, playing, pause, seek, toggle };
}
