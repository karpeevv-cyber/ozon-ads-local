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

  useEffect(() => {
    const savedToken = window.localStorage.getItem("ozon_ads_token");
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
        window.localStorage.removeItem("ozon_ads_token");
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  function handleAuthenticated(nextToken: string) {
    window.localStorage.setItem("ozon_ads_token", nextToken);
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
    return <div className="loading-card">Checking access...</div>;
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
