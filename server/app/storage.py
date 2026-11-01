"""ストレージ抽象。ローカルファイル（開発・テスト）と S3 互換（本番: R2 / S3 / Supabase Storage）。
キーは 'uploads/<id>.mp4', 'jobs/<job>/stages/01_decode.json', 'jobs/<job>/results.json' のような相対パス。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, BinaryIO


class Storage:
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    def put_file(self, key: str, src: Path, content_type: str | None = None) -> None: ...
    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None, max_bytes: int | None = None) -> int: ...
    def get_bytes(self, key: str) -> bytes: ...
    def local_path(self, key: str) -> Path:
        """処理のためにローカルパスが必要な場合（S3 ではダウンロードしてから返す）。"""
        ...
    def exists(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def url_for(self, key: str) -> str: ...
    def presign_upload(self, key: str, content_type: str, expires_s: int = 900) -> dict[str, Any]:
        """署名付きアップロード URL。ローカルでは API 経由の PUT を返す。"""
        ...

    def put_json(self, key: str, obj: Any) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json")

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))


class LocalStorage(Storage):
    def __init__(self, root: Path, public_base: str = "/files"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base = public_base.rstrip("/")

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError("invalid key")
        return p

    def put_bytes(self, key, data, content_type=None):
        p = self._p(key); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)

    def put_file(self, key, src, content_type=None):
        p = self._p(key); p.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, p)

    def put_stream(self, key, stream, content_type=None, max_bytes=None):
        p = self._p(key); p.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(p, "wb") as f:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                n += len(chunk)
                if max_bytes is not None and n > max_bytes:
                    f.close(); p.unlink(missing_ok=True)
                    raise ValueError("upload too large")
                f.write(chunk)
        return n

    def get_bytes(self, key):
        return self._p(key).read_bytes()

    def local_path(self, key):
        return self._p(key)

    def exists(self, key):
        return self._p(key).exists()

    def delete_prefix(self, prefix):
        p = self._p(prefix)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()

    def url_for(self, key):
        return f"{self.public_base}/{key}"

    def presign_upload(self, key, content_type, expires_s=900):
        return {"method": "PUT", "url": f"/api/uploads/{key}", "headers": {"Content-Type": content_type}, "key": key, "expires_in": expires_s}


class S3Storage(Storage):
    """S3 互換（AWS S3 / Cloudflare R2 / Backblaze B2）。boto3 が必要。本番で使う。
    注意: この環境では接続先がないため未検証。"""

    def __init__(self, bucket: str, prefix: str = "", endpoint_url: str | None = None, region: str | None = None, cache_dir: Path | None = None):
        import boto3  # type: ignore

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.cache_dir = Path(cache_dir or "./.s3cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put_bytes(self, key, data, content_type=None):
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=content_type or "application/octet-stream")

    def put_file(self, key, src, content_type=None):
        self.client.upload_file(str(src), self.bucket, self._k(key), ExtraArgs={"ContentType": content_type or "application/octet-stream"})

    def put_stream(self, key, stream, content_type=None, max_bytes=None):
        data = stream.read()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError("upload too large")
        self.put_bytes(key, data, content_type)
        return len(data)

    def get_bytes(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()

    def local_path(self, key):
        p = self.cache_dir / key
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket, self._k(key), str(p))
        return p

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key)); return True
        except Exception:
            return False

    def delete_prefix(self, prefix):
        pag = self.client.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=self.bucket, Prefix=self._k(prefix)):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objs})

    def url_for(self, key):
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self._k(key)}, ExpiresIn=3600)

    def presign_upload(self, key, content_type, expires_s=900):
        url = self.client.generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": self._k(key), "ContentType": content_type}, ExpiresIn=expires_s)
        return {"method": "PUT", "url": url, "headers": {"Content-Type": content_type}, "key": key, "expires_in": expires_s}
