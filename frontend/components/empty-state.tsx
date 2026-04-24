type Props = {
  title: string;
  hint?: string;
};

export function EmptyState({ title, hint }: Props) {
  return (
    <div className="panel-sm text-center py-10">
      <div className="text-ink font-semibold">{title}</div>
      {hint ? <div className="text-sm text-muted mt-2 max-w-md mx-auto">{hint}</div> : null}
    </div>
  );
}
