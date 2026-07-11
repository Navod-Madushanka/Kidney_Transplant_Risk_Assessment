// src/App.jsx
import { Navigate, Route, Routes } from "react-router-dom"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import DashboardPage from "./pages/DashboardPage"
import DashboardLayout from "./layout/DashboardLayout"
import ProtectedRoute from "./routes/ProtectedRoute"
import PatientsListPage from "./pages/PatientsListPage"
import NewPatientPage from "./pages/NewPatientPage"
import PatientDetailPage from "./pages/PatientDetailPage"
import DonorsListPage from "./pages/DonorsListPage"
import NewDonorPage from "./pages/NewDonorPage"
import DonorDetailPage from "./pages/DonorDetailPage"

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route 
            path="/" 
            element={<DashboardPage />} 
            handle={{ title: "Dashboard" }} 
          />
          <Route path="/patients" element={<PatientsListPage />} handle={{ title: "Patients" }} />
          <Route path="/patients/new" element={<NewPatientPage />} handle={{ title: "Add patient" }} />
          <Route path="/patients/:patientId" element={<PatientDetailPage />} handle={{ title: "Patient" }} />
          <Route path="/donors" element={<DonorsListPage />} handle={{ title: "Donors" }} />
          <Route path="/donors/new" element={<NewDonorPage />} handle={{ title: "Add donor" }} />
          <Route path="/donors/:donorId" element={<DonorDetailPage />} handle={{ title: "Donor" }} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

export default App