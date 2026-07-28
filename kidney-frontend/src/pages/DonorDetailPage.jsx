// src/pages/DonorDetailPage.jsx
import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { getDonor, getDonorHlaTypings, replaceDonorHlaTypings } from "../api/donors"
import Badge from "../components/ui/Badge"
import HlaTypingEditor from "../components/domain/hla/HlaTypingEditor"

export default function DonorDetailPage() {
  const { donorId } = useParams()
  const [donor, setDonor] = useState(null)
  const [donorLoadState, setDonorLoadState] = useState("loading")
  const [hlaState, setHlaState] = useState({ state: "loading", data: [] })

  useEffect(() => {
    let cancelled = false

    getDonor(donorId)
      .then((data) => !cancelled && (setDonor(data), setDonorLoadState("loaded")))
      .catch(() => !cancelled && setDonorLoadState("error"))

    getDonorHlaTypings(donorId)
      .then((data) => !cancelled && setHlaState({ state: "loaded", data }))
      .catch(() => !cancelled && setHlaState({ state: "error", data: [] }))

    return () => {
      cancelled = true
    }
  }, [donorId])

  if (donorLoadState === "loading") {
    return (
      <div className="flex justify-center py-16">
        <div className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
      </div>
    )
  }

  if (donorLoadState === "error" || !donor) {
    return <p className="text-[15px] text-text-muted">Couldn't load this donor.</p>
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-[22px] font-bold text-text">{donor.full_name}</h1>
          <Badge status="neutral">{donor.blood_type}</Badge>
        </div>
        <p className="text-[14px] text-text-muted">
          {donor.nic_number || "No NIC on file"} · DOB {donor.date_of_birth}
        </p>
      </div>

      <HlaTypingEditor
        loadState={hlaState.state}
        initialEntries={hlaState.data}
        onSave={(entries) => replaceDonorHlaTypings(donor.id, entries)}
      />
    </div>
  )
}