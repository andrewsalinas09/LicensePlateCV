"""Assemble the Phase-1 renderer pipeline (design-01 stages [1]-[3])."""

from __future__ import annotations

from lrlpr.pipeline import Pipeline
from lrlpr.render.project import PROJECT_STAGE
from lrlpr.render.shading import SHADING_STAGE
from lrlpr.render.surface import SURFACE_STAGE


def build_render_pipeline() -> Pipeline:
    return Pipeline([SURFACE_STAGE, SHADING_STAGE, PROJECT_STAGE])
