"use client";

import { useState, type FormEvent } from "react";
import { API_URL } from "@/shared/lib/api-client";
import { AUTH_STORAGE_KEY } from "./auth-gate";

interface LoginPageProps {
  onLogin: (password: string) => void;
}

/** Full-screen login form that verifies the password against the backend. */
export function LoginPage({ onLogin }: LoginPageProps) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      // Raw fetch is required here because the typed API client reads the
      // password from localStorage, which hasn't been set yet at this point.
      // eslint-disable-next-line no-restricted-globals
      const response = await fetch(`${API_URL}/api/auth/verify`, {
        method: "POST",
        headers: { Authorization: `Bearer ${password}` },
      });

      if (response.ok) {
        localStorage.setItem(AUTH_STORAGE_KEY, password);
        onLogin(password);
      } else {
        setError("Incorrect password");
      }
    } catch {
      setError("Unable to connect to server");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-sm">
        <h1 className="mb-1 text-xl font-semibold text-card-foreground">Schmidt Simulations</h1>
        <p className="mb-6 text-sm text-muted-foreground">Enter the password to continue</p>

        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            className="mb-4 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />

          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={isLoading || password.length === 0}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {isLoading ? "Verifying..." : "Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}
