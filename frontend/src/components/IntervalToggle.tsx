type Props = { intervals: number[]; interval: number; onChange: (interval: number) => void };

export function IntervalToggle({ intervals, interval, onChange }: Props) {
  return (
    <div className="interval-control">
      <span id="interval-label">Checkpoint spacing</span>
      <div className="interval-toggle" role="group" aria-labelledby="interval-label">
        {intervals.map(value => (
          <button key={value} type="button" aria-pressed={value === interval}
            onClick={() => onChange(value)}>{value} mi</button>
        ))}
      </div>
    </div>
  );
}
