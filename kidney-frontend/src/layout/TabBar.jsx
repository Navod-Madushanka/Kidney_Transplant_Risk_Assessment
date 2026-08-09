// src/layout/TabBar.jsx
import { NavLink } from "react-router-dom"
import { Home, Users, FilePlus, Repeat, FileText } from "lucide-react"

// Review #2 bug 22: /calculator and /history were never real routes (see
// App.jsx's <Routes> tree) -- every tap 404'd via the catch-all redirect.
// Paths and labels below now match Sidebar.jsx's desktop nav exactly
// (/checks/new "New Check", /reports "Reports"), which is also where
// Paired Exchange -- previously missing from mobile nav entirely -- comes
// from.
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/patients", label: "Patients", icon: Users },
  { to: "/checks/new", label: "New Check", icon: FilePlus },
  { to: "/exchange", label: "Exchange", icon: Repeat },
  { to: "/reports", label: "Reports", icon: FileText },
]

export default function TabBar() {
  return (
    <nav 
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-xl border-t border-gray-200 shadow-lg"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="max-w-md mx-auto flex items-center justify-around py-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => `
              flex flex-col items-center justify-center py-2 px-3 text-[10px] font-medium transition-all flex-1
              ${isActive ? "text-blue-600" : "text-gray-500"}
            `}
          >
            {({ isActive }) => (
              <>
                <Icon 
                  className={`w-6 h-6 mb-0.5 transition-transform ${isActive ? "scale-110" : ""}`} 
                />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}