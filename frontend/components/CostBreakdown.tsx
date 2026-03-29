"use client";

interface CostBreakdownProps {
  computeCost: number;
  platformFee: number;
  total: number;
  compact?: boolean;
}

export default function CostBreakdown({
  computeCost,
  platformFee,
  total,
  compact = false,
}: CostBreakdownProps) {
  const fmt = (n: number) => `$${n.toFixed(2)}`;

  if (compact) {
    return (
      <div className="text-sm text-muted">
        Estimated cost: <span className="font-medium text-foreground">{fmt(total)}</span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-5 font-mono text-sm">
      <div className="flex justify-between py-1">
        <span className="text-muted">Compute cost</span>
        <span>{fmt(computeCost)}</span>
      </div>
      <div className="flex justify-between py-1">
        <span className="text-muted">Platform fee</span>
        <span>{fmt(platformFee)}</span>
      </div>
      <div className="my-2 border-t border-border" />
      <div className="flex justify-between py-1 font-semibold">
        <span>Total</span>
        <span>{fmt(total)}</span>
      </div>
      <p className="mt-3 text-xs text-muted font-sans">
        We run Real-ESRGAN ourselves. No middleman markup.
      </p>
    </div>
  );
}
