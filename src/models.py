"""
Data models for options chain representation.

This module re-exports from the models package for backward compatibility.
New code should import directly from src.models package.
"""

# Re-export all models from the new package structure
from .models.base import OptionContract, OptionsChain

__all__ = [
    "OptionContract",
    "OptionsChain",
]
