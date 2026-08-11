// src/layout/Sidebar.jsx
import { NavLink } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import {
  HomeIcon,
  PatientsIcon,
  DonorIcon,
  NewCheckIcon,
  HistoryIcon,
  ExchangeIcon,
  AuditIcon,
  LogoutIcon,
  RegisterPairIcon,
} from "../components/icons"

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: HomeIcon, end: true },
  // Primary way to add people (see implementation-prompt-part-f.md F6/F7)
  // -- the two lab documents most checks start from cover a patient and
  // donor together, so registering them together here is the front door.
  // /patients/new and /donors/new still exist for the unassigned-donor
  // case (see PatientsListPage.jsx/DonorsListPage.jsx's demoted "Register
  // individually" links).
  { to: "/pairs/new", label: "Register Patient & Donor", icon: RegisterPairIcon },
  { to: "/patients", label: "Patients", icon: PatientsIcon },
  { to: "/donors", label: "Donors", icon: DonorIcon },
  { to: "/checks/new", label: "New Check", icon: NewCheckIcon },
  { to: "/exchange", label: "Paired Exchange", icon: ExchangeIcon },
  { to: "/reports", label: "Reports", icon: HistoryIcon },
]

function navLinkClass({ isActive }) {
  return [
    "flex items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-medium transition-colors",
    isActive ? "bg-accent-subtle text-accent" : "text-text-muted hover:bg-bg hover:text-text",
  ].join(" ")
}

export default function Sidebar() {
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
            {label}
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
          <p className="text-[13px] font-semibold text-text truncate">{user?.full_name ?? user?.email}</p>
          <p className="text-[12px] text-text-muted truncate">{user?.hospital_name ?? user?.role}</p>
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