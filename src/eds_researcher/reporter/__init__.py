"""Report generation for EDS research findings."""

from .delta_report import generate_delta_report
from .full_report import generate_full_report

__all__ = ["generate_delta_report", "generate_full_report"]
