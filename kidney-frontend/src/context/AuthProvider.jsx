// src/context/AuthProvider.jsx
import { useCallback, useEffect, useReducer } from "react";
import {
  apiGet,
  apiPost,
  readSession,
  writeSession,
  clearSession,
  setOnAuthExpired,
} from "../api/client";
import { decodeJwt, isTokenExpired } from "../utils/jwt";
import { AuthContext } from "./AuthContext";

const initialState = {
  status: "loading",
  user: null,
  expiresAt: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "AUTHENTICATED":
      // expiresAt (ms epoch, from the JWT's own exp claim) is what
      // SessionExpiryBanner.jsx times its warning off of -- set fresh on
      // every login/reauthenticate/session-restore so re-authenticating
      // near expiry actually pushes the warning back out, not just
      // silences it once.
      return { status: "authenticated", user: action.user, expiresAt: action.expiresAt };
    case "PROFILE_LOADED":
      // Only merges into an already-authenticated session -- a stray
      // /auth/me response resolving after logout (or after the token
      // expired mid-flight) must not resurrect a signed-out user.
      return state.status === "authenticated"
        ? { ...state, user: { ...state.user, ...action.profile } }
        : state;
    case "UNAUTHENTICATED":
      return { status: "unauthenticated", user: null, expiresAt: null };
    default:
      return state;
  }
}

function buildUser(session, claims) {
  return {
    id: claims.sub,
    hospitalId: claims.hospital_id,
    role: claims.role,
    email: session.email,
    fullName: session.full_name ?? null,
    hospitalName: session.hospital_name ?? null,
  };
}

export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // Best-effort: on failure the sidebar just falls back to email/role
  // (buildUser's `?? null`) exactly as it did before this existed -- a
  // doctor can still use the whole app without a name/hospital showing.
  const loadProfile = useCallback((session) => {
    apiGet("/auth/me")
      .then((profile) => {
        writeSession({
          ...session,
          full_name: profile.full_name,
          hospital_name: profile.hospital_name,
        });
        dispatch({
          type: "PROFILE_LOADED",
          profile: { fullName: profile.full_name, hospitalName: profile.hospital_name },
        });
      })
      .catch(() => {});
  }, []);

  const applySession = useCallback(
    (session) => {
      const claims = decodeJwt(session.access_token);
      if (!claims || isTokenExpired(claims)) {
        clearSession();
        dispatch({ type: "UNAUTHENTICATED" });
        return;
      }

      writeSession(session);
      dispatch({
        type: "AUTHENTICATED",
        user: buildUser(session, claims),
        expiresAt: claims.exp * 1000,
      });
      loadProfile(session);
    },
    [loadProfile]
  );

  const login = useCallback(
    async (email, password) => {
      const data = await apiPost("/auth/login", { email, password });
      applySession({ access_token: data.access_token, email });
    },
    [applySession]
  );

  const logout = useCallback(() => {
    clearSession();
    dispatch({ type: "UNAUTHENTICATED" });
  }, []);

  useEffect(() => {
    setOnAuthExpired(() => dispatch({ type: "UNAUTHENTICATED" }));

    const session = readSession();
    const claims = session ? decodeJwt(session.access_token) : null;

    if (!session || !claims || isTokenExpired(claims)) {
      clearSession();
      dispatch({ type: "UNAUTHENTICATED" });
      return;
    }

    // Paints immediately from whatever name/hospital was cached in
    // storage by a previous loadProfile call (buildUser's `?? null`
    // handles a session with none yet), then refreshes it -- so a reload
    // doesn't flash back to the email/role fallback while /auth/me is
    // in flight.
    dispatch({
      type: "AUTHENTICATED",
      user: buildUser(session, claims),
      expiresAt: claims.exp * 1000,
    });
    loadProfile(session);
  }, [loadProfile]);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}