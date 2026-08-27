"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { login, register, setToken, storeUser } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (searchParams.get("mode") === "register") setMode("register");
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    if (mode === "register" && password.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload =
        mode === "register"
          ? await register(username.trim(), password)
          : await login(username.trim(), password);
      setToken(payload.access_token);
      storeUser(payload.user);
      router.push("/");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "发生未知错误");
    } finally {
      setBusy(false);
    }
  }

  const active = mode === "login";

  return (
    <div className="card p-8">
      <div className="text-center">
        <div className="eyebrow">InsightFlow</div>
        <h1 className="font-display mt-2 text-2xl font-bold text-ink">
          {active ? "登录" : "创建账号"}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {active
            ? "欢迎回来，继续你的数据分析工作"
            : "注册后即可拥有独立的数据与分析空间"}
        </p>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
        <button
          type="button"
          onClick={() => setMode("login")}
          className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
            active ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
          }`}
        >
          登录
        </button>
        <button
          type="button"
          onClick={() => setMode("register")}
          className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
            !active ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
          }`}
        >
          注册
        </button>
      </div>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted">
            用户名
          </label>
          <input
            className="input w-full"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="例如：alice"
            autoComplete="username"
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted">
            密码
          </label>
          <input
            className="input w-full"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={active ? "输入密码" : "至少 6 位"}
            autoComplete={active ? "current-password" : "new-password"}
          />
        </div>

        {error && (
          <div className="rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="btn btn-primary w-full justify-center"
        >
          {busy ? "处理中…" : active ? "登录" : "注册"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-faint">
        不登录也可以{" "}
        <Link href="/" className="text-accent hover:text-accent-strong">
          以访客身份浏览
        </Link>
        ，登录后数据将独立保存。
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col pt-8">
      <Suspense
        fallback={
          <div className="card p-8">
            <div className="skeleton h-6 w-1/2 mx-auto" />
            <div className="skeleton mt-3 h-3 w-2/3 mx-auto" />
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </div>
  );
}
