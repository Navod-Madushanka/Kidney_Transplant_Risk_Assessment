// src/layout/Sidebar.jsx
import { NavLink } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { AuditIcon, LogoutIcon } from "../components/icons"
import { NAV_ITEMS } from "./navItems"

function navLinkClass({ isActive }) {
  return [
    "flex items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-medium transition-colors",
    isActive ? "bg-accent-subtle text-accent" : "text-text-muted hover:bg-bg hover:text-text",
  ].join(" ")
}

export default function Sidebar({ pendingExchangeCount = 0 }) {
  const { user, logout } = useAuth()
  const isAdmin = user?.role === "admin"

  return (
    <aside className="hidden md:flex md:flex-col md:w-60 md:shrink-0 md:border-r md:border-border md:bg-surface md:h-screen md:sticky md:top-0">
      <div className="px-5 py-6">
        <p className="text-[15px] font-bold text-text leading-tight">Kidney Transplant</p>
        <p className="text-[13px] text-text-muted">Compatibility System</p>
      </div>

      <nav className="flex-1 px-3 flex flex-col gap-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={navLinkClass}>
            <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
            <span className="flex-1">{label}</span>
            {/* K6: pending-decisions count -- a workflow badge, so accent,
                never the clinical palette (see index.css's @theme comment:
                clear/moderate/high-moderate/high-risk are reserved for
                clinical status only). */}
            {to === "/exchange" && pendingExchangeCount > 0 && (
              <span className="min-w-5 h-5 px-1 rounded-full bg-accent text-white text-[11px] font-semibold flex items-center justify-center">
                {pendingExchangeCount}
              </span>
            )}
          </NavLink>
        ))}

        {isAdmin && (
          <NavLink to="/audit-log" className={navLinkClass}>
            <AuditIcon className="h-5 w-5 shrink-0" aria-hidden="true" />
            Audit Log
          </NavLink>
        )}
      </nav>

      <div className="px-3 py-4 border-t border-border">
        <div className="px-3 pb-3">
          <p className="text-[13px] font-semibold text-text truncate">{user?.fullName ?? user?.email}</p>
          <p className="text-[12px] text-text-muted truncate">{user?.hospitalName ?? user?.role}</p>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-medium text-text-muted hover:bg-bg hover:text-high-risk transition-colors"
        >
          <LogoutIcon className="h-5 w-5 shrink-0" aria-hidden="true" />
          Log out
        </button>
      </div>
    </aside>
  )
}