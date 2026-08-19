"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  ["/", "Dashboard", "01"],
  ["/discovery", "Discovery Studio", "02"],
  ["/capabilities", "Capabilities", "03"],
  ["/replay", "Deterministic Replay", "04"],
  ["/runs", "Runs", "05"],
  ["/interventions", "Interventions", "06"],
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">BA</div>
        <div>
          <div className="brand-title">Banking AI Admin</div>
          <div className="brand-subtitle">System Operator</div>
        </div>
      </div>
      <Link className="btn primary" href="/discovery">New Discovery Run</Link>
      <nav className="nav">
        {items.map(([href, label, index]) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link key={href} className={active ? "active" : ""} href={href}>
              <span className="mono">{index}</span>
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div style={{ marginTop: "auto" }} className="nav">
        <a href="#" aria-disabled="true">Settings</a>
        <a href="#" aria-disabled="true">Support</a>
      </div>
    </aside>
  );
}
