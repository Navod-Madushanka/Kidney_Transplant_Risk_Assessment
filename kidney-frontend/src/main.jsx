// src/main.jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthProvider"
import { ReviewedReportsProvider } from "./context/ReviewedReportsProvider"
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ReviewedReportsProvider>
          <App />
        </ReviewedReportsProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);