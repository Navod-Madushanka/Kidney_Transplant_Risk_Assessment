// src/context/AuthProvider.jsx
import { useCallback, useEffect, useReducer } from "react";
import { apiPost, readSession, writeSession, clearSession, setOnAuthExpired } from "../api/client";
import { decodeJwt, isTokenExpired } from "../utils/jwt";
import { AuthContext } from "./AuthContext";

const initialState = { 
  status: "loading", 
  user: null 
};

function reducer(state, action) {
  switch (action.type) {
    case "AUTHENTICATED":
      return { status: "authenticated", user: action.user };
    case "UNAUTHENTICATED":
      return { status: "unauthenticated", user: null };
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

  const applySession = useCallback((session) => {
    const claims = decodeJwt(session.access_token);
    if (!claims || isTokenExpired(claims)) {
      clearSession();
      dispatch({ type: "UNAUTHENTICATED" });
      return;
    }

    writeSession(session);
    dispatch({ type: "AUTHENTICATED", user: buildUser(session, claims) });
  }, []);

  const login = useCallback(
    async (email, password) => {
      const data = await apiPost("/auth/login", { email, password });
      applySession({ access_token: data.access_token, email });
    },
    [applySession]
  );

  const register = useCallback(
    async ({ email, password, fullName, hospitalName }) => {
      const data = await apiPost("/auth/register", {
        email,
        password,
        full_name: fullName,
        hospital_name: hospitalName,
      });
      applySession({
        access_token: data.access_token,
        email,
        full_name: fullName,
        hospital_name: hospitalName,
      });
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

    dispatch({ type: "AUTHENTICATED", user: buildUser(session, claims) });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}