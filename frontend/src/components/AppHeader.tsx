import logoUrl from '../assets/truck-logo.png';

export function AppHeader() {
  return (
    <header className="app-header">
      <span className="app-header__badge">
        <img src={logoUrl} alt="Weather-Aware Truck Routing logo" height={40} />
      </span>
      <h1>Weather-Aware Truck Routing</h1>
    </header>
  );
}
