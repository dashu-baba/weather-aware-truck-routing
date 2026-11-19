import truckLoaderUrl from "../assets/truck-loader.svg";
import logoUrl from "../assets/truck-logo.png";

/** Self-animating SVG, with an explicit still-image fallback for reduced motion. */
export default function TruckLoader({ label = "Planning your route…", width = 280 }: { label?: string; width?: number }) {
  return (
    <div className="truck-loader" role="status" aria-live="polite">
      <picture>
        <source media="(prefers-reduced-motion: reduce)" srcSet={logoUrl} />
        <img src={truckLoaderUrl} width={width} alt="" />
      </picture>
      <span>{label}</span>
    </div>
  );
}
