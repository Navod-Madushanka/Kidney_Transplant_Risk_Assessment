// src/pages/NewPatientPage.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import Card from "../components/ui/Card"
import PatientForm from "../components/domain/patient/PatientForm"
import { createPatient } from "../api/patients"

export default function NewPatientPage() {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(payload) {
    setIsSubmitting(true)
    try {
      const patient = await createPatient(payload)
      navigate(`/patients/${patient.id}`, { replace: true })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-[22px] font-bold text-text mb-1">Add patient</h1>
      <p className="text-[14px] text-text-muted mb-6">
        Basic details now — HLA typing and antibody profiles can be added from the patient's page.
      </p>
      <Card>
        <PatientForm onSubmit={handleSubmit} isSubmitting={isSubmitting} submitLabel="Add patient" />
      </Card>
    </div>
  )
}