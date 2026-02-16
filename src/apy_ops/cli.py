#!/usr/bin/env python3
"""CLI entry point for APIM deployment tool."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from apy_ops.apim_client import ApimClient
from apy_ops.state import get_backend, empty_state
from apy_ops.planner import generate_plan, print_plan, save_plan, load_plan
from apy_ops.applier import apply_plan
from apy_ops.extractor import extract

DEFAULT_STATE_FILE = ".apim-state.json"
DEFAULT_SOURCE_DIR = "."
DEFAULT_OUTPUT_DIR = "./api-management"


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared across subcommands."""
    # State backend
    parser.add_argument("--backend", choices=["local", "azure"],
                        help="State backend type (default: local)")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE,
                        help=f"Path to local state file (default: {DEFAULT_STATE_FILE})")
    parser.add_argument("--backend-storage-account", help="Azure storage account for state")
    parser.add_argument("--backend-container", help="Azure blob container for state")
    parser.add_argument("--backend-blob", help="Azure blob path for state")
    # Auth
    parser.add_argument("--client-id", help="Service principal client ID")
    parser.add_argument("--client-secret", help="Service principal client secret")
    parser.add_argument("--tenant-id", help="Azure AD tenant ID")


def add_apim_args(parser: argparse.ArgumentParser, required: bool = True) -> None:
    """Add APIM target arguments."""
    parser.add_argument("--subscription-id", required=required,
                        help="Azure subscription ID (or APIM_SUBSCRIPTION_ID env var)")
    parser.add_argument("--resource-group", required=required,
                        help="Resource group name (or APIM_RESOURCE_GROUP env var)")
    parser.add_argument("--service-name", required=required,
                        help="APIM service name (or APIM_SERVICE_NAME env var)")


def _resolve_apim_args(args: argparse.Namespace, state: dict[str, Any] | None = None) -> None:
    """Resolve APIM connection args from flags → env vars → state file."""
    args.subscription_id = (
        getattr(args, "subscription_id", None)
        or os.environ.get("APIM_SUBSCRIPTION_ID")
        or (state.get("subscription_id") if state else None)
    )
    args.resource_group = (
        getattr(args, "resource_group", None)
        or os.environ.get("APIM_RESOURCE_GROUP")
        or (state.get("resource_group") if state else None)
    )
    args.service_name = (
        getattr(args, "service_name", None)
        or os.environ.get("APIM_SERVICE_NAME")
        or (state.get("apim_service") if state else None)
    )


def _require_apim_args(args: argparse.Namespace) -> None:
    """Error if APIM connection args are still missing."""
    missing = []
    if not args.subscription_id:
        missing.append("--subscription-id")
    if not args.resource_group:
        missing.append("--resource-group")
    if not args.service_name:
        missing.append("--service-name")
    if missing:
        print(f"Error: {', '.join(missing)} required. "
              "Set via flags, env vars (APIM_SUBSCRIPTION_ID, APIM_RESOURCE_GROUP, "
              "APIM_SERVICE_NAME), or init the state file with these values.",
              file=sys.stderr)
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize an empty state file."""
    backend = get_backend(args)

    # Check if state file already exists
    existing_state = backend.read()
    if existing_state and not args.force:
        print("Error: State file already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    sub_id = getattr(args, "subscription_id", None) or ""
    rg = getattr(args, "resource_group", None) or ""
    svc = getattr(args, "service_name", None) or ""
    state = backend.init(sub_id, rg, svc)
    print(f"Initialized empty state file.")
    if hasattr(args, "state_file") and args.state_file:
        print(f"  Backend: local ({args.state_file})")
    else:
        print(f"  Backend: azure")


def cmd_plan(args: argparse.Namespace) -> None:
    """Generate a plan showing what would change."""
    backend = get_backend(args)
    state = backend.read()
    if state is None:
        print("Error: State file not found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    _resolve_apim_args(args, state)

    only = args.only.split(",") if args.only else None
    source_dir = args.source_dir or DEFAULT_SOURCE_DIR
    plan = generate_plan(
        source_dir, state, only=only,
        subscription_id=args.subscription_id,
        resource_group=args.resource_group,
        service_name=args.service_name,
    )
    print_plan(plan, verbose=args.verbose)

    if args.out:
        save_plan(plan, args.out)

    # Exit with code 2 if there are changes (useful for CI)
    if plan["summary"]["create"] or plan["summary"]["update"] or plan["summary"]["delete"]:
        sys.exit(2)


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply changes to APIM."""
    backend = get_backend(args)
    source_dir = getattr(args, "source_dir", None) or DEFAULT_SOURCE_DIR

    # Load saved plan if provided
    if args.plan:
        plan = load_plan(args.plan)
        # Extract APIM target from plan
        apim = plan.get("apim", {})
        if apim.get("subscription_id") != "NOT-SET":
            args.subscription_id = apim.get("subscription_id")
        if apim.get("resource_group") != "NOT-SET":
            args.resource_group = apim.get("resource_group")
        if apim.get("service_name") != "NOT-SET":
            args.service_name = apim.get("service_name")
    else:
        state = backend.read()
        if state is None:
            print("Error: State file not found. Run 'init' first.", file=sys.stderr)
            sys.exit(1)

        _resolve_apim_args(args, state)
        only = args.only.split(",") if args.only else None

        if args.force:
            _require_apim_args(args)
            client = ApimClient(
                args.subscription_id, args.resource_group, args.service_name,
                args.client_id, args.client_secret, args.tenant_id,
            )
            backend.lock()
            try:
                state = backend.read() or {"artifacts": {}}
                success, total, error = apply_plan(
                    None, client, backend, state,
                    force=True, source_dir=source_dir, only=only,
                )
            finally:
                backend.unlock()
            sys.exit(1 if error else 0)

        plan = generate_plan(
            source_dir, state, only=only,
            subscription_id=args.subscription_id,
            resource_group=args.resource_group,
            service_name=args.service_name,
        )

    # Check if there are changes
    if plan["summary"]["create"] == 0 and plan["summary"]["update"] == 0 and plan["summary"]["delete"] == 0:
        print("\nNo changes. Infrastructure is up-to-date.\n")
        sys.exit(0)

    print_plan(plan)

    # Confirm unless auto-approve
    if not args.auto_approve:
        answer = input("Do you want to apply these changes? (yes/no): ")
        if answer.lower() not in ("yes", "y"):
            print("Apply cancelled.")
            sys.exit(0)

    # Resolve APIM args if not already set from plan
    state = backend.read() if not args.plan else {}
    _resolve_apim_args(args, state if state else None)
    _require_apim_args(args)

    client = ApimClient(
        args.subscription_id, args.resource_group, args.service_name,
        args.client_id, args.client_secret, args.tenant_id,
    )

    backend.lock()
    try:
        state = backend.read() or {"artifacts": {}}
        success, total, error = apply_plan(plan, client, backend, state)
    finally:
        backend.unlock()

    sys.exit(1 if error else 0)


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract artifacts from live APIM."""
    # Try to resolve APIM args from state if available
    state = None
    if args.update_state:
        be = get_backend(args)
        state = be.read()
        _resolve_apim_args(args, state)
    else:
        _resolve_apim_args(args)
    _require_apim_args(args)

    client = ApimClient(
        args.subscription_id, args.resource_group, args.service_name,
        args.client_id, args.client_secret, args.tenant_id,
    )

    only = args.only.split(",") if args.only else None
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR

    backend = None
    if args.update_state:
        backend = get_backend(args)
        if state is None:
            state = empty_state(args.subscription_id, args.resource_group, args.service_name)

    print(f"\nExtracting from {args.service_name}...\n")
    extract(client, output_dir, only=only, backend=backend, state=state)


def cmd_force_unlock(args: argparse.Namespace) -> None:
    """Force-unlock a stuck state file."""
    backend = get_backend(args)
    backend.force_unlock()
    print("Lock released.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Azure APIM deployment tool (Terraform-style plan & apply)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize empty state file")
    add_common_args(p_init)
    p_init.add_argument("--subscription-id", default="", help="Azure subscription ID")
    p_init.add_argument("--resource-group", default="", help="Resource group name")
    p_init.add_argument("--service-name", default="", help="APIM service name")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing state file (use with caution)")

    # plan
    p_plan = subparsers.add_parser("plan", help="Show what would change")
    add_common_args(p_plan)
    add_apim_args(p_plan, required=False)
    p_plan.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR,
                        help=f"Path to APIOps directory (default: {DEFAULT_SOURCE_DIR})")
    p_plan.add_argument("--out", help="Save plan to JSON file")
    p_plan.add_argument("--only", help="Comma-separated list of artifact types")
    p_plan.add_argument("--verbose", "-v", action="store_true",
                        help="Show unchanged artifacts")

    # apply
    p_apply = subparsers.add_parser("apply", help="Apply changes to APIM")
    add_common_args(p_apply)
    add_apim_args(p_apply, required=False)
    p_apply.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR,
                         help=f"Path to APIOps directory (default: {DEFAULT_SOURCE_DIR})")
    p_apply.add_argument("--plan", help="Path to saved plan file")
    p_apply.add_argument("--force", action="store_true",
                         help="Bypass state diff, push ALL artifacts")
    p_apply.add_argument("--auto-approve", action="store_true",
                         help="Skip confirmation prompt")
    p_apply.add_argument("--only", help="Comma-separated list of artifact types")

    # extract
    p_extract = subparsers.add_parser("extract",
                                       help="Extract artifacts from live APIM")
    add_common_args(p_extract)
    add_apim_args(p_extract, required=False)
    p_extract.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                           help=f"Directory to write APIOps files (default: {DEFAULT_OUTPUT_DIR})")
    p_extract.add_argument("--only", help="Comma-separated list of artifact types")
    p_extract.add_argument("--update-state", action="store_true",
                           help="Update state file to match extracted artifacts")

    # force-unlock
    p_unlock = subparsers.add_parser("force-unlock",
                                      help="Force-unlock a stuck state file")
    add_common_args(p_unlock)

    args = parser.parse_args()

    # Validate apply args
    if args.command == "apply":
        if not args.plan and not args.source_dir:
            parser.error("apply requires --source-dir or --plan")

    commands = {
        "init": cmd_init,
        "plan": cmd_plan,
        "apply": cmd_apply,
        "extract": cmd_extract,
        "force-unlock": cmd_force_unlock,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
