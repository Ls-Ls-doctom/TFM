from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


@dataclass(frozen=True)
class CloudSettings:
    bucket: str
    project_root: Path
    pipeline_root: Path
    prefix: str
    region: str
    run_id: str
    mode: str
    since_year: int
    municipal_max_resources: int
    skip_municipal_resources: bool
    continue_on_collect_error: bool
    download_bronze: bool
    build_sqlite: bool
    upload_workers: int

    @classmethod
    def from_env(cls, mode: str | None = None) -> "CloudSettings":
        project_root = Path(os.getenv("ISEU_PROJECT_ROOT", "/app")).resolve()
        pipeline_root = project_root / "api_clients" / "intento 3"
        run_id = os.getenv("ISEU_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        settings = cls(
            bucket=os.getenv("ISEU_BUCKET", "").strip(),
            project_root=project_root,
            pipeline_root=pipeline_root,
            prefix=os.getenv("ISEU_S3_PREFIX", "").strip("/"),
            region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-1")),
            run_id=run_id,
            mode=(mode or os.getenv("ISEU_MODE", "full")).strip().lower(),
            since_year=int(os.getenv("ISEU_SINCE_YEAR", "2010")),
            municipal_max_resources=int(os.getenv("ISEU_MUNICIPAL_MAX_RESOURCES", "80")),
            skip_municipal_resources=env_bool("ISEU_SKIP_MUNICIPAL_RESOURCES", False),
            continue_on_collect_error=env_bool("ISEU_CONTINUE_ON_COLLECT_ERROR", True),
            download_bronze=env_bool("ISEU_DOWNLOAD_BRONZE", True),
            build_sqlite=env_bool("ISEU_BUILD_SQLITE", False),
            upload_workers=max(1, int(os.getenv("ISEU_UPLOAD_WORKERS", "8"))),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.bucket:
            raise ValueError("Falta la variable obligatoria ISEU_BUCKET.")
        if self.mode not in {"full", "collect", "transform"}:
            raise ValueError("ISEU_MODE debe ser full, collect o transform.")
        if not self.pipeline_root.is_dir():
            raise FileNotFoundError(f"No existe el pipeline local: {self.pipeline_root}")

    def s3_key(self, *parts: str) -> str:
        clean = [part.strip("/") for part in parts if part and part.strip("/")]
        if self.prefix:
            clean.insert(0, self.prefix)
        return "/".join(clean)
