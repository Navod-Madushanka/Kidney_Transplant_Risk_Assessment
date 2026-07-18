// src/App.jsx
import { Navigate, Route, Routes } from "react-router-dom"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import DashboardLayout from "./layout/DashboardLayout"
import ProtectedRoute from "./routes/ProtectedRoute"
import DashboardPage from "./pages/DashboardPage"
import PatientsListPage from "./pages/PatientsListPage"
import NewPatientPage from "./pages/NewPatientPage"
import PatientDetailPage from "./pages/PatientDetailPage"
import DonorsListPage from "./pages/DonorsListPage"
import NewDonorPage from "./pages/NewDonorPage"
import DonorDetailPage from "./pages/DonorDetailPage"

import { WizardProvider } from "./context/WizardProvider"
import WizardLayout from "./layout/WizardLayout"
import PhotoUploadsStep from "./pages/PhotoUploadsStep"
import DetailsStep from "./pages/DetailsStep"
import HlaTypingStep from "./pages/HlaTypingStep"
import SensitizationStep from "./pages/SensitizationStep"
import BeadSpecificityStep from "./pages/BeadSpecificityStep"
import ReviewStep from "./pages/ReviewStep"
import ReportDetailPage from "@/pages/ReportDetailPage"

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<DashboardPage />} handle={{ title: "Dashboard" }} />
          <Route path="/patients" element={<PatientsListPage />} handle={{ title: "Patients" }} />
          <Route path="/patients/new" element={<NewPatientPage />} handle={{ title: "Add patient" }} />
          <Route path="/patients/:patientId" element={<PatientDetailPage />} handle={{ title: "Patient" }} />
          <Route path="/donors" element={<DonorsListPage />} handle={{ title: "Donors" }} />
          <Route path="/donors/new" element={<NewDonorPage />} handle={{ title: "Add donor" }} />
          <Route path="/donors/:donorId" element={<DonorDetailPage />} handle={{ title: "Donor" }} />
        </Route>

        {/* Compatibility check wizard — its own full-screen layout branch,
            deliberately outside DashboardLayout (no sidebar/tab-bar; see
            WizardLayout's own comment for the reasoning). WizardProvider is
            scoped to just this subtree so wizard state never exists before
            a doctor starts a check and resets cleanly between checks. */}
        <Route
          path="/checks/new"
          element={
            <WizardProvider>
              <WizardLayout />
            </WizardProvider>
          }
        >
          <Route index element={<Navigate to="photos" replace />} />
          <Route path="photos" element={<PhotoUploadsStep />} handle={{ title: "New Check" }} />
          <Route path="details" element={<DetailsStep />} handle={{ title: "New Check" }} />
          <Route path="hla" element={<HlaTypingStep />} handle={{ title: "New Check" }} />
          <Route path="sensitization" element={<SensitizationStep />} handle={{ title: "New Check" }} />
          <Route path="bead-chart" element={<BeadSpecificityStep />} handle={{ title: "New Check" }} />
          <Route path="review" element={<ReviewStep />} handle={{ title: "New Check" }} />
        </Route>

        {/* Standalone Report Details Page (Fixed: Moved out of the wizard structure) */}
        <Route path="/reports/:reportId" element={<ReportDetailPage />} handle={{ title: "Report" }} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App