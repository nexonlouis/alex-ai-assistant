"""
Cortex module - Intelligence layer for Alex AI Assistant.

Implements the Dual-Cortex architecture:
- Flash: Fast, cost-effective responses (Basal Cortex)
- Pro: Deep reasoning for complex tasks (Executive Cortex)
"""

from alex.cortex.flash import get_flash_model
from alex.cortex.pro import get_pro_model
from alex.cortex.router import route_to_cortex

__all__ = ["get_flash_model", "get_pro_model", "route_to_cortex"]
