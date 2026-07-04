interface StatTileProps {
  value: string;
  label: string;
  detail?: string;
}

export function StatTile({ value, label, detail }: StatTileProps) {
  return (
    <div className="rounded-lg border bg-white p-6 dark:bg-muted">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-[34px] font-semibold leading-none tracking-display">{value}</div>
      {detail && <div className="mt-2 text-[13px] text-muted-foreground">{detail}</div>}
    </div>
  );
}
