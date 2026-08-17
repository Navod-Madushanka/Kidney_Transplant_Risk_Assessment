// src/layout/TabBar.jsx
import { NavLink } from "react-router-dom"
import { NAV_ITEMS } from "./navItems"

// Review #2 bug 22: /calculator and /history were never real routes (see
// App.jsx's <Routes> tree) -- every tap 404'd via the catch-all redirect.
// NAV_ITEMS is shared with Sidebar.jsx (see that file's docstring) so the
// two navs can no longer drift the way they did before -- this filters to
// the subset flagged mobile:true and uses each item's mobileLabel where the
// sidebar's fuller label doesn't fit a five-slot bar.
const MOBILE_NAV_ITEMS = NAV_ITEMS.filter((item) => item.mobile)

export default function TabBar({ pendingExchangeCount = 0 }) {
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface/95 backdrop-blur-xl border-t border-border shadow-lg"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="max-w-md mx-auto flex items-center justify-around py-1">
        {MOBILE_NAV_ITEMS.map(({ to, label, mobileLabel, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end ?? to === "/"}
            className={({ isActive }) => `
              relative flex flex-col items-center justify-center min-h-11 py-2 px-3 text-[10px] font-medium transition-all flex-1
              ${isActive ? "text-accent" : "text-text-muted"}
            `}
          >
            {({ isActive }) => (
              <>
                <span className="relative">
                  <Icon
                    className={`w-6 h-6 mb-0.5 transition-transform ${isActive ? "scale-110" : ""}`}
                  />
                  {/* K6: same workflow badge as Sidebar's, accent not
                      clinical (see that file's comment). */}
                  {to === "/exchange" && pendingExchangeCount > 0 && (
                    <span className="absolute -top-1 -right-1.5 min-w-4 h-4 px-1 rounded-full bg-accent text-white text-[9px] font-semibold flex items-center justify-center">
                      {pendingExchangeCount}
                    </span>
                  )}
                </span>
                <span>{mobileLabel ?? label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}