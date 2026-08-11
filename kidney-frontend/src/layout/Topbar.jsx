// src/layout/Topbar.jsx
import { useAuth } from "../hooks/useAuth"
import { LogOut } from "lucide-react"

export default function Topbar({ title }) {
  const { user, logout } = useAuth()

  return (
    <header
      className="md:hidden sticky top-0 z-50 bg-surface border-b border-border px-4 min-h-14 flex items-center justify-between backdrop-blur-lg"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
    >
      <div className="min-w-0">
        <p className="font-semibold text-[17px] text-text truncate">{title}</p>
        <p className="text-xs text-text-muted -mt-0.5 truncate">
          {user?.hospitalName || "Kandy National Hospital"}
        </p>
      </div>

      <button
        onClick={logout}
        className="p-2 -mr-2 min-h-11 min-w-11 flex items-center justify-center text-text-muted hover:text-high-risk rounded-full active:bg-bg transition-all"
      >
        <LogOut className="w-5 h-5" />
      </button>
    </header>
  )
}