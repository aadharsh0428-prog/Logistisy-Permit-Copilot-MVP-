export default function Header() {
  return (
    <header className="site-header">
      <div className="brand">
        <svg className="brand-mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M3 12L11 4L13 8L21 4L15 20L13 14L5 20L3 12Z"
            fill="currentColor"
          />
        </svg>
        <span>LOGISTISY</span>
      </div>
      <nav className="nav-links" aria-label="Primary navigation">
        <span className="active">Permit Copilot</span>
        <span>Notice Reader</span>
        <span>About Us</span>
      </nav>
    </header>
  );
}
