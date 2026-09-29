"""Optional Cloudflare R2 storage for completed videos."""

from __future__ import annotations

from pathlib import Path

from .config import settings


def enabled() -> bool:
    values = (settings.r2_endpoint_url, settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket)
    if any(values) and not all(values):
        raise RuntimeError("R2 requires endpoint URL, access key ID, secret access key, and bucket.")
    return all(values)


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload(job_id: str, path: Path) -> str | None:
    if not enabled():
        return None
    key = f"videos/{job_id}.mp4"
    _client().upload_file(str(path), settings.r2_bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    return key


def signed_url(key: str) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=settings.video_url_ttl_sec,
    )
