"""Artifact type registry and deployment order."""

from apy_ops.artifacts import (
    named_values,
    gateways,
    tags,
    version_sets,
    backends,
    loggers,
    diagnostics,
    policy_fragments,
    service_policy,
    products,
    groups,
    apis,
    subscriptions,
    api_policies,
    api_tags,
    api_diagnostics,
    gateway_apis,
    product_policies,
    product_groups,
    product_tags,
    product_apis,
    api_operation_policies,
)

# Ordered list of artifact modules — deployment order for creates/updates.
# Deletions happen in reverse order.
DEPLOY_ORDER = [
    named_values,        # 1
    gateways,            # 2
    tags,                # 3
    version_sets,        # 4
    backends,            # 5
    loggers,             # 6
    diagnostics,         # 7
    policy_fragments,    # 8
    service_policy,      # 9
    products,            # 10
    groups,              # 11
    apis,                # 12
    subscriptions,       # 13
    api_policies,        # 14
    api_tags,            # 15
    api_diagnostics,     # 16
    gateway_apis,        # 17
    product_policies,    # 18
    product_groups,      # 19
    product_tags,        # 20
    product_apis,        # 21
    api_operation_policies,  # 22
]

# Map artifact type name → module
ARTIFACT_TYPES = {mod.ARTIFACT_TYPE: mod for mod in DEPLOY_ORDER}
