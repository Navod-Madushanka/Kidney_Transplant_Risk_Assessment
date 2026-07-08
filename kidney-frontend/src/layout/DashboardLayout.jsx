// src/layout/DashboardLayout.jsx
import { Outlet, useMatches } from "react-router-dom"
import Sidebar from "./Sidebar"
import Topbar from "./Topbar"
import TabBar from "./TabBar"

// Reads a page title from the matched route's `handle`, e.g.:
//   <Route path="/patients" element={<PatientsListPage />} handle={{ title: "Patients" }} />
export default function DashboardLayout() {
  const matches = useMatches()
  const currentTitle = [...matches].reverse().find((m) => m.handle?.title)?.handle?.title ?? "Dashboard"

  return (
    <div className="min-h-screen flex bg-bg">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar title={currentTitle} />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 pb-20 md:pb-6 max-w-6xl w-full mx-auto">
          <Outlet />
        </main>
        <TabBar />
      </div>
    </div>
  )
}