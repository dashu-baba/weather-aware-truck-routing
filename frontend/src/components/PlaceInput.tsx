import { useEffect, useId, useState } from 'react';
import { geocode } from '../api/client';
import type { Place, SearchPlace } from '../api/types';

type Props = {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  picking: boolean;
  onPick: () => void;
  warning: string | null;
};

export function PlaceInput({ label, value, onChange, picking, onPick, warning }: Props) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchPlace[]>([]);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const text = value?.label ?? query;
  const suggestions = open && !value && query.trim().length >= 3;

  useEffect(() => {
    if (value || !open || query.trim().length < 3) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError('');
      void geocode(query.trim(), controller.signal)
        .then(places => {
          if (controller.signal.aborted) return;
          setResults(places);
          setActive(-1);
        })
        .catch((err: unknown) => {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : 'Search unavailable.');
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, value, open]);

  function select(place: Place) {
    onChange({ label: place.label, lat: place.lat, lon: place.lon });
    setQuery('');
    setOpen(false);
    setResults([]);
    setError('');
    setLoading(false);
  }

  return (
    <div className="place-field">
      <label htmlFor={id}>{label}</label>
      <div className="place-control">
        <input id={id} role="combobox" autoComplete="off"
          placeholder={label === 'Origin' ? 'City or address to start' : 'Where are you heading?'}
          value={text} aria-describedby={warning ? `${id}-warning` : undefined} aria-autocomplete="list" aria-expanded={suggestions} aria-controls={`${id}-list`}
          aria-activedescendant={suggestions && active >= 0 ? `${id}-option-${active}` : undefined}
          onFocus={() => {
            setOpen(true);
            if (!value && query.trim().length >= 3) setLoading(true);
          }}
          onBlur={() => { setOpen(false); setLoading(false); }}
          onChange={event => {
            onChange(null);
            setQuery(event.target.value);
            setResults([]);
            setActive(-1);
            setLoading(event.target.value.trim().length >= 3);
            setError('');
            setOpen(true);
          }}
          onKeyDown={event => {
            if (event.key === 'Escape') { setOpen(false); setLoading(false); return; }
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault();
              setOpen(true);
              setActive(index => {
                if (!results.length) return -1;
                if (index < 0) return event.key === 'ArrowDown' ? 0 : results.length - 1;
                return (index + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
              });
            }
            if (event.key === 'Enter' && suggestions) {
              event.preventDefault();
              if (results[active]) select(results[active]);
            }
          }} />
        <div className="place-actions">
          {text && (
            <button type="button" className="clear" aria-label={`Clear ${label.toLowerCase()}`}
              onClick={() => {
                onChange(null);
                setQuery('');
                setResults([]);
                setOpen(false);
                setError('');
                setLoading(false);
              }}>×</button>
          )}
          <button type="button" className="place-pick" aria-label={`Pick ${label.toLowerCase()} on map`}
            aria-pressed={picking} title={`Pick ${label.toLowerCase()} on map`} onClick={() => {
              setQuery('');
              setResults([]);
              setOpen(false);
              setLoading(false);
              setError('');
              onPick();
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true" focusable="false">
                <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" />
                <circle cx="12" cy="10" r="2.5" />
              </svg>
            </button>
        </div>
      </div>
      {warning && <p className="place-warning" id={`${id}-warning`} role="status">{warning}</p>}
      {suggestions && (
        <div className="suggestions">
          <ul id={`${id}-list`} role="listbox" aria-label={`${label} suggestions`}>
            {results.map((place, index) => (
              <li key={`${place.lat},${place.lon},${index}`} role="option" id={`${id}-option-${index}`}
                aria-selected={active === index} className={active === index ? 'active' : ''}
                onMouseDown={event => event.preventDefault()} onClick={() => select(place)}>
                {place.label}
              </li>
            ))}
          </ul>
          <div className="search-message" role="status">
            {error || (loading ? 'Searching…' : results.length === 0 ? 'No places found.' : '')}
          </div>
        </div>
      )}
    </div>
  );
}
