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
    QMainWindow, QPushButton, QScrollArea, QSlider, QSpinBox, QStatusBar,
    QTabWidget, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from lrlpr.camera import build_full_pipeline  # noqa: E402
from lrlpr.decode import ScoringModel, slot_tables  # noqa: E402
from lrlpr.pipeline import ParamSpec, Pipeline  # noqa: E402
from lrlpr.plate_spec import SPECS  # noqa: E402

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


def tile_ensemble(arrays: list[np.ndarray], cols: int = 3) -> np.ndarray:
    """Tile equally-shaped draws into a grid with thin separators."""
    tiles = [a if a.ndim == 3 else np.dstack([a] * 3) for a in arrays]
    h, w, _ = tiles[0].shape
    sep = 2
    rows = (len(tiles) + cols - 1) // cols
    grid = np.full((rows * h + (rows - 1) * sep, cols * w + (cols - 1) * sep, 3), 0.25)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y, x = r * (h + sep), c * (w + sep)
        grid[y : y + h, x : x + w] = t[:h, :w]
    return grid


def _text_pixmap(lines: list[tuple[str, tuple[int, int, int]]], scale: int = 2) -> QImage:
    """Render colored monospace lines to a QImage (no external deps)."""
    from PySide6.QtGui import QColor, QFont

    cw, ch = 11 * scale, 20 * scale
    width = cw * max((len(t) for t, _ in lines), default=1) + 12
    height = ch * len(lines) + 12
    img = QImage(width, height, QImage.Format_RGB888)
    img.fill(QColor(18, 18, 18))
    p = QPainter(img)
    f = QFont("Consolas")
    f.setPixelSize(int(15 * scale))
    p.setFont(f)
    for i, (text, rgb) in enumerate(lines):
        p.setPen(QColor(*rgb))
        p.drawText(6, 6 + ch * (i + 1) - 4 * scale, text)
    p.end()
    return img


def decode_heatmap(tables, truth: str) -> QImage:
    """Per-slot posterior heatmap: rows=slots, cells=alphabet, brightness=prob.

    Truth cell outlined green; decoded-argmax cell outlined red when wrong.
    """
    from PySide6.QtGui import QColor

    n = len(tables)
    max_alpha = max(len(t.scores) for t in tables)
    cell = 26
    W, H = max_alpha * cell + 60, n * cell + 24
    img = QImage(W, H, QImage.Format_RGB888)
    img.fill(QColor(18, 18, 18))
    p = QPainter(img)
    from PySide6.QtGui import QFont
    f = QFont("Consolas"); f.setPixelSize(14); p.setFont(f)
    for j, t in enumerate(tables):
        post = t.posterior()
        chars = list(t.scores)
        amax = t.argmax()
        y = 4 + j * cell
        p.setPen(QColor(200, 200, 200))
        p.drawText(2, y + cell - 8, f"{j}")
        for k, chv in enumerate(chars):
            x = 24 + k * cell
            v = int(40 + 215 * post[chv])
            p.fillRect(x, y, cell - 2, cell - 2, QColor(v, v, v))
            p.setPen(QColor(0, 0, 0) if v > 140 else QColor(210, 210, 210))
            p.drawText(x + 6, y + cell - 8, chv)
            if chv == truth[j]:
                p.setPen(QColor(60, 220, 60)); p.drawRect(x, y, cell - 2, cell - 2)
            if chv == amax and amax != truth[j]:
                p.setPen(QColor(230, 60, 60)); p.drawRect(x, y, cell - 2, cell - 2)
    p.end()
    return img


