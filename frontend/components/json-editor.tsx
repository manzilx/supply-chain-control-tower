type Props = {
  label: string;
  value: string;
  rows?: number;
  onChange: (value: string) => void;
};

export function JsonEditor({ label, value, rows = 10, onChange }: Props) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      <textarea rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
