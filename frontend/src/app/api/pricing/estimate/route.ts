import {
  estimateCost,
  MAX_INPUT_PX,
} from "@/lib/pricing/cost";
import { formatMicrodollars } from "@/lib/pricing/format";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const widthStr = searchParams.get("width");
  const heightStr = searchParams.get("height");

  if (!widthStr || !heightStr) {
    return Response.json(
      { error: "width and height query parameters are required" },
      { status: 400 }
    );
  }

  const width = parseInt(widthStr, 10);
  const height = parseInt(heightStr, 10);

  if (isNaN(width) || isNaN(height) || width <= 0 || height <= 0) {
    return Response.json(
      { error: "width and height must be positive integers" },
      { status: 400 }
    );
  }

  if (width > MAX_INPUT_PX || height > MAX_INPUT_PX) {
    return Response.json(
      {
        error: `Dimensions exceed maximum of ${MAX_INPUT_PX}px per side`,
        max_input_px: MAX_INPUT_PX,
      },
      { status: 400 }
    );
  }

  const costBreakdown = estimateCost(width, height);

  return Response.json({
    input_pixels: width * height,
    estimated_processing_seconds: costBreakdown.processing_seconds,
    cost_breakdown: costBreakdown,
    formatted_total: formatMicrodollars(
      BigInt(costBreakdown.total_microdollars)
    ),
    max_input_px: MAX_INPUT_PX,
  });
}
