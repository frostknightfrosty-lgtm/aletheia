"""Marker used by the parser-coverage CI pre-flight.

A parser test must decorate exactly the adapter descriptor name it exercises.
The CI checker independently verifies that the marked function actually calls
an adapter's parse method and that every inventory adapter is covered or has
an explicit, reasoned exemption.
"""

from __future__ import annotations


def parser_test(adapter_name: str):
    if not isinstance(adapter_name, str) or not adapter_name.strip():
        raise ValueError("parser_test requires a non-empty adapter descriptor name")

    def decorator(function):
        function.__aletheia_parser_adapter__ = adapter_name
        return function

    return decorator
