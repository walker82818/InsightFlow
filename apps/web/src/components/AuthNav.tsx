"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearToken, getStoredUser, type AuthUser } from "@/lib/auth";

export default function AuthNav() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    // 在 hydration 后一次性读取本地登录态，避免刷新时从默认态硬切换造成的闪烁
    setUser(getStoredUser());
    setReady(true);
  }, []);

  function handleLogout() {
    clearToken();
    setUser(null);
    router.push("/");
    router.refresh();
  }

  if (!ready) {
    // 数据未就绪前渲染等宽占位，保持导航高度稳定，避免布局跳动
    return (
      <div className="ml-1 flex items-center gap-2">
        <div className="skeleton h-8 w-16 rounded-lg" />
        <div className="skeleton h-8 w-16 rounded-lg" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="ml-1 flex items-center gap-2">
        <Link
          href="/login"
          className="btn-quiet rounded-lg px-3 py-2 text-sm font-medium"
        >
          登录
        </Link>
        <Link
          href="/login?mode=register"
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:opacity-90"
        >
          注册
        </Link>
      </div>
    );
  }

  return (
    <div className="ml-1 flex items-center gap-2">
      <span className="hidden items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-muted sm:inline-flex">
        <span className="h-2 w-2 rounded-full bg-pine" />
        {user.username}
      </span>
      <button
        onClick={handleLogout}
        className="btn-quiet rounded-lg px-3 py-2 text-sm font-medium"
      >
        退出
      </button>
    </div>
  );
}
