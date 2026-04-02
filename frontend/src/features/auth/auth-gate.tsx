"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { API_URL } from "@/shared/lib/api-client";
import { LoginPage } from "./login-page";

export const AUTH_STORAGE_KEY = "app_password";

type AuthState = "loading" | "authenticated" | "unauthenticated";

/**
 * Gate that wraps the app and requires password authentication.
 *
 * Checks localStorage for a stored password. If none is found, probes the
 * backend to detect whether auth is disabled (APP_PASSWORD unset). Shows a
 * login page when authentication is required.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>("loading");

  useEffect(() => {
    // Always call the verify endpoint to check auth status. If a stored
    // password exists, include it as a Bearer token. This also validates that
    // previously stored passwords are still accepted by the server.
    const stored = localStorage.getItem(AUTH_STORAGE_KEY);
    const headers: Record<string, string> = {};
    if (stored) {
      headers["Authorization"] = `Bearer ${stored}`;
    }

    // eslint-disable-next-line no-restricted-globals
    fetch(`${API_URL}/api/auth/verify`, { method: "POST", headers })
      .then(res => {
        if (res.ok) {
          setAuthState("authenticated");
        } else {
          localStorage.removeItem(AUTH_STORAGE_KEY);
          setAuthState("unauthenticated");
        }
      })
      .catch(() => {
        setAuthState("unauthenticated");
      });
  }, []);

  const handleLogin = useCallback((password: string) => {
    localStorage.setItem(AUTH_STORAGE_KEY, password);
    setAuthState("authenticated");
  }, []);

  if (authState === "loading") {
    return null;
  }

  if (authState === "unauthenticated") {
    return <LoginPage onLogin={handleLogin} />;
  }

  return <>{children}</>;
}
