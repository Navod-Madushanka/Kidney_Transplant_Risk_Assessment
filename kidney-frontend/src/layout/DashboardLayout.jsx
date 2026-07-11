// src/layout/DashboardLayout.jsx
import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"
import Topbar from "./Topbar"
import TabBar from "./TabBar"

export default function DashboardLayout() {
  return (
    <div className="min-h-screen flex bg-bg">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar title="Dashboard" />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 pb-24 md:pb-6 max-w-6xl w-full mx-auto">
          <Outlet />
        </main>
        <TabBar />
      </div>
    </div>
  )
}