/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Toaster } from "sonner";
import { LanguageProvider } from "@/providers/LanguageProvider";
import { DiagnosisToastListener } from "@/components/diagnosis/DiagnosisToastListener";
import "./globals.css";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "宏革智能测试平台",
  description: "AI 驱动的智能测试系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={plusJakartaSans.className} suppressHydrationWarning>
        <LanguageProvider>
          <NuqsAdapter>{children}</NuqsAdapter>
          <Toaster />
          <DiagnosisToastListener />
        </LanguageProvider>
      </body>
    </html>
  );
}

