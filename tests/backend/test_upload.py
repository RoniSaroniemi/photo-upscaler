import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


def create_test_image(width=100, height=100, fmt="PNG") -> bytes:
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.read()


@pytest.mark.anyio
async def test_upload_accepts_png():
    image_bytes = create_test_image(fmt="PNG")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("completed", "failed", "queued", "processing")


@pytest.mark.anyio
async def test_upload_accepts_jpeg():
    image_bytes = create_test_image(fmt="JPEG")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("test.jpg", image_bytes, "image/jpeg")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data


@pytest.mark.anyio
async def test_upload_rejects_unsupported_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_status_returns_job():
    image_bytes = create_test_image()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        upload_resp = await client.post(
            "/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
        job_id = upload_resp.json()["job_id"]
        status_resp = await client.get(f"/status/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id


@pytest.mark.anyio
async def test_status_404_for_unknown_job():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/status/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_download_completed_job():
    image_bytes = create_test_image()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        upload_resp = await client.post(
            "/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
        data = upload_resp.json()
        if data["status"] == "completed":
            dl_resp = await client.get(f"/download/{data['job_id']}")
            assert dl_resp.status_code == 200
            assert dl_resp.headers["content-type"] == "image/png"


@pytest.mark.anyio
async def test_pricing_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/pricing?width=1920&height=1080")
    assert response.status_code == 200
    data = response.json()
    assert data["scale_factor"] == 4
    assert data["output_dimensions"]["width"] == 1920 * 4
    assert data["cost_breakdown"]["total"] == data["cost_breakdown"]["compute"] + data["cost_breakdown"]["platform_fee"]


@pytest.mark.anyio
async def test_pricing_default_dimensions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/pricing")
    assert response.status_code == 200
    data = response.json()
    assert data["input_dimensions"]["width"] == 1920
    assert data["input_dimensions"]["height"] == 1080
