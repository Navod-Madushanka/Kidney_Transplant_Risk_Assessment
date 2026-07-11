// src/layout/Topbar.jsx
import { useAuth } from "../hooks/useAuth"
import { LogOut } from "lucide-react"

export default function Topbar({ title }) {
  const { user, logout } = useAuth()

  return (
    <header className="md:hidden sticky top-0 z-50 bg-white border-b border-gray-200 px-4 h-14 flex items-center justify-between backdrop-blur-lg">
      <div>
        <p className="font-semibold text-[17px] text-text truncate">{title}</p>
        <p className="text-xs text-text-muted -mt-0.5">
          {user?.hospitalName || "Kandy National Hospital"}
        </p>
      </div>

      <button
        onClick={logout}
        className="p-2 -mr-2 text-text-muted hover:text-red-500 rounded-full active:bg-gray-100 transition-all"
      >
        <LogOut className="w-5 h-5" />
      </button>
    </header>
  )
}