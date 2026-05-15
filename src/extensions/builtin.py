# -*- coding: utf-8 -*-
"""Built-in Extension Runtime declarations."""

from __future__ import annotations

from typing import Any, Dict

from src.extensions.actions import ActionContext, ActionDefinition, ActionMode
from src.extensions.registry import ExtensionRegistry, PluginDefinition, PluginStatus
from src.extensions.runtime import ExtensionRuntime


def _require(payload: Dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _pending(status: str, *, dry_run: bool) -> Dict[str, Any]:
    return {
        "status": "validated" if dry_run else status,
        "dry_run": dry_run,
        "degradation": {
            "code": "adapter_not_bound",
            "message": "Action is declared; service binding is planned for a later phase.",
        },
    }


def _handle_analyze_stock(payload: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
    return {
        **_pending("adapter_pending", dry_run=context.dry_run),
        "stock_code": _require(payload, "stock_code"),
        "report_type": payload.get("report_type", "detailed"),
    }


def _handle_notification_send(payload: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
    return {**_pending("adapter_pending", dry_run=context.dry_run), "channel": payload.get("channel", "default")}


def _handle_stock_pool_import(payload: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
    if "items" not in payload or payload.get("items") is None:
        raise ValueError("items is required")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    return {**_pending("adapter_pending", dry_run=context.dry_run), "items_count": len(items)}


def get_builtin_actions() -> list[ActionDefinition]:
    return [
        ActionDefinition(
            action_id="dsa.analyze_stock",
            plugin_id="dsa-core",
            description="Run DSA stock analysis through the shared Action Runtime.",
            handler=_handle_analyze_stock,
            input_schema={
                "type": "object",
                "required": ["stock_code"],
                "properties": {
                    "stock_code": {"type": "string"},
                    "report_type": {"type": "string"},
                },
            },
            mode=ActionMode.ASYNC,
            permissions=["analysis.run"],
            timeout_seconds=300,
            category="analysis",
            subject_key="stock_code",
        ),
        ActionDefinition(
            action_id="notification.send",
            plugin_id="dsa-core",
            description="Send a notification through the existing notification gateway.",
            handler=_handle_notification_send,
            input_schema={"type": "object"},
            permissions=["notification.send"],
            requires_confirmation=True,
            category="notification",
        ),
        ActionDefinition(
            action_id="stock_pool.import",
            plugin_id="dsa-core",
            description="Import candidates into a DSA stock pool or watchlist.",
            handler=_handle_stock_pool_import,
            input_schema={"type": "object", "required": ["items"], "properties": {"items": {"type": "array"}}},
            permissions=["stock_pool.write"],
            requires_confirmation=True,
            category="portfolio",
        ),
    ]


def create_builtin_extension_registry() -> ExtensionRegistry:
    registry = ExtensionRegistry()
    registry.register_plugin(
        PluginDefinition(
            plugin_id="dsa-core",
            name="DSA Core Actions",
            description="Built-in Action declarations shared by DSA entrypoints.",
            status=PluginStatus.ENABLED,
            version="mvp",
        )
    )
    registry.register_actions(get_builtin_actions())
    return registry


def create_builtin_extension_runtime() -> ExtensionRuntime:
    return ExtensionRuntime(registry=create_builtin_extension_registry())
