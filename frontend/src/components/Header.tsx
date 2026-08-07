interface Props {
  dockerAvailable: boolean | null;
  onHome: () => void;
}

export function Header({ dockerAvailable, onHome }: Props) {
  return (
    <header className="app-header">
      <button className="brand" onClick={onHome}>
        <span className="brand-mark">F</span>
        <div>
          <h1>Forge</h1>
          <p>AI Agent Builder</p>
        </div>
      </button>
      <div
        className={`docker-pill ${
          dockerAvailable === null ? "pending" : dockerAvailable ? "up" : "down"
        }`}
        title={
          dockerAvailable === null
            ? "Checking Docker…"
            : dockerAvailable
              ? "Docker is reachable"
              : "Docker is not reachable"
        }
      >
        <span className="dot" />
        {dockerAvailable === null ? "Checking Docker…" : dockerAvailable ? "Docker up" : "Docker down"}
      </div>
    </header>
  );
}
