"use client";

import { FormEvent, useState } from "react";

import { login, register } from "@/shared/api/client";

type LoginCardProps = {
  onAuthenticated: (token: string) => void;
};

export function LoginCard({ onAuthenticated }: LoginCardProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const isRegisterMode = mode === "register";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = isRegisterMode
        ? await register({ email, password, full_name: fullName })
        : await login({ email, password });
      onAuthenticated(result.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : isRegisterMode ? "Registration failed" : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  function switchMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setError("");
  }

  return (
    <form className="login-card" onSubmit={handleSubmit}>
      <p className="eyebrow">Access</p>
      <h2>{isRegisterMode ? "Create account" : "Sign in to the new control room"}</h2>
      <div className="auth-mode-switch" role="tablist" aria-label="Auth mode">
        <button
          aria-selected={!isRegisterMode}
          className={!isRegisterMode ? "auth-mode-active" : ""}
          onClick={() => switchMode("login")}
          role="tab"
          type="button"
        >
          Sign in
        </button>
        <button
          aria-selected={isRegisterMode}
          className={isRegisterMode ? "auth-mode-active" : ""}
          onClick={() => switchMode("register")}
          role="tab"
          type="button"
        >
          Create account
        </button>
      </div>
      {isRegisterMode ? (
        <label>
          <span>Name</span>
          <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </label>
      ) : null}
      <label>
        <span>Email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        <span>Password</span>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={isRegisterMode ? 8 : undefined}
        />
      </label>
      {error ? <p className="error-copy">{error}</p> : null}
      <button type="submit" disabled={loading}>
        {loading ? (isRegisterMode ? "Creating account..." : "Signing in...") : isRegisterMode ? "Create account" : "Sign in"}
      </button>
    </form>
  );
}
