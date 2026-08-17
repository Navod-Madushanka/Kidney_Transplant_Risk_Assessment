// src/layout/navItems.js
import {
  HomeIcon,
  PatientsIcon,
  DonorIcon,
  NewCheckIcon,
  HistoryIcon,
  ExchangeIcon,
  RegisterPairIcon,
} from "../components/icons"

// Single source of truth for Sidebar.jsx (desktop) and TabBar.jsx (mobile) --
// previously two hand-maintained arrays on two different icon sets (Sidebar
// used the app's own icons.jsx, TabBar used lucide-react) that had already
// drifted once (review #2 bug 22: /calculator and /history routes that
// didn't exist). `mobile: true` marks the items TabBar's five-slot bar has
// room for; `mobileLabel` overrides `label` for TabBar's narrower tabs where
// the sidebar's fuller label doesn't fit. Audit Log is deliberately NOT
// here -- it's admin-gated and desktop-only, so Sidebar still adds it as a
// one-off after this list.
export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: HomeIcon, end: true, mobile: true },
  // Primary way to add people (see implementation-prompt-part-f.md F6/F7)
  // -- the two lab documents most checks start from cover a patient and
  // donor together, so registering them together here is the front door.
  // /patients/new and /donors/new still exist for the unassigned-donor
  // case (see PatientsListPage.jsx/DonorsListPage.jsx's demoted "Register
  // individually" links).
  { to: "/pairs/new", label: "Register Patient & Donor", icon: RegisterPairIcon, mobile: false },
  { to: "/patients", label: "Patients", icon: PatientsIcon, mobile: true },
  { to: "/donors", label: "Donors", icon: DonorIcon, mobile: false },
  { to: "/checks/new", label: "New Check", icon: NewCheckIcon, mobile: true },
  {
    to: "/exchange",
    label: "Paired Exchange",
    mobileLabel: "Exchange",
    icon: ExchangeIcon,
    mobile: true,
  },
  { to: "/reports", label: "Reports", icon: HistoryIcon, mobile: true },
]
