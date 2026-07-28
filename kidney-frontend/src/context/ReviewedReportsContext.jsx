// src/context/ReviewedReportsContext.jsx
//
// Just the context object. The provider component lives in
// ReviewedReportsProvider.jsx (imported from src/main.jsx) — keeping this
// file to a single non-component export is what Vite's fast-refresh
// requires; a file that exports both a component and a plain value (like a
// context) opts the whole file out of fast refresh
// (react-refresh/only-export-components). This file used to also define
// ReviewedReportsProvider, but that was dead code: main.jsx has always
// imported the provider from ./ReviewedReportsProvider instead.
import { createContext } from "react"

export const ReviewedReportsContext = createContext(null)