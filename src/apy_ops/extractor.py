"""Extract artifacts from live APIM instance, write as APIOps-format files."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apy_ops.apim_client import ApimClient
from apy_ops.artifacts import DEPLOY_ORDER
from apy_ops.artifact_reader import compute_hash
from apy_ops.exceptions import ApimTransientError, ApimPermanentError


def extract(client: ApimClient, output_dir: str, only: list[str] | None = None,
            backend: Any = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract all artifacts from APIM and write to disk.

    Args:
        client: ApimClient instance
        output_dir: Directory to write APIOps files
        only: Optional list of artifact type names to extract
        backend: Optional state backend (for --update-state)
        state: Optional state dict (for --update-state)

    Returns:
        dict of all extracted artifacts
    """
    all_artifacts: dict[str, Any] = {}

    for mod in DEPLOY_ORDER:
        if only and mod.ARTIFACT_TYPE not in only:
            continue

        type_name = mod.ARTIFACT_TYPE.replace("_", " ")
        print(f"  Extracting {type_name}...", end="", flush=True)

        try:
            artifacts = mod.read_live(client)
            if artifacts:
                mod.write_local(output_dir, artifacts)
                all_artifacts.update(artifacts)
                print(f" {len(artifacts)} found")
            else:
                print(" none")
        except ApimTransientError as e:
            # Transient error — might work on next run
            error_msg = _format_extract_error(e, "Transient")
            print(f" ERROR: {error_msg}")
            print(f"         → May work on next run. Continuing with other artifact types...")
        except ApimPermanentError as e:
            # Permanent error — won't work without fixing the issue
            error_msg = _format_extract_error(e, "Permanent")
            print(f" ERROR: {error_msg}")
            print(f"         → Skipping {type_name}. Fix the issue and re-run extract.")
        except Exception as e:
            # Unexpected error
            print(f" ERROR: {e}")
            print(f"         → Skipping {type_name}. Check logs and re-run extract.")

    print(f"\nExtracted {len(all_artifacts)} artifacts to {output_dir}\n")

    # Optionally update state
    if backend and state is not None:
        state["artifacts"] = {}
        for key, artifact in all_artifacts.items():
            state["artifacts"][key] = {
                "type": artifact["type"],
                "id": artifact["id"],
                "hash": artifact["hash"],
                "properties": artifact["properties"],
            }
        state["last_applied"] = datetime.now(timezone.utc).isoformat()
        backend.write(state)
        print("State file updated to match extracted artifacts.\n")

    return all_artifacts


def _format_extract_error(exc: Exception, error_type: str = "Error") -> str:
    """Format an exception message for extract with error details.

    Args:
        exc: ApimError exception or other exception
        error_type: Type of error (e.g., "Transient", "Permanent")

    Returns:
        Formatted error message with error code and request ID if available
    """
    msg = f"{error_type}"

    if hasattr(exc, "message") and exc.message:
        msg += f": {exc.message}"
    elif str(exc):
        msg += f": {exc}"

    if hasattr(exc, "error_code") and exc.error_code:
        msg += f" [{exc.error_code}]"

    if hasattr(exc, "request_id") and exc.request_id:
        msg += f" (req-id: {exc.request_id})"

    return msg
