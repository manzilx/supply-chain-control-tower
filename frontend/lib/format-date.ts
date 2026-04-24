export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(d);
}

export function daysFromNow(iso?: string | null): number | null {
  if (!iso) return null;
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const diff = target.getTime() - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round(diff / (1000 * 60 * 60 * 24));
}

export function formatMoney(value?: number | null): string {
  if (value == null) return "—";
  return `$${value.toLocaleString("en", { maximumFractionDigits: 0 })}`;
}
