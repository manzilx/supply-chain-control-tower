/** Animated shimmer placeholder. Use in place of "Loading..." text. */
export function Skeleton({
  className = "",
  height,
  width,
}: {
  className?: string;
  height?: number | string;
  width?: number | string;
}) {
  const style: React.CSSProperties = {};
  if (height !== undefined) style.height = typeof height === "number" ? `${height}px` : height;
  if (width !== undefined) style.width = typeof width === "number" ? `${width}px` : width;
  return (
    <div
      className={`rounded bg-white/5 relative overflow-hidden ${className}`}
      style={style}
    >
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="panel space-y-3">
      <Skeleton height={14} width="40%" />
      <Skeleton height={22} width="80%" />
      <Skeleton height={10} width="60%" />
      <div className="grid grid-cols-3 gap-3 pt-2">
        <Skeleton height={36} />
        <Skeleton height={36} />
        <Skeleton height={36} />
      </div>
    </div>
  );
}
