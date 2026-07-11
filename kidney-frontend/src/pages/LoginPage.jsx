// src/pages/LoginPage.jsx
import { useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { ApiError } from "../api/client"
import Card from "../components/ui/Card"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  
  const redirectTo = location.state?.from?.pathname || "/"

  const [form, setForm] = useState({
    email: "",
    password: "",
  })

  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  function updateField(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  function validate() {
    const next = {}
    if (!form.email.trim()) next.email = "Email is required"
    if (!form.password) next.password = "Password is required"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError("")
    if (!validate()) return

    setIsSubmitting(true)
    try {
      await login(form.email.trim(), form.password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setFormError("Incorrect email or password.")
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
              autoComplete="current-password"
              value={form.password}
              onChange={updateField("password")}
              error={errors.password}
              required
            />

            {formError && (
              <p role="alert" className="text-[13px] text-high-risk font-medium">
                {formError}
              </p>
            )}

            <Button type="submit" loading={isSubmitting} className="w-full mt-2">
              Log in
            </Button>
          </form>
        </Card>

        <p className="text-center text-[13px] text-text-muted mt-6">
          Need an account?{" "}
          <Link to="/register" className="text-accent font-semibold hover:text-accent-hover">
            Register your hospital
          </Link>
        </p>
      </div>
    </div>
  )
}