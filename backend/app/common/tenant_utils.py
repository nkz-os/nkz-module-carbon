"""Tenant ID normalization — mirrors nkz/services/common/tenant_utils.py"""
import re

MIN_TENANT_ID_LENGTH = 3
MAX_TENANT_ID_LENGTH = 63


def normalize_tenant_id(tenant_id: str) -> str:
    """Normalize tenant ID for consistency across all Nekazari services.

    Rules:
    - Convert to lowercase
    - Replace hyphens with underscores
    - Remove non-alphanumeric/non-underscore chars
    - Strip leading/trailing underscores
    """
    if not tenant_id:
        raise ValueError("Tenant ID cannot be empty")

    normalized = tenant_id.lower().strip()
    normalized = normalized.replace('-', '_')
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    normalized = normalized.strip('_')

    if len(normalized) < MIN_TENANT_ID_LENGTH:
        raise ValueError(f"Tenant ID too short: {normalized}")
    if len(normalized) > MAX_TENANT_ID_LENGTH:
        normalized = normalized[:MAX_TENANT_ID_LENGTH]

    return normalized
