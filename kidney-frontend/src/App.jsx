// src/App.jsx
import { useEffect, useState } from 'react'
import { apiGet } from './api/client'

function App() {
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    apiGet('/health/db')
      .then(() => setStatus('connected'))
      .catch(() => setStatus('down'))
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md text-center">
        <h1 className="text-2xl font-bold text-gray-800 mb-4">
          Kidney Transplant Compatibility System
        </h1>

        {status === 'checking' && (
          <span className="inline-block px-4 py-2 rounded-full bg-gray-200 text-gray-700">
            Checking backend...
          </span>
        )}

        {status === 'connected' && (
          <span className="inline-block px-4 py-2 rounded-full bg-green-100 text-green-700 font-medium">
            Backend connected
          </span>
        )}

        {status === 'down' && (
          <span className="inline-block px-4 py-2 rounded-full bg-red-100 text-red-700 font-medium">
            Backend down
          </span>
        )}
      </div>
    </div>
  )
}

export default App