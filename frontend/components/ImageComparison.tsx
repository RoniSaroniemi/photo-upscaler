"use client";

import { useState, useCallback, useRef, useEffect } from "react";

interface ImageComparisonProps {
  originalSrc: string;
  upscaledSrc: string;
  originalDimensions?: { width: number; height: number };
  upscaledDimensions?: { width: number; height: number };
}

export default function ImageComparison({
  originalSrc,
  upscaledSrc,
  originalDimensions,
  upscaledDimensions,
}: ImageComparisonProps) {
  const [position, setPosition] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setPosition(pct);
  }, []);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      isDragging.current = true;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      updatePosition(e.clientX);
    },
    [updatePosition]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return;
      updatePosition(e.clientX);
    },
    [updatePosition]
  );

  const handlePointerUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-lg border border-border select-none touch-none"
        style={{ aspectRatio: "auto" }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {/* Upscaled (right / background) */}
        <img
          src={upscaledSrc}
          alt="Upscaled"
          className="block w-full h-auto"
          draggable={false}
        />

        {/* Original (left / clipped overlay) */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ width: `${position}%` }}
        >
          <img
            src={originalSrc}
            alt="Original"
            className="block w-full h-auto"
            style={{ width: containerRef.current?.offsetWidth || "100%" }}
            draggable={false}
          />
        </div>

        {/* Divider */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg"
          style={{ left: `${position}%`, transform: "translateX(-50%)" }}
        >
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow-md flex items-center justify-center">
            <svg
              className="w-4 h-4 text-gray-600"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M8 9l4-4 4 4M8 15l4 4 4-4"
              />
            </svg>
          </div>
        </div>

        {/* Labels */}
        <div className="absolute top-3 left-3 rounded bg-black/60 px-2 py-1 text-xs text-white">
          Original
        </div>
        <div className="absolute top-3 right-3 rounded bg-black/60 px-2 py-1 text-xs text-white">
          Upscaled
        </div>
      </div>

      {/* Dimensions */}
      <div className="flex justify-between text-xs text-muted">
        {originalDimensions && (
          <span>
            Original: {originalDimensions.width} x {originalDimensions.height}
          </span>
        )}
        {upscaledDimensions && (
          <span>
            Upscaled: {upscaledDimensions.width} x {upscaledDimensions.height}
          </span>
        )}
      </div>
    </div>
  );
}
