"use client";

import { FormEvent, useState } from "react";

import { login } from "@/shared/api/client";

type LoginCardProps = {
  onAuthenticated: (token: string) => void;
};

export function LoginCard({ onAuthenticated }: LoginCardProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await login({ email, password });
      onAuthenticated(result.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="login-card" onSubmit={handleSubmit}>
      <p className="eyebrow">Access</p>
      <h2>Sign in to the new control room</h2>
      <label>
        <span>Email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        <span>Password</span>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error ? <p className="error-copy">{error}</p> : null}
      <button type="submit" disabled={loading}>
        {loading ? "Signing in..." : "Sign in"}
      </button>
    </form>
  );
}
