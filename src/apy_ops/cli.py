#!/usr/bin/env python3
"""CLI entry point for APIM deployment tool."""

import argparse
import sys

from apy_ops.apim_client import ApimClient
from apy_ops.state import get_backend, empty_state
from apy_ops.planner import generate_plan, print_plan, save_plan, load_plan
from apy_ops.applier import apply_plan, apply_force
from apy_ops.extractor import extract


def add_common_args(parser):
    """Add arguments shared across subcommands."""
    # State backend
    parser.add_argument("--backend", choices=["local", "azure"],
                        help="State backend type (default: local)")
    parser.add_argument("--state-file", help="Path to local state file")
    parser.add_argument("--backend-storage-account", help="Azure storage account for state")
    parser.add_argument("--backend-container", help="Azure blob container for state")
    parser.add_argument("--backend-blob", help="Azure blob path for state")
    # Auth
    parser.add_argument("--client-id", help="Service principal client ID")
    parser.add_argument("--client-secret", help="Service principal client secret")
    parser.add_argument("--tenant-id", help="Azure AD tenant ID")


def add_apim_args(parser):
    """Add APIM target arguments."""
    parser.add_argument("--subscription-id", required=True, help="Azure subscription ID")
    parser.add_argument("--resource-group", required=True, help="Resource group name")
    parser.add_argument("--service-name", required=True, help="APIM service name")


def cmd_init(args):
    """Initialize an empty state file."""
    backend = get_backend(args)
    sub_id = getattr(args, "subscription_id", None) or ""
    rg = getattr(args, "resource_group", None) or ""
    svc = getattr(args, "service_name", None) or ""
    state = backend.init(sub_id, rg, svc)
    print(f"Initialized empty state file.")
    if hasattr(args, "state_file") and args.state_file:
        print(f"  Backend: local ({args.state_file})")
    else:
        print(f"  Backend: azure")


def cmd_plan(args):
    """Generate a plan showing what would change."""
    backend = get_backend(args)
    state = backend.read()
    if state is None:
        print("Error: State file not found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    only = args.only.split(",") if args.only else None
    plan = generate_plan(args.source_dir, state, only=only)
    print_plan(plan, verbose=args.verbose)

    if args.out:
        save_plan(plan, args.out)

    # Exit with code 2 if there are changes (useful for CI)
    if plan["summary"]["create"] or plan["summary"]["update"] or plan["summary"]["delete"]:
        sys.exit(2)


def cmd_apply(args):
    """Apply changes to APIM."""
    backend = get_backend(args)

    # Load saved plan if provided
    if args.plan:
        plan = load_plan(args.plan)
    else:
        state = backend.read()
        if state is None:
            print("Error: State file not found. Run 'init' first.", file=sys.stderr)
            sys.exit(1)

        only = args.only.split(",") if args.only else None

        if args.force:
            # Force mode: push everything
            client = ApimClient(
                args.subscription_id, args.resource_group, args.service_name,
                args.client_id, args.client_secret, args.tenant_id,
            )
            backend.lock()
            try:
                state = backend.read()
                success, total, errors = apply_force(
                    args.source_dir, client, backend, state, only=only,
                )
            finally:
                backend.unlock()
            sys.exit(1 if errors else 0)

        plan = generate_plan(args.source_dir, state, only=only)

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

    client = ApimClient(
        args.subscription_id, args.resource_group, args.service_name,
        args.client_id, args.client_secret, args.tenant_id,
    )

    backend.lock()
    try:
        # Re-read state under lock
        state = backend.read()
        success, total, error = apply_plan(plan, client, backend, state)
    finally:
        backend.unlock()

    sys.exit(1 if error else 0)


def cmd_extract(args):
    """Extract artifacts from live APIM."""
    client = ApimClient(
        args.subscription_id, args.resource_group, args.service_name,
        args.client_id, args.client_secret, args.tenant_id,
    )

    only = args.only.split(",") if args.only else None

    backend = None
    state = None
    if args.update_state:
        backend = get_backend(args)
        state = backend.read()
        if state is None:
            state = empty_state(args.subscription_id, args.resource_group, args.service_name)

    print(f"\nExtracting from {args.service_name}...\n")
    extract(client, args.output_dir, only=only, backend=backend, state=state)


def cmd_force_unlock(args):
    """Force-unlock a stuck state file."""
    backend = get_backend(args)
    backend.force_unlock()
    print("Lock released.")


def main():
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

    # plan
    p_plan = subparsers.add_parser("plan", help="Show what would change")
    add_common_args(p_plan)
    add_apim_args(p_plan)
    p_plan.add_argument("--source-dir", required=True, help="Path to APIOps directory")
    p_plan.add_argument("--out", help="Save plan to JSON file")
    p_plan.add_argument("--only", help="Comma-separated list of artifact types")
    p_plan.add_argument("--verbose", "-v", action="store_true",
                        help="Show unchanged artifacts")

    # apply
    p_apply = subparsers.add_parser("apply", help="Apply changes to APIM")
    add_common_args(p_apply)
    add_apim_args(p_apply)
    p_apply.add_argument("--source-dir", help="Path to APIOps directory")
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
    add_apim_args(p_extract)
    p_extract.add_argument("--output-dir", required=True,
                           help="Directory to write APIOps files")
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
