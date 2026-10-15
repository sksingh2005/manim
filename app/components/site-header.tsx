"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Brand from "./brand";

export default function SiteHeader() {
  const studio = usePathname() === "/studio";
  return (
    <header className="site-header">
      <Brand />
      <nav aria-label="Main navigation">
        <Link className="studio-link" href={studio ? "/" : "/studio"}>
          {studio ? "Back to home" : "Open studio"}
        </Link>
      </nav>
    </header>
  );
}
