// src/pages/RegisterPage.jsx
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { ApiError } from "../api/client"
import Card from "../components/ui/Card"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    hospitalName: "",
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
  })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  function updateField(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  function validate() {
    const next = {}
    if (!form.hospitalName.trim()) next.hospitalName = "Hospital name is required"
    if (!form.fullName.trim()) next.fullName = "Your full name is required"
    if (!form.email.trim()) next.email = "Email is required"
    if (!form.password) next.password = "Password is required"
    else if (form.password.length < 8) next.password = "Password must be at least 8 characters"
    if (form.confirmPassword !== form.password) next.confirmPassword = "Passwords don't match"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError("")
    if (!validate()) return

    setIsSubmitting(true)
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        fullName: form.fullName.trim(),
        hospitalName: form.hospitalName.trim(),
      })
      navigate("/", { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setFormError(err.message || "An account with this email already exists.")
      } else {
        setFormError("Something went wrong. Please try again.")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <p className="text-[20px] font-bold text-text">Kidney Transplant</p>
          <p className="text-[14px] text-text-muted">Compatibility System</p>
        </div>

        <Card>
          <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
            <InputField
              label="Hospital name"
              value={form.hospitalName}
              onChange={updateField("hospitalName")}
              error={errors.hospitalName}
              required
            />
            <InputField
              label="Your full name"
              value={form.fullName}
              onChange={updateField("fullName")}
              error={errors.fullName}
              required
            />
            <InputField
              label="Email"
              type="email"
              autoComplete="username"
              value={form.email}
              onChange={updateField("email")}
              error={errors.email}
              required
            />
            <InputField
              label="Password"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={updateField("password")}
              error={errors.password}
              required
            />
            <InputField
              label="Confirm password"
              type="password"
              autoComplete="new-password"
              value={form.confirmPassword}
              onChange={updateField("confirmPassword")}
              error={errors.confirmPassword}
              required
            />

            {formError && (
              <p role="alert" className="text-[13px] text-high-risk font-medium">
                {formError}
              </p>
            )}

            <Button type="submit" loading={isSubmitting} className="w-full mt-2">
              Create account
            </Button>
          </form>
        </Card>

        <p className="text-center text-[13px] text-text-muted mt-6">
          Already have an account?{" "}
          <Link to="/login" className="text-accent font-semibold hover:text-accent-hover">
            Log in
          </Link>
        </p>
      </div>
    </div>
  )
}