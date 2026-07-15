"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../providers";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(username, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="card login-card">
        <h1 className="login-title">好室資料管理</h1>
        <p className="login-subtitle">請使用內部帳號登入</p>
        <form className="login-form" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="username">使用者名稱</label>
            <input
              id="username"
              className="control"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">密碼</label>
            <input
              id="password"
              className="control"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          <button className="button button-primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "登入中" : "登入"}
          </button>
        </form>
        {error ? <div className="error">{error}</div> : null}
      </section>
    </main>
  );
}
