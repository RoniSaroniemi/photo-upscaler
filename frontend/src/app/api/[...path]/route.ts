import { NextResponse } from "next/server";

function notFoundResponse(request: Request) {
  const url = new URL(request.url);
  return NextResponse.json(
    { error: "Not found", path: url.pathname },
    { status: 404 }
  );
}

export async function GET(request: Request) {
  return notFoundResponse(request);
}

export async function POST(request: Request) {
  return notFoundResponse(request);
}

export async function PUT(request: Request) {
  return notFoundResponse(request);
}

export async function PATCH(request: Request) {
  return notFoundResponse(request);
}

export async function DELETE(request: Request) {
  return notFoundResponse(request);
}
