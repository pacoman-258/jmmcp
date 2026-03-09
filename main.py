from __future__ import annotations

import os
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Any

from jmcomic import JmOption, create_option_by_file, download_album
from mcp.server.fastmcp import FastMCP


SERVER_NAME = "jmmcp"
DEFAULT_SAVE_DIR = Path("downloads/pdf")
DEFAULT_TEMP_ROOT = Path(".tmp")

mcp = FastMCP(SERVER_NAME)


def _normalize_album_id(album_id: Any) -> tuple[str | None, str | None]:
    value = str(album_id).strip()
    if not value:
        return None, "album_id must not be empty"
    if not value.isdigit():
        return None, "album_id must be a numeric string"
    return value, None


def _resolve_output_dir(save_dir: str | None) -> Path:
    base = Path(save_dir) if save_dir else DEFAULT_SAVE_DIR
    return base.expanduser().resolve()


def _allocate_pdf_path(output_dir: Path, album_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate = output_dir / f"{album_id}.pdf"
    if not candidate.exists():
        return candidate

    index = 1
    while True:
        candidate = output_dir / f"{album_id} ({index}).pdf"
        if not candidate.exists():
            return candidate
        index += 1


def _build_option(job_dir: Path) -> JmOption:
    option_path = os.getenv("JM_OPTION_PATH")
    if option_path and Path(option_path).expanduser().is_file():
        option_dict = create_option_by_file(str(Path(option_path).expanduser())).deconstruct()
    else:
        option_dict = JmOption.default().deconstruct()

    option_dict["log"] = False
    option_dict["dir_rule"] = {
        "rule": "Bd_Aid_Pid",
        "base_dir": str(job_dir),
    }

    plugins = option_dict.setdefault("plugins", {})
    plugins["after_album"] = [
        {
            "plugin": "img2pdf",
            "kwargs": {
                "pdf_dir": str(job_dir),
                "filename_rule": "Aid",
                "delete_original_file": True,
            },
        }
    ]

    return JmOption.construct(option_dict)


def _find_generated_pdf(job_dir: Path) -> Path | None:
    pdf_candidates = [path for path in job_dir.rglob("*.pdf") if path.is_file()]
    if not pdf_candidates:
        return None
    return max(pdf_candidates, key=lambda p: p.stat().st_mtime)


@mcp.tool(
    name="download_jm_album_pdf",
    description=(
        "Download a JM album and convert it to a PDF file. "
        "Example: when user says 'Download album id 350234', "
        "extract album_id=350234 and call this tool."
    ),
)
def download_jm_album_pdf(album_id: str, save_dir: str | None = None) -> dict[str, Any]:
    normalized_id, error = _normalize_album_id(album_id)
    if error:
        return {
            "ok": False,
            "album_id": str(album_id),
            "pdf_path": None,
            "file_size_bytes": None,
            "filename": None,
            "error": error,
            "suggestion": "Use a numeric string, for example: 350234",
        }

    target_dir = _resolve_output_dir(save_dir)

    try:
        temp_root = DEFAULT_TEMP_ROOT.expanduser().resolve()
        temp_root.mkdir(parents=True, exist_ok=True)

        job_dir = (temp_root / f"jm_{normalized_id}_{uuid4().hex}").resolve()
        job_dir.mkdir(parents=True, exist_ok=False)

        try:
            option = _build_option(job_dir)
            download_album(normalized_id, option=option)

            generated_pdf = _find_generated_pdf(job_dir)
            if generated_pdf is None:
                raise RuntimeError("download finished but no generated PDF was found")

            final_pdf_path = _allocate_pdf_path(target_dir, normalized_id)
            shutil.move(str(generated_pdf), str(final_pdf_path))
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

        final_pdf_path = final_pdf_path.resolve()
        return {
            "ok": True,
            "album_id": normalized_id,
            "pdf_path": str(final_pdf_path),
            "file_size_bytes": final_pdf_path.stat().st_size,
            "filename": final_pdf_path.name,
            "error": None,
            "suggestion": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "album_id": normalized_id,
            "pdf_path": None,
            "file_size_bytes": None,
            "filename": None,
            "error": str(exc),
            "suggestion": (
                "If anonymous access is blocked, set JM_OPTION_PATH to a jmcomic "
                "option file with cookies/domain/proxy and retry."
            ),
        }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
