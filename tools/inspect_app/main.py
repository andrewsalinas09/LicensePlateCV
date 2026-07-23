"""LRLPR pipeline inspection app (design-03).

A thin reflective viewer over the real library pipeline: parameter controls are
auto-generated from each Stage's ParamSpec schema, so what you inspect IS what
the decoder will use. Sliders recompute live (debounced, worker thread, prefix
caching in the Pipeline keeps it fast).

Run:  uv run --group tools python tools/inspect_app/main.py
"""

from __future__ import annotations

import os
import sys
import traceback

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QGraphicsPixmapItem,
    QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QScrollArea, QSlider, QSpinBox, QStatusBar, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from lrlpr.camera import build_full_pipeline  # noqa: E402
from lrlpr.pipeline import ParamSpec, Pipeline  # noqa: E402

FALLBACK_FONTS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "fonts",
                 "GL-Nummernschild-Eng.ttf"),
    r"C:\Windows\Fonts\arialbd.ttf",
]

# Preferred display order for known taps; unknown image-like keys are appended.
VIEW_ORDER = [
    "albedo", "height_mm", "char_mask", "shading", "radiance", "image",
    "image_motion", "image_optics", "sensor_rgb", "raw_mosaic", "raw_noisy",
    "demosaiced", "isp_image", "delivered", "decoded",
]


def viewable_keys(state: dict) -> list[str]:
    def is_img(v) -> bool:
        return isinstance(v, np.ndarray) and v.ndim in (2, 3) and v.size > 16

    known = [k for k in VIEW_ORDER if is_img(state.get(k))]
    extra = sorted(k for k, v in state.items() if is_img(v) and k not in VIEW_ORDER
                   and k != "current")
    return known + extra


def to_qimage(arr: np.ndarray) -> QImage:
    """Linear float array (H,W) or (H,W,3) -> displayable 8-bit QImage.

    PROVISIONAL display transform: simple gamma 1/2.2 for color images;
    single-channel maps are normalized to their max (inspection, not science).
    """
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        a = a / a.max() if a.max() > 0 else a
        a = np.dstack([a] * 3)
    else:
        a = np.clip(a, 0.0, 1.0) ** (1 / 2.2)
    a8 = np.ascontiguousarray((a * 255).astype(np.uint8))
    h, w, _ = a8.shape
    return QImage(a8.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class Worker(QThread):
    """Serialized pipeline runner: always computes the latest requested config."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline: Pipeline):
        super().__init__()
        self.pipeline = pipeline
        self._pending: dict | None = None

    def request(self, overrides: dict) -> None:
        self._pending = overrides
        if not self.isRunning():
            self.start()

    def run(self) -> None:
        while self._pending is not None:
            job, self._pending = self._pending, None
            try:
                state = self.pipeline.run(job)
                self.done.emit(state)
            except Exception:
                self.failed.emit(traceback.format_exc(limit=3))


class ZoomView(QGraphicsView):
    """Pixel-inspectable image view: wheel zoom, nearest-neighbor at high zoom."""

    hovered = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)  # keep a reference (Qt ownership)
        self.setScene(self._scene)
        self.item = QGraphicsPixmapItem()
        self._scene.addItem(self.item)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def set_image(self, qimg: QImage) -> None:
        self.item.setPixmap(QPixmap.fromImage(qimg))

    def wheelEvent(self, ev) -> None:
        factor = 1.25 if ev.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def mouseMoveEvent(self, ev) -> None:
        p = self.mapToScene(ev.position().toPoint())
        self.hovered.emit(int(p.x()), int(p.y()))
        super().mouseMoveEvent(ev)


def make_control(spec: ParamSpec, on_change) -> QWidget:
    """Auto-generate the right control for a ParamSpec (design-03)."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    label = QLabel(spec.name + (f" [{spec.units}]" if spec.units else ""))
    label.setToolTip(spec.doc)
    label.setMinimumWidth(130)
    lay.addWidget(label)

    if spec.choices is not None:
        box = QComboBox()
        box.addItems(spec.choices)
        box.setCurrentText(str(spec.default))
        box.currentTextChanged.connect(lambda v: on_change(spec.name, v))
        lay.addWidget(box)
    elif isinstance(spec.default, bool):
        cb = QCheckBox()
        cb.setChecked(spec.default)
        cb.toggled.connect(lambda v: on_change(spec.name, bool(v)))
        lay.addWidget(cb)
    elif isinstance(spec.default, (int, float)) and spec.lo is not None:
        is_int = isinstance(spec.default, int)
        step = spec.step or (1 if is_int else (spec.hi - spec.lo) / 100)
        slider = QSlider(Qt.Horizontal)
        n_steps = int(round((spec.hi - spec.lo) / step))
        slider.setRange(0, n_steps)
        slider.setValue(int(round((spec.default - spec.lo) / step)))
        spin = QSpinBox() if is_int else QDoubleSpinBox()
        spin.setRange(spec.lo, spec.hi)
        if not is_int:
            spin.setDecimals(3)
            spin.setSingleStep(step)
        spin.setValue(spec.default)

        def from_slider(tick: int) -> None:
            v = spec.lo + tick * step
            v = int(round(v)) if is_int else round(v, 6)
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)
            on_change(spec.name, v)

        def from_spin(v) -> None:
            slider.blockSignals(True)
            slider.setValue(int(round((v - spec.lo) / step)))
            slider.blockSignals(False)
            on_change(spec.name, int(v) if is_int else float(v))

        slider.valueChanged.connect(from_slider)
        spin.valueChanged.connect(from_spin)
        lay.addWidget(slider, stretch=1)
        lay.addWidget(spin)
    else:  # free text (e.g. plate_string, font_path)
        edit = QLineEdit(str(spec.default))
        edit.editingFinished.connect(lambda: on_change(spec.name, edit.text()))
        lay.addWidget(edit)
    return row


class InspectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LRLPR Pipeline Inspector — design-01 stages [1]-[11]")
        self.pipeline = build_full_pipeline()
        self.overrides: dict[str, dict] = {}
        font = next((f for f in FALLBACK_FONTS if os.path.exists(f)), None)
        if font:
            self.overrides["surface"] = {"font_path": os.path.abspath(font)}

        self.worker = Worker(self.pipeline)
        self.worker.done.connect(self.on_result)
        self.worker.failed.connect(self.on_error)
        self.debounce = QTimer(self, singleShot=True, interval=120)
        self.debounce.timeout.connect(self.compute)

        # Left: auto-generated parameter panel.
        panel = QWidget()
        pv = QVBoxLayout(panel)
        for stage in self.pipeline.stages:
            box = QGroupBox(f"[{stage.name}] {stage.doc}")
            bv = QVBoxLayout(box)
            for spec in stage.params:
                if spec.name == "font_path" and font:
                    spec = ParamSpec(**{**spec.__dict__, "default": os.path.abspath(font)})
                bv.addWidget(make_control(spec, self._changer(stage.name)))
            pv.addWidget(box)
        pv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(430)

        # Right: stage-tap selector + zoomable view (repopulated per result).
        self.tap = QComboBox()
        self.tap.addItems(VIEW_ORDER)
        self.tap.setCurrentText("decoded")
        self.tap.currentTextChanged.connect(lambda _: self.refresh_view())
        self.view = ZoomView()
        self.view.hovered.connect(self.show_pixel)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(self.tap)
        rv.addWidget(self.view, stretch=1)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.addWidget(scroll)
        rl.addWidget(right, stretch=1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.state: dict | None = None
        self.compute()

    def _changer(self, stage: str):
        def on_change(name: str, value) -> None:
            self.overrides.setdefault(stage, {})[name] = value
            self.debounce.start()
        return on_change

    def compute(self) -> None:
        self.statusBar().showMessage("computing…")
        self.worker.request({k: dict(v) for k, v in self.overrides.items()})

    def on_result(self, state: dict) -> None:
        self.state = state
        dist = state.get("camera_distance_m")
        msg = f"ok — camera at {dist:.1f} m" if dist else "ok"
        self.statusBar().showMessage(msg)
        current = self.tap.currentText()
        keys = viewable_keys(state)
        self.tap.blockSignals(True)
        self.tap.clear()
        self.tap.addItems(keys)
        self.tap.setCurrentText(current if current in keys else keys[-1])
        self.tap.blockSignals(False)
        self.refresh_view()

    def on_error(self, tb: str) -> None:
        self.statusBar().showMessage(tb.strip().splitlines()[-1])

    def refresh_view(self) -> None:
        if self.state is None:
            return
        key = self.tap.currentText()
        if key in self.state:
            self.view.set_image(to_qimage(self.state[key]))

    def show_pixel(self, x: int, y: int) -> None:
        if self.state is None:
            return
        arr = self.state.get(self.tap.currentText())
        if arr is not None and 0 <= y < arr.shape[0] and 0 <= x < arr.shape[1]:
            val = np.round(np.atleast_1d(arr[y, x]), 4)
            dist = self.state.get("camera_distance_m")
            extra = f" — camera {dist:.1f} m" if dist else ""
            self.statusBar().showMessage(f"({x}, {y}) = {val}{extra}")


def main() -> None:
    app = QApplication(sys.argv)
    win = InspectorWindow()
    win.resize(1400, 800)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
