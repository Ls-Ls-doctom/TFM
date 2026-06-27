from __future__ import annotations

import hashlib
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError


class S3Storage:
    def __init__(self, bucket: str, region: str, root_prefix: str = "", run_id: str = "") -> None:
        self.bucket = bucket
        self.root_prefix = root_prefix.strip("/")
        self.run_id = run_id
        self.client = boto3.client("s3", region_name=region)

    def key(self, *parts: str) -> str:
        clean = [part.strip("/") for part in parts if part and part.strip("/")]
        if self.root_prefix:
            clean.insert(0, self.root_prefix)
        return "/".join(clean)

    def sync_directory(self, local_dir: Path, remote_prefix: str, workers: int = 8) -> dict[str, int]:
        if not local_dir.exists():
            return {"files": 0, "uploaded": 0, "skipped": 0, "bytes": 0}

        files = [path for path in local_dir.rglob("*") if path.is_file()]
        summary = {"files": len(files), "uploaded": 0, "skipped": 0, "bytes": 0}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._upload_if_changed, path, local_dir, remote_prefix): path
                for path in files
            }
            for future in as_completed(futures):
                result = future.result()
                summary[result["status"]] += 1
                if result["status"] == "uploaded":
                    summary["bytes"] += result["bytes"]
        return summary

    def _upload_if_changed(self, path: Path, local_root: Path, remote_prefix: str) -> dict[str, int | str]:
        relative = path.relative_to(local_root).as_posix()
        key = self.key(remote_prefix, relative)
        digest = sha256_file(path)
        try:
            remote = self.client.head_object(Bucket=self.bucket, Key=key)
            if remote.get("Metadata", {}).get("sha256") == digest:
                return {"status": "skipped", "bytes": 0}
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in {403, 404}:
                raise

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        metadata = {"sha256": digest}
        if self.run_id:
            metadata["run-id"] = self.run_id
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": metadata,
                "ServerSideEncryption": "AES256",
            },
        )
        return {"status": "uploaded", "bytes": path.stat().st_size}

    def download_prefix(self, remote_prefix: str, local_dir: Path) -> dict[str, int]:
        prefix = self.key(remote_prefix)
        normalized_prefix = prefix.rstrip("/") + "/"
        paginator = self.client.get_paginator("list_objects_v2")
        downloaded = 0
        total_bytes = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=normalized_prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                relative = key[len(normalized_prefix):]
                if not relative:
                    continue
                destination = local_dir / Path(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(self.bucket, key, str(destination))
                downloaded += 1
                total_bytes += int(item.get("Size", 0))
        return {"files": downloaded, "bytes": total_bytes}

    def put_json(self, remote_key: str, payload: Any) -> str:
        key = self.key(remote_key)
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
            Metadata={"run-id": self.run_id} if self.run_id else {},
        )
        return f"s3://{self.bucket}/{key}"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

