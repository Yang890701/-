"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { apiJson, configureApiAuth, login as apiLogin, type ApiUser } from "../lib/api";

type AuthContextValue = {
  accessToken: string | null;
  user: ApiUser | null;
  isReady: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setAccessToken: (token: string | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const TOP_NAV_ITEMS = [
  { href: "/", label: "首頁" },
  { href: "/billing", label: "電費作業" },
  { href: "/data", label: "資料檢視" },
  { href: "/audit", label: "稽核" },
] as const;

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<ApiUser | null>(null);
  const [isReady, setIsReady] = useState(false);
  const accessTokenRef = useRef<string | null>(null);
  const router = useRouter();

  const updateAccessToken = useCallback((token: string | null) => {
    accessTokenRef.current = token;
    setAccessToken(token);
  }, []);

  const clearAuth = useCallback(() => {
    updateAccessToken(null);
    setUser(null);
  }, [updateAccessToken]);

  useEffect(() => {
    configureApiAuth({
      getAccessToken: () => accessTokenRef.current,
      setAccessToken: updateAccessToken,
      onUnauthorized: () => {
        clearAuth();
        router.replace("/login");
      },
    });
  }, [clearAuth, router, updateAccessToken]);

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      try {
        const refreshed = await apiJson<{ access_token: string }>("/api/auth/refresh", {
          method: "POST",
        });
        if (cancelled) {
          return;
        }
        updateAccessToken(refreshed.access_token);
        const me = await apiJson<ApiUser>("/api/auth/me");
        if (!cancelled) {
          setUser(me);
        }
      } catch {
        if (!cancelled) {
          clearAuth();
        }
      } finally {
        if (!cancelled) {
          setIsReady(true);
        }
      }
    }
    restoreSession();
    return () => {
      cancelled = true;
    };
  }, [clearAuth, updateAccessToken]);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await apiLogin(username, password);
      updateAccessToken(response.access_token);
      setUser(response.user);
    },
    [updateAccessToken],
  );

  const logout = useCallback(async () => {
    try {
      await apiJson<void>("/api/auth/logout", { method: "POST" });
    } catch {
      // Logout still clears client state if the server session is already gone.
    } finally {
      clearAuth();
      router.replace("/login");
    }
  }, [clearAuth, router]);

  const value = useMemo(
    () => ({ accessToken, user, isReady, login, logout, setAccessToken: updateAccessToken }),
    [accessToken, user, isReady, login, logout, updateAccessToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, isReady, user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (!isReady) {
      return;
    }
    if (!accessToken && !isLogin) {
      router.replace("/login");
    }
    if (accessToken && isLogin) {
      router.replace("/");
    }
  }, [accessToken, isLogin, isReady, router]);

  if (!isReady) {
    return <div className="loading">載入中</div>;
  }

  if (isLogin) {
    return <>{children}</>;
  }

  if (!accessToken) {
    return <div className="loading">請先登入</div>;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <Link className="brand" href="/">
            好室資料入口
          </Link>
          <nav className="topnav" aria-label="主選單">
            {TOP_NAV_ITEMS.map((item) => {
              const isActive =
                item.href === "/" ? pathname === item.href : pathname.startsWith(item.href);
              return (
                <Link
                  className={`topnav-link${isActive ? " topnav-link-active" : ""}`}
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="user-actions">
          <span className="username">{user?.username ?? "使用者"}</span>
          <button className="button button-secondary" type="button" onClick={logout}>
            登出
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
