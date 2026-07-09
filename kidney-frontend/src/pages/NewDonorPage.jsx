// src/pages/NewDonorPage.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import Card from "../components/ui/Card"
import DonorForm from "../components/domain/donor/DonorForm"
import { createDonor } from "../api/donors"

export default function NewDonorPage() {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(payload) {
    setIsSubmitting(true)
    try {
      const donor = await createDonor(payload)
      navigate(`/donors/${donor.id}`, { replace: true })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-[22px] font-bold text-text mb-1">Add donor</h1>
      <p className="text-[14px] text-text-muted mb-6">
        Basic details now — HLA typing can be added from the donor's page.
      </p>
      <Card>
        <DonorForm onSubmit={handleSubmit} isSubmitting={isSubmitting} submitLabel="Add donor" />
      </Card>
    </div>
  )
}