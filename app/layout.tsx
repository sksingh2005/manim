import type { Metadata } from "next";
import "./globals.css";
import SiteHeader from "@/app/components/site-header";
import localFont from "next/font/local";

const geist = localFont({ src: "../public/fonts/geist-latin.woff2", display: "swap", variable: "--font-forma", weight: "100 900" });

export const metadata: Metadata = {
  title: { default: "Forma | Ideas, made visible", template: "%s | Forma" },
  description: "Turn an idea into a short explanatory animation with Forma.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={geist.variable}>
      <body><SiteHeader />{children}</body>
    </html>
  );
}
