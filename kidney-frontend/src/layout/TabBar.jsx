// src/layout/TabBar.jsx
import { NavLink } from "react-router-dom"
import { HomeIcon, PatientsIcon, DonorIcon, NewCheckIcon, HistoryIcon } from "../components/icons"

const NAV_ITEMS = [
  { to: "/", label: "Home", icon: HomeIcon, end: true },
  { to: "/patients", label: "Patients", icon: PatientsIcon },
  { to: "/checks/new", label: "New Check", icon: NewCheckIcon },
  { to: "/donors", label: "Donors", icon: DonorIcon },
  { to: "/reports", label: "Reports", icon: HistoryIcon },
]

// Mobile-only; hidden at md breakpoint where Sidebar takes over.
// env(safe-area-inset-bottom) clears the home indicator on notched iPhones.
export default function TabBar() {
  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-40 flex border-t border-border bg-surface/95 backdrop-blur-sm"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            [
              "flex flex-1 flex-col items-center justify-center gap-1 py-2 text-[11px] font-medium min-h-[54px]",
              isActive ? "text-accent" : "text-text-muted",
            ].join(" ")
          }
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}