// src/components/icons.jsx
function iconProps(props) {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    ...props,
  }
}

export function HomeIcon(props) {
  return <svg {...iconProps(props)}><path d="M4 11.5L12 4l8 7.5M6 9.5V20h12V9.5" /></svg>
}
export function PatientsIcon(props) {
  return <svg {...iconProps(props)}><circle cx="12" cy="8" r="3.5" /><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6" /></svg>
}
export function DonorIcon(props) {
  return <svg {...iconProps(props)}><path d="M12 20s-7-4.35-9.5-9.02C1 7.5 3 4.5 6.2 4.5c1.9 0 3.3 1 3.8 2.2.5-1.2 1.9-2.2 3.8-2.2 3.2 0 5.2 3 3.7 6.48C19 15.65 12 20 12 20z" /></svg>
}
export function NewCheckIcon(props) {
  return <svg {...iconProps(props)}><circle cx="12" cy="12" r="8.5" /><path d="M12 8v8M8 12h8" /></svg>
}
export function HistoryIcon(props) {
  return <svg {...iconProps(props)}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>
}
export function AuditIcon(props) {
  return <svg {...iconProps(props)}><path d="M12 3.5l7 3v5.2c0 4.4-3 8.1-7 9.3-4-1.2-7-4.9-7-9.3V6.5l7-3z" /><path d="M9 12l2 2 4-4.5" /></svg>
}
export function LogoutIcon(props) {
  return <svg {...iconProps(props)}><path d="M9 4H6a2 2 0 00-2 2v12a2 2 0 002 2h3M15 16l4-4-4-4M19 12H9" /></svg>
}