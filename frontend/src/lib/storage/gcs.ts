import { Storage } from "@google-cloud/storage";
import { randomUUID } from "crypto";

const storage = new Storage();
const bucketName = process.env.GCS_BUCKET_NAME!;

export async function uploadResult(
  buffer: Buffer,
  contentType: string
): Promise<{ gcsKey: string }> {
  const gcsKey = `results/${randomUUID()}.webp`;
  const bucket = storage.bucket(bucketName);
  const file = bucket.file(gcsKey);

  await file.save(buffer, {
    contentType,
    resumable: false,
  });

  return { gcsKey };
}

export async function generateSignedUrl(gcsKey: string): Promise<string> {
  const bucket = storage.bucket(bucketName);
  const file = bucket.file(gcsKey);

  const [url] = await file.getSignedUrl({
    version: "v4",
    action: "read",
    expires: Date.now() + 60 * 60 * 1000, // 1 hour
  });

  return url;
}
