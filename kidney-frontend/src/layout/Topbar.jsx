// src/layout/Topbar.jsx
import { useAuth } from "../hooks/useAuth"
import { LogoutIcon } from "../components/icons"

// Mobile-only (Sidebar shows this info on desktop).
export default function Topbar({ title }) {
  const { logout } = useAuth()

  return (
    <header className="md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-surface/90 backdrop-blur-sm px-4 h-14">
      <p className="text-[17px] font-semibold text-text truncate">{title}</p>
      <button onClick={logout} aria-label="Log out" className="p-2 -mr-2 text-text-muted hover:text-high-risk">
        <LogoutIcon className="h-5 w-5" aria-hidden="true" />
      </button>
    </header>
  )
}