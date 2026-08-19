export function TopBar() {
  return (
    <header className="topbar">
      <strong>Aegis Operator Console</strong>
      <div className="row">
        <span className="badge info">System-Control</span>
        <span className="badge human">Operator-Required</span>
      </div>
    </header>
  );
}
