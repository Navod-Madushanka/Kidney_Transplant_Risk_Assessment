// src/layout/DashboardLayout.jsx
import { Outlet, matchPath, useLocation } from "react-router-dom"
import Sidebar from "./Sidebar"
import Topbar from "./Topbar"
import TabBar from "./TabBar"
import { usePendingExchangeProposalsCount } from "../hooks/usePendingExchangeProposalsCount"

// Mirrors the handle={{ title }} App.jsx already declares on every route
// nested under <DashboardLayout> -- but useMatches() (the "correct" way to
// read a route's handle) only works under a data router
// (createBrowserRouter), and this app uses the plain declarative
// <Routes>/<Route> form (see App.jsx), so useMatches() throws "must be used
// within a data router" and takes down this entire layout on every route.
// matchPath works standalone against any <Routes> tree, so this table is a
// deliberate, small duplication of App.jsx's titles rather than a read from
// its actual route config. Ordered exactly like App.jsx's JSX -- static
// segments (e.g. "/patients/new") before the dynamic ones they'd otherwise
// collide with ("/patients/:patientId" also structurally matches
// "/patients/new"), same disambiguation the real router tree gets from its
// ranking algorithm.
const ROUTE_TITLES = [
  { path: "/", title: "Dashboard" },
  { path: "/pairs/new", title: "Register patient & donor" },
  { path: "/patients/new", title: "Add patient" },
  { path: "/patients/:patientId/donor-search", title: "Search donors" },
  { path: "/patients/:patientId", title: "Patient" },
  { path: "/patients", title: "Patients" },
  { path: "/donors/new", title: "Add donor" },
  { path: "/donors/:donorId/safety-assessment", title: "Donor safety assessment" },
  { path: "/donors/:donorId", title: "Donor" },
  { path: "/donors", title: "Donors" },
  { path: "/exchange/proposals/:proposalId", title: "Exchange proposal" },
  { path: "/exchange/proposals", title: "Exchange proposals" },
  { path: "/exchange", title: "Paired exchange" },
  { path: "/reports", title: "Reports" },
  { path: "/checks/start-from-records", title: "Start check from records" },
  { path: "/audit-log", title: "Audit log" },
]

function titleForPathname(pathname) {
  const match = ROUTE_TITLES.find((route) => matchPath(route.path, pathname))
  return match?.title ?? ""
}

export default function DashboardLayout() {
  const { pathname } = useLocation()
  const title = titleForPathname(pathname)
  // K6: polled pending-decisions count for the Exchange nav badge -- lifted
  // here (rather than polled separately inside Sidebar and TabBar) so both
  // navs share one poll loop instead of two independent ones.
  const pendingExchangeCount = usePendingExchangeProposalsCount()

  return (
    <div className="min-h-screen flex bg-bg">
      <Sidebar pendingExchangeCount={pendingExchangeCount} />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar title={title} />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 pb-24 md:pb-6 max-w-6xl w-full mx-auto">
          <Outlet />
        </main>
        <TabBar pendingExchangeCount={pendingExchangeCount} />
      </div>
    </div>
  )
}
