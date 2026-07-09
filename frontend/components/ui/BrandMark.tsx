/** The favicon mark: white T on brand blue. Shared by the header and footer. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#0E62D9" />
      <rect x="16" y="17" width="32" height="9" rx="2" fill="#fff" />
      <rect x="27.5" y="17" width="9" height="30" rx="2" fill="#fff" />
    </svg>
  );
}
