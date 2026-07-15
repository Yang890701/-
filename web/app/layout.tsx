import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AuthGuard, AuthProvider } from "./providers";

export const metadata: Metadata = {
  title: "好室資料管理",
  description: "好室資料管理前台",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>
        <AuthProvider>
          <AuthGuard>{children}</AuthGuard>
        </AuthProvider>
      </body>
    </html>
  );
}
