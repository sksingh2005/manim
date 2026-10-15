import Link from "next/link";

export default function Brand() {
  return (
    <Link href="/" className="brand" aria-label="Forma home">
      <svg className="brand-mark" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M7 26V12a6 6 0 0 1 6-6h12" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
        <path d="M14 14h10M14 21h5" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
      <span>forma</span>
    </Link>
  );
}
