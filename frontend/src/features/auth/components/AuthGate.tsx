"use client";

import Link from "next/link";
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
  const [menuOpen, setMenuOpen] = useState(false);

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

  function handleLogout() {
    clearStoredToken();
    setToken(null);
    setUser(null);
    setMenuOpen(false);
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
        <div className="user-menu">
          <button
            className="user-menu-trigger"
            type="button"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span aria-hidden="true">⚙</span>
            <span className="sr-only">Open settings</span>
          </button>
          {menuOpen ? (
            <div className="user-menu-popover" role="menu">
              <Link className="user-menu-item" href="/?tab=profile" role="menuitem" onClick={() => setMenuOpen(false)}>
                Profile
              </Link>
              <button className="user-menu-item" type="button" role="menuitem" onClick={handleLogout}>
                Logout
              </button>
            </div>
          ) : null}
        </div>
      </div>
      {children}
    </>
  );
}
