// src/App.jsx
import { Navigate, Route, Routes } from "react-router-dom"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import DashboardLayout from "./layout/DashboardLayout"
import ProtectedRoute from "./routes/ProtectedRoute"

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<div>Dashboard placeholder</div>} handle={{ title: "Dashboard" }} />
          {/* patients, donors, checks, reports routes go here next */}
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App