// src/pages/DashboardPage.jsx
import { useAuth } from "../hooks/useAuth"

export default function DashboardPage() {
  const { user } = useAuth()

  return (
    <div className="space-y-8">
      <div className="bg-white rounded-3xl p-8 shadow-sm">
        <h1 className="text-4xl font-semibold text-text">
          Welcome back, Dr. {user?.fullName ? user.fullName.split(" ").pop() : "Doctor"}
        </h1>
        <p className="text-xl text-text-muted mt-2">
          Kandy National Hospital
        </p>
      </div>

      <div className="bg-white rounded-3xl p-8 shadow-sm">
        <h2 className="text-2xl font-medium text-text mb-6">You have successfully logged in!</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-gray-50 rounded-2xl p-6">
            <p className="text-sm text-text-muted">Status</p>
            <p className="text-2xl font-semibold text-green-600 mt-1">Authenticated</p>
          </div>
          <div className="bg-gray-50 rounded-2xl p-6">
            <p className="text-sm text-text-muted">Hospital</p>
            <p className="text-2xl font-semibold text-text mt-1">
              {user?.hospitalName || "Kandy National Hospital"}
            </p>
          </div>
          <div className="bg-gray-50 rounded-2xl p-6">
            <p className="text-sm text-text-muted">Role</p>
            <p className="text-2xl font-semibold text-text mt-1">{user?.role || "Doctor"}</p>
          </div>
        </div>
      </div>
    </div>
  )
}