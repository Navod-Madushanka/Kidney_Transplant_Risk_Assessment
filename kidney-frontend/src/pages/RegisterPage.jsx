// src/pages/RegisterPage.jsx
import { Link } from "react-router-dom"
import Card from "../components/ui/Card"

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <p className="text-[20px] font-bold text-text">Kidney Transplant</p>
          <p className="text-[14px] text-text-muted">Compatibility System</p>
        </div>

        <Card>
          <div className="flex flex-col gap-3 text-center">
            <p className="text-[15px] font-semibold text-text">Self-registration is disabled</p>
            <p className="text-[13px] text-text-muted">
              Contact your system administrator to request an account.
            </p>
          </div>
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
