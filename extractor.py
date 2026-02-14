"""Extract artifacts from live APIM instance, write as APIOps-format files."""

from datetime import datetime, timezone

from artifacts import DEPLOY_ORDER
from artifact_reader import compute_hash


def extract(client, output_dir, only=None, backend=None, state=None):
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
    all_artifacts = {}

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
        except Exception as e:
            print(f" ERROR: {e}")

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
