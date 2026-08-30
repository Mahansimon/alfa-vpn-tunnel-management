"""Adapter تونل BackPack (منبع: Repository گیت)."""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata
from app.tunnel_adapters.repo_based import RepositoryAdapter


class BackPackAdapter(RepositoryAdapter):
    metadata = AdapterMetadata(
        key="backpack",
        display_name="BackPack",
        display_name_fa="بک‌پک",
        source_kind="repository",
        summary_fa="تونل BackPack؛ از Repository نصب یا Build می‌شود.",
        requires=["systemd"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health"],
        env_keys=["BACKPACK_REPOSITORY", "BACKPACK_REF"],
        docs_fa="docs/tunnel-adapters.md#backpack",
    )

    @staticmethod
    def describe() -> AdapterMetadata:
        return BackPackAdapter.metadata