class Worker(QThread):
    """Serialized pipeline runner: always computes the latest requested config."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline: Pipeline):
        super().__init__()
        self.pipeline = pipeline
        self._pending: tuple[dict, str | None] | None = None

    def request(self, overrides: dict, ensemble_tap: str | None = None) -> None:
        self._pending = (overrides, ensemble_tap)
        if not self.isRunning():
            self.start()

    def run(self) -> None:
        while self._pending is not None:
            (job, ensemble_tap), self._pending = self._pending, None
            try:
                state = self.pipeline.run(job)
                if ensemble_tap:
                    draws = []
                    for seed in range(9):
                        ov = {k: dict(v) for k, v in job.items()}
                        ov.setdefault("sensor_noise", {})["seed"] = seed
                        st = self.pipeline.run(ov)
                        arr = st.get(ensemble_tap)
                        if isinstance(arr, np.ndarray):
                            draws.append(np.clip(arr, 0.0, 1.0))
                    if draws:
                        state = dict(state)
                        state["__ensemble__"] = tile_ensemble(draws)
                self.done.emit(state)
            except Exception:
                self.failed.emit(traceback.format_exc(limit=3))


class DecodeWorker(QThread):
    """Oracle-mode decode of the current frame: score every legal char per slot."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline: Pipeline):
        super().__init__()
        self.pipeline = pipeline
        self._job = None

    def request(self, overrides, spec_name, truth, a, b, seed):
        self._job = (overrides, spec_name, truth, a, b, seed)
        if not self.isRunning():
            self.start()

    def run(self):
        while self._job is not None:
            (overrides, spec_name, truth, a, b, seed), self._job = self._job, None
            try:
                spec = SPECS[spec_name]
                truth = spec.validate_string(truth)
                model = ScoringModel(self.pipeline, overrides, frozenset(), a, b)
                y = model.observe(truth, seed)
                tables = slot_tables(model, y, spec, truth)
                decoded = "".join(t.argmax() for t in tables)
                self.done.emit((tables, truth, decoded))
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
        self.ensemble = QCheckBox("seed ensemble 3×3")
        self.ensemble.setToolTip(
            "Tile 9 noise-seed draws of the current tap: the forward model predicts a "
            "DISTRIBUTION over images, not one image — this shows its spread. A real "
            "frame should look like it belongs among the draws, not equal any one of them."
        )
        self.ensemble.toggled.connect(lambda _: self.debounce.start())
        self.tap.currentTextChanged.connect(self._tap_changed)
        self.view = ZoomView()
        self.view.hovered.connect(self.show_pixel)
        image_tab = QWidget()
        rv = QVBoxLayout(image_tab)
        top_row = QWidget()
        tr = QHBoxLayout(top_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.addWidget(self.tap, stretch=1)
        tr.addWidget(self.ensemble)
        rv.addWidget(top_row)
        rv.addWidget(self.view, stretch=1)

        # Decoder tab: oracle-mode per-slot likelihood tables for the current frame.
        self.decode_worker = DecodeWorker(self.pipeline)
        self.decode_worker.done.connect(self.on_decode)
        self.decode_worker.failed.connect(self.on_error)
        decode_tab = QWidget()
        dv = QVBoxLayout(decode_tab)
        drow = QWidget()
        dl = QHBoxLayout(drow)
        dl.setContentsMargins(0, 0, 0, 0)
        self.decode_btn = QPushButton("Decode this frame (oracle)")
        self.decode_btn.setToolTip(
            "Score every legal character in every slot against the current frame, "
            "using the current settings as the known nuisances. Green = truth, "
            "red = wrong argmax. Brightness = posterior probability."
        )
        self.decode_btn.clicked.connect(self.run_decode)
        dl.addWidget(self.decode_btn)
        self.decode_summary = QLabel("Decode not run.")
        dl.addWidget(self.decode_summary, stretch=1)
        dv.addWidget(drow)
        self.decode_view = ZoomView()
        dv.addWidget(self.decode_view, stretch=1)

        self.tabs = QTabWidget()
        self.tabs.addTab(image_tab, "Image")
        self.tabs.addTab(decode_tab, "Decoder")

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.addWidget(scroll)
        rl.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.state: dict | None = None
        self.compute()

    def _changer(self, stage: str):
        def on_change(name: str, value) -> None:
            self.overrides.setdefault(stage, {})[name] = value
            self.debounce.start()
        return on_change

    def _tap_changed(self, _text: str) -> None:
        if self.ensemble.isChecked():
            self.debounce.start()  # ensemble is computed per-tap -> recompute
        else:
            self.refresh_view()

    def compute(self) -> None:
        self.statusBar().showMessage("computing…")
        tap = self.tap.currentText() if self.ensemble.isChecked() else None
        self.worker.request({k: dict(v) for k, v in self.overrides.items()}, tap)

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
        if self.ensemble.isChecked() and "__ensemble__" in self.state:
            self.view.set_image(to_qimage(self.state["__ensemble__"]))
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

    def run_decode(self) -> None:
        ov = {k: dict(v) for k, v in self.overrides.items()}
        surf = ov.get("surface", {})
        truth = surf.get("plate_string", "ABC1D23")
        spec_name = surf.get("spec", "mercosur_br_car")
        noise = ov.get("sensor_noise", {})
        a = noise.get("shot_gain", 0.0)
        b = noise.get("read_var", 0.0)
        seed = int(noise.get("seed", 0))
        self.decode_summary.setText("decoding… (scoring 7 slots × alphabet)")
        self.decode_btn.setEnabled(False)
        self.decode_worker.request(ov, spec_name, truth, a, b, seed)

    def on_decode(self, result) -> None:
        tables, truth, decoded = result
        self.decode_btn.setEnabled(True)
        ok = decoded == truth
        mean_margin = float(np.mean([t.margin() for t in tables]))
        min_conf = min(t.top1_posterior() for t in tables)
        tag = "✓ correct" if ok else f"✗ decoded {decoded}"
        self.decode_summary.setText(
            f"truth {truth} — {tag} | mean margin {mean_margin:.2f} nats | "
            f"weakest slot conf {min_conf:.2f}"
        )
        self.decode_view.set_image(decode_heatmap(tables, truth))
        self.tabs.setCurrentIndex(1)


def main() -> None:
    app = QApplication(sys.argv)
    win = InspectorWindow()
    win.resize(1400, 800)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
