from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from apisVcloud.s3_storage import S3Storage
from apisVcloud.settings import CloudSettings


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: list[str]
    sync_layers: tuple[str, ...]
    collection_step: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta ISEU Bronze/Silver/Gold en Fargate y persiste en S3.")
    parser.add_argument("--mode", choices=("full", "collect", "transform"), default=None)
    return parser.parse_args()


def build_steps(settings: CloudSettings) -> list[PipelineStep]:
    python = sys.executable
    root = settings.pipeline_root
    collect_steps = [
        PipelineStep("apis", [python, str(root / "APIS" / "run_all.py")], ("bronze", "reports"), True),
        PipelineStep(
            "municipios_catalogos",
            [python, str(root / "APIS" / "municipios" / "run_municipios.py")],
            ("bronze", "reports"),
            True,
        ),
    ]
    if not settings.skip_municipal_resources:
        collect_steps.append(
            PipelineStep(
                "municipios_recursos",
                [
                    python,
                    str(root / "APIS" / "municipios" / "download_recursos.py"),
                    "barcelona",
                    "madrid",
                    "valencia",
                    "sevilla",
                    "bilbao",
                    "malaga",
                    "zaragoza",
                    "--since",
                    str(settings.since_year),
                    "--max-resources",
                    str(settings.municipal_max_resources),
                ],
                ("bronze", "reports"),
                True,
            )
        )

    transform_steps = [
        PipelineStep("inventory_bronze", [python, str(root / "pipeline" / "01_inventory_bronze.py")], ("reports",)),
        PipelineStep("clean_silver", [python, str(root / "pipeline" / "02_clean_silver.py")], ("silver", "reports")),
        PipelineStep("build_gold", [python, str(root / "pipeline" / "03_build_gold.py")], ("gold", "reports")),
        PipelineStep(
            "publish_parquet",
            [python, str(settings.project_root / "apisVcloud" / "publish_cloud.py")],
            ("silver", "gold", "reports"),
        ),
    ]
    if settings.build_sqlite:
        transform_steps.append(
            PipelineStep("build_sqlite", [python, str(root / "pipeline" / "04_build_sqlite.py")], ("gold", "reports"))
        )
    if settings.mode == "collect":
        return collect_steps
    if settings.mode == "transform":
        return transform_steps
    return collect_steps + transform_steps


def run_step(step: PipelineStep, cwd: Path) -> dict[str, object]:
    print(f"\n=== CLOUD STEP: {step.name} ===", flush=True)
    started = time.monotonic()
    completed = subprocess.run(step.command, cwd=cwd, env=os.environ.copy(), check=False)
    duration = round(time.monotonic() - started, 2)
    return {
        "name": step.name,
        "command": step.command,
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "finished_at": utc_now(),
    }


def sync_layers(settings: CloudSettings, storage: S3Storage, layers: tuple[str, ...]) -> dict[str, dict[str, int]]:
    roots = {
        "bronze": settings.pipeline_root / "data_lake" / "bronze",
        "silver": settings.pipeline_root / "data_lake" / "silver",
        "gold": settings.pipeline_root / "data_lake" / "gold",
        "reports": settings.pipeline_root / "reports",
    }
    results = {}
    for layer in dict.fromkeys(layers):
        print(f"Sincronizando {layer}/ con S3...", flush=True)
        results[layer] = storage.sync_directory(roots[layer], layer, settings.upload_workers)
        print(f"  {layer}: {results[layer]}", flush=True)
    return results


def main() -> int:
    args = parse_args()
    settings = CloudSettings.from_env(args.mode)
    storage = S3Storage(settings.bucket, settings.region, settings.prefix, settings.run_id)
    report: dict[str, object] = {
        "run_id": settings.run_id,
        "mode": settings.mode,
        "bucket": settings.bucket,
        "prefix": settings.prefix,
        "started_at": utc_now(),
        "steps": [],
        "status": "RUNNING",
    }

    try:
        if settings.mode == "transform" and settings.download_bronze:
            target = settings.pipeline_root / "data_lake" / "bronze"
            print(f"Descargando s3://{settings.bucket}/{settings.s3_key('bronze')}/", flush=True)
            report["bronze_download"] = storage.download_prefix("bronze", target)

        for step in build_steps(settings):
            result = run_step(step, settings.pipeline_root)
            result["s3_sync"] = sync_layers(settings, storage, step.sync_layers)
            report["steps"].append(result)
            if result["returncode"] != 0:
                can_continue = step.collection_step and settings.continue_on_collect_error
                result["continued_after_error"] = can_continue
                if not can_continue:
                    raise RuntimeError(f"Fallo el paso {step.name} con codigo {result['returncode']}.")

        report["status"] = "OK"
        return_code = 0
    except Exception as error:  # noqa: BLE001
        report["status"] = "ERROR"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        storage.put_json(f"errors/run_id={settings.run_id}/pipeline_error.json", report)
        print(report["traceback"], file=sys.stderr, flush=True)
        return_code = 1
    finally:
        report["finished_at"] = utc_now()
        report_uri = storage.put_json(f"reports/cloud_runs/run_id={settings.run_id}.json", report)
        print(f"Reporte cloud: {report_uri}", flush=True)

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
