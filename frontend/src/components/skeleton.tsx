export function Skeleton({
  className = "",
  width,
  height,
}: {
  className?: string;
  width?: string | number;
  height?: string | number;
}) {
  return (
    <div
      className={`rounded-lg ${className}`}
      style={{
        width: width || "100%",
        height: height || "1rem",
        background:
          "linear-gradient(90deg, rgba(100,116,139,0.08) 25%, rgba(100,116,139,0.15) 50%, rgba(100,116,139,0.08) 75%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.5s infinite",
      }}
    />
  );
}

export function SquawkSkeleton() {
  return (
    <div className="p-4 rounded-xl space-y-3" style={{ border: "1px solid var(--border-glass)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton width={48} height={16} />
          <Skeleton width={40} height={16} />
          <Skeleton width={36} height={16} />
        </div>
        <Skeleton width={24} height={12} />
      </div>
      <Skeleton height={14} />
      <Skeleton width="80%" height={12} />
      <div className="flex items-center justify-between pt-1">
        <Skeleton width={28} height={28} className="rounded-full" />
        <Skeleton width={48} height={12} />
      </div>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="px-5 py-4 flex items-center gap-4">
      <Skeleton width={32} height={32} className="rounded-lg flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton height={14} width="60%" />
        <Skeleton height={11} width="40%" />
      </div>
      <Skeleton width={48} height={14} />
    </div>
  );
}
