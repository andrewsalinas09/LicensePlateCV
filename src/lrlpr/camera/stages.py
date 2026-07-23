"""Assemble the full design-01 pipeline: renderer [1]-[3] + camera [4]-[11]."""

from __future__ import annotations

from lrlpr.camera.delivery import CODEC_STAGE, RESAMPLE_STAGE
from lrlpr.camera.demosaic import DEMOSAIC_STAGE
from lrlpr.camera.isp import ISP_STAGE
from lrlpr.camera.motion import MOTION_STAGE
from lrlpr.camera.optics import OPTICS_STAGE
from lrlpr.camera.sensor import NOISE_STAGE, SENSOR_STAGE
from lrlpr.pipeline import Pipeline
from lrlpr.render.project import PROJECT_STAGE
from lrlpr.render.shading import SHADING_STAGE
from lrlpr.render.surface import SURFACE_STAGE


def build_full_pipeline() -> Pipeline:
    return Pipeline(
        [
            SURFACE_STAGE,      # [1]
            SHADING_STAGE,      # [2]
            PROJECT_STAGE,      # [3]
            MOTION_STAGE,       # [4]
            OPTICS_STAGE,       # [5]
            SENSOR_STAGE,       # [6]
            NOISE_STAGE,        # [7]
            DEMOSAIC_STAGE,     # [8]
            ISP_STAGE,          # [9]
            RESAMPLE_STAGE,     # [10]
            CODEC_STAGE,        # [11]
        ]
    )
