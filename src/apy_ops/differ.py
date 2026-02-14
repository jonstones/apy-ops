"""Diff local artifacts against state to produce a list of changes."""


# Change actions
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
NOOP = "noop"


def diff(local_artifacts, state_artifacts):
    """Compare local artifacts dict against state artifacts dict.

    Both are dict[key, artifact] where artifact has at minimum:
      {"type": str, "id": str, "hash": str, "properties": dict}

    Returns list of change dicts:
      {"action": str, "key": str, "type": str, "id": str,
       "display_name": str, "detail": str,
       "old": artifact|None, "new": artifact|None}
    """
    changes = []

    all_keys = set(local_artifacts.keys()) | set(state_artifacts.keys())

    for key in sorted(all_keys):
        local = local_artifacts.get(key)
        state = state_artifacts.get(key)

        if local and not state:
            changes.append({
                "action": CREATE,
                "key": key,
                "type": local["type"],
                "id": local["id"],
                "display_name": _display_name(local),
                "detail": "new",
                "old": None,
                "new": local,
            })
        elif state and not local:
            changes.append({
                "action": DELETE,
                "key": key,
                "type": state["type"],
                "id": state["id"],
                "display_name": _display_name(state),
                "detail": "removed",
                "old": state,
                "new": None,
            })
        elif local["hash"] != state["hash"]:
            detail = _diff_detail(state.get("properties", {}), local.get("properties", {}))
            changes.append({
                "action": UPDATE,
                "key": key,
                "type": local["type"],
                "id": local["id"],
                "display_name": _display_name(local),
                "detail": detail,
                "old": state,
                "new": local,
            })
        else:
            changes.append({
                "action": NOOP,
                "key": key,
                "type": local["type"],
                "id": local["id"],
                "display_name": _display_name(local),
                "detail": "unchanged",
                "old": state,
                "new": local,
            })

    return changes


def _display_name(artifact):
    """Get a human-readable display name for an artifact."""
    props = artifact.get("properties", {})
    return props.get("displayName") or props.get("name") or artifact.get("id", "")


def _diff_detail(old_props, new_props):
    """Produce a short summary of what changed between two property dicts."""
    changed = []
    all_keys = set(old_props.keys()) | set(new_props.keys())
    for k in sorted(all_keys):
        old_val = old_props.get(k)
        new_val = new_props.get(k)
        if old_val != new_val:
            if old_val is None:
                changed.append(f"added {k}")
            elif new_val is None:
                changed.append(f"removed {k}")
            else:
                # For simple scalar values, show old→new
                if isinstance(old_val, (str, int, float, bool)) and isinstance(new_val, (str, int, float, bool)):
                    changed.append(f"{k} {old_val!r}\u2192{new_val!r}")
                else:
                    changed.append(f"changed {k}")
    if not changed:
        return "changed"
    return ", ".join(changed[:3]) + ("..." if len(changed) > 3 else "")
