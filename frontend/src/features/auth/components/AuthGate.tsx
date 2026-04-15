"use client";

import { ReactNode, useEffect, useState } from "react";

import { LoginCard } from "@/features/auth/components/LoginCard";
import { getCurrentUser } from "@/shared/api/client";
import { CurrentUser } from "@/shared/api/types";

type AuthGateProps = {
  children: ReactNode;
};

export function AuthGate({ children }: AuthGateProps) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  function readStoredToken(): string | null {
    try {
      return window.localStorage.getItem("ozon_ads_token");
    } catch {
      return null;
    }
  }

  function writeStoredToken(nextToken: string) {
    try {
      window.localStorage.setItem("ozon_ads_token", nextToken);
    } catch {
      // Ignore storage errors in strict privacy/browser modes.
    }
  }

  function clearStoredToken() {
    try {
      window.localStorage.removeItem("ozon_ads_token");
    } catch {
      // Ignore storage errors in strict privacy/browser modes.
    }
  }

  useEffect(() => {
    const savedToken = readStoredToken();
    if (!savedToken) {
      setLoading(false);
      return;
    }
    setToken(savedToken);
    getCurrentUser(savedToken)
      .then((response) => {
        setUser(response);
      })
      .catch(() => {
        clearStoredToken();
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  function handleAuthenticated(nextToken: string) {
    writeStoredToken(nextToken);
    setToken(nextToken);
    setLoading(true);
    getCurrentUser(nextToken)
      .then((response) => {
        setUser(response);
      })
      .finally(() => {
        setLoading(false);
      });
  }

  if (loading) {
    return (
      <div className="loading-card skeleton-card" aria-busy="true" aria-live="polite">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-line" />
      </div>
    );
  }

  if (!token || !user) {
    return <LoginCard onAuthenticated={handleAuthenticated} />;
  }

  return (
    <>
      <div className="session-bar">
        <span>{user.full_name || user.email}</span>
        <span>{user.is_admin ? "admin" : "member"}</span>
      </div>
      {children}
    </>
  );
}
