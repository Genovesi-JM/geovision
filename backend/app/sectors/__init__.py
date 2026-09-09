"""Sector packages depend on common modules; common modules never depend on sectors."""

from .registry import SECTOR_MODULES, SECTOR_MODULES_BY_NAME

__all__ = ["SECTOR_MODULES", "SECTOR_MODULES_BY_NAME"]
