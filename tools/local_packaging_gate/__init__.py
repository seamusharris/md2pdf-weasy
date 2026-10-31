"""Fail-closed local packaging-gate evidence."""

from .gate import run
from .model import GateError, GateRecord, load_record

__all__ = ["GateError", "GateRecord", "load_record", "run"]
