// src/routes/ProtectedRoute.jsx
import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"

export default function ProtectedRoute({ allowedRoles }) {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg">
        <div
          className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
          role="status"
          aria-label="Loading"
        />
      </div>
    )
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (allowedRoles && !allowedRoles.includes(user?.role)) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}