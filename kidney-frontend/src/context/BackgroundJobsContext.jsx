// src/context/BackgroundJobsContext.jsx
import { createContext } from "react"

// Tracks OCR extraction jobs started outside the compatibility-check
// wizard (currently: registration-time bead-specificity extraction, see
// NewPairPage.jsx) that need to keep reporting progress no matter what page
// the doctor navigates to afterward -- unlike WizardContext, which resets
// per wizard session and only exists inside /checks/new/*, this is mounted
// once above every authenticated route (see App.jsx) so it survives
// navigating anywhere in the dashboard.
export const BackgroundJobsContext = createContext(null)
