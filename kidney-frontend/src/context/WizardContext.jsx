// src/context/WizardContext.jsx
import { createContext } from "react";

// Holds the entire in-progress compatibility check: patient/donor details,
// HLA typing for both people, sensitization data, and the bead specificity
// report. Deliberately separate from AuthContext — auth is "who is using
// the app", this is "what check are they currently building". Kept as its
// own context (rather than folded into Auth) so resetting or persisting the
// wizard never has to reason about login state, and vice versa.
export const WizardContext = createContext(null);