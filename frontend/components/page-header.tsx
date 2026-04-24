import type { ReactNode } from "react";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  right?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, right }: Props) {
  return (
    <div className="flex items-end justify-between gap-4 mb-5">
      <div>
        {eyebrow ? (
          <div className="text-[0.68rem] uppercase tracking-[0.18em] text-accent font-bold mb-2">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="m-0 text-2xl md:text-3xl font-bold tracking-tight">{title}</h1>
        {description ? (
          <p className="mt-2 text-sm text-muted max-w-2xl leading-relaxed">{description}</p>
        ) : null}
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  );
}
