import {
  PIXEL_RATE_US,
  COMPUTE_RATE_MICRODOLLARS_PER_S,
  PLATFORM_FEE_MICRODOLLARS,
  MAX_INPUT_PX,
} from "@/lib/pricing/cost";

export async function GET() {
  return Response.json({
    pixel_rate_us: PIXEL_RATE_US,
    compute_rate_microdollars_per_s: COMPUTE_RATE_MICRODOLLARS_PER_S,
    platform_fee_microdollars: PLATFORM_FEE_MICRODOLLARS,
    max_input_px: MAX_INPUT_PX,
  });
}
