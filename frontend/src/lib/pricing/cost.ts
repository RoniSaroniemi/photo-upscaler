// Pricing constants
export const PIXEL_RATE_US = 28; // microseconds per input pixel
export const COMPUTE_RATE_MICRODOLLARS_PER_S = 116;
export const PLATFORM_FEE_MICRODOLLARS = 5000;
export const MAX_INPUT_PX = 1024;

export interface CostBreakdown {
  compute_microdollars: number;
  platform_fee_microdollars: number;
  total_microdollars: number;
  processing_seconds: number;
}

/**
 * Estimate cost from image dimensions.
 */
export function estimateCost(width: number, height: number): CostBreakdown {
  const processing_seconds = (width * height * PIXEL_RATE_US) / 1_000_000;
  const compute_microdollars = Math.round(
    processing_seconds * COMPUTE_RATE_MICRODOLLARS_PER_S
  );
  return {
    compute_microdollars,
    platform_fee_microdollars: PLATFORM_FEE_MICRODOLLARS,
    total_microdollars: compute_microdollars + PLATFORM_FEE_MICRODOLLARS,
    processing_seconds,
  };
}

/**
 * Calculate actual cost from real processing time.
 */
export function calculateActualCost(processingTimeMs: number): CostBreakdown {
  const processing_seconds = processingTimeMs / 1000;
  const compute_microdollars = Math.round(
    processing_seconds * COMPUTE_RATE_MICRODOLLARS_PER_S
  );
  return {
    compute_microdollars,
    platform_fee_microdollars: PLATFORM_FEE_MICRODOLLARS,
    total_microdollars: compute_microdollars + PLATFORM_FEE_MICRODOLLARS,
    processing_seconds,
  };
}
