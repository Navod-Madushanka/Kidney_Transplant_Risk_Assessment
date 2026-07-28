// src/components/domain/sensitization/SensitizationEventEditor.jsx
import { useState } from "react"
import Select from "../../ui/Select"
import InputField from "../../ui/InputField"
import Button from "../../ui/Button"
import Card from "../../ui/Card"
import { SENSITIZATION_EVENT_OPTIONS } from "../../../constants/clinicalEnums"

const EVENT_LABELS = Object.fromEntries(SENSITIZATION_EVENT_OPTIONS.map((o) => [o.value, o.label]))

/**
 * loadState: "loading" | "loaded" | "error"
 *
 * Usage:
 *   <SensitizationEventEditor
 *     loadState={loadState}
 *     existingEvents={events}
 *     onAdd={(entries) => createSensitizationEvents(patient.id, entries)}
 *   />
 */
export default function SensitizationEventEditor({ loadState, existingEvents = [], onAdd }) {
  const [eventType, setEventType] = useState("")
  const [eventDate, setEventDate] = useState("")
  const [error, setError] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [justAdded, setJustAdded] = useState([])

  async function handleAdd(e) {
    e.preventDefault()
    setError("")

    if (!eventType || !eventDate) {
      setError("Select an event type and date.")
      return
    }

    setIsSaving(true)
    try {
      const created = await onAdd([{ event_type: eventType, event_date: eventDate }])
      setJustAdded((prev) => [...created, ...prev])
      setEventType("")
      setEventDate("")
    } catch (err) {
      setError(err.message || "Couldn't add this event. Please try again.")
    } finally {
      setIsSaving(false)
    }
  }

  const displayEvents = [...justAdded, ...existingEvents]

  return (
    <Card>
      <Card.Header
        title="Sensitization events"
        subtitle="Previous transplant, pregnancy, or transfusion — feeds the sensitization score"
      />

      <form onSubmit={handleAdd} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-start mb-4">
        <Select
          options={SENSITIZATION_EVENT_OPTIONS}
          placeholder="Event type"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        />
        <InputField
          type="date"
          value={eventDate}
          onChange={(e) => setEventDate(e.target.value)}
        />
        <Button type="submit" size="sm" loading={isSaving}>
          Add event
        </Button>
      </form>

      {error && <p className="text-[13px] text-high-risk font-medium mb-3">{error}</p>}

      {loadState === "loading" ? (
        <div className="flex justify-center py-6">
          <div className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
        </div>
      ) : displayEvents.length === 0 ? (
        <p className="text-[14px] text-text-muted">No sensitization events recorded yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {displayEvents.map((event) => (
            <li key={event.id} className="py-2.5 flex items-center justify-between text-[14px]">
              <span className="text-text font-medium">{EVENT_LABELS[event.event_type] ?? event.event_type}</span>
              <span className="text-text-muted tabular-nums">{event.event_date}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}