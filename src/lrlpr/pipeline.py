"""Stage/Pipeline architecture (design-01 impl. req. 1, design-03).

Every processing step is a Stage: a pure function ``fn(state, params) -> state``
plus a declared parameter schema. The same schema drives library use, ablation
toggles, and the inspection GUI's auto-generated controls. State is an immutable
mapping from string keys to arrays/values; stages return a NEW dict (never mutate).

Caching: Pipeline.run() memoizes per-stage outputs keyed on the effective
parameters of that stage and everything upstream, so changing one parameter
only recomputes from the first affected stage onward (design-03 requirement
for real-time sliders).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ParamSpec:
    """Schema for one stage parameter. GUI controls are generated from this."""

    name: str
    default: Any
    lo: float | None = None  # numeric range (None for bool/str/choice params)
    hi: float | None = None
    step: float | None = None  # slider granularity hint
    scale: str = "linear"  # "linear" | "log" — slider mapping, not math
    units: str = ""
    choices: tuple[str, ...] | None = None  # discrete options (combo box)
    doc: str = ""
    hidden: bool = False  # library-only param (e.g. fitted matrices) — no GUI control

    def validate(self, value: Any) -> Any:
        if self.choices is not None and value not in self.choices:
            raise ValueError(f"{self.name}: {value!r} not in {self.choices}")
        if self.lo is not None and isinstance(value, (int, float)) and value < self.lo:
            raise ValueError(f"{self.name}: {value} < lo={self.lo}")
        if self.hi is not None and isinstance(value, (int, float)) and value > self.hi:
            raise ValueError(f"{self.name}: {value} > hi={self.hi}")
        return value


@dataclass(frozen=True)
class Stage:
    """A pure pipeline step.

    fn must not mutate ``state`` or depend on anything outside (state, params).
    ``provides`` names the state keys this stage adds/replaces (documentation
    and GUI tap labels; not enforced).
    """

    name: str
    fn: Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]
    params: tuple[ParamSpec, ...] = ()
    provides: tuple[str, ...] = ()
    optional: bool = False  # if True, GUI shows an on/off toggle (ablation switch)
    doc: str = ""

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def run(self, state: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
        params = self.defaults()
        for k, v in overrides.items():
            spec = next((p for p in self.params if p.name == k), None)
            if spec is None:
                raise KeyError(f"stage {self.name!r} has no param {k!r}")
            params[k] = spec.validate(v)
        out = dict(state)
        out.update(self.fn(state, MappingProxyType(params)))
        return out


def _freeze(value: Any) -> Any:
    """Hashable cache key for a parameter value."""
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if hasattr(value, "tobytes") and hasattr(value, "shape"):  # ndarray
        return ("ndarray", tuple(value.shape), value.tobytes())
    return value


@dataclass
class Pipeline:
    """Ordered stages with prefix caching.

    run(overrides={stage: {param: value}}, disabled={stage,...}, upto=stage)
    returns the state after the last (or ``upto``) stage. Consecutive calls
    reuse cached per-stage outputs for the unchanged prefix.
    """

    stages: list[Stage]
    _cache_keys: list[Any] = field(default_factory=list, repr=False)
    _cache_states: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def stage_names(self) -> list[str]:
        return [s.name for s in self.stages]

    def schema(self) -> dict[str, tuple[ParamSpec, ...]]:
        return {s.name: s.params for s in self.stages}

    def run(
        self,
        overrides: Mapping[str, Mapping[str, Any]] | None = None,
        disabled: set[str] | None = None,
        upto: str | None = None,
        initial: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        overrides = overrides or {}
        disabled = disabled or set()
        unknown = set(overrides) - set(self.stage_names())
        if unknown:
            raise KeyError(f"overrides for unknown stages: {sorted(unknown)}")
        for name in disabled:
            stage = next(s for s in self.stages if s.name == name)
            if not stage.optional:
                raise ValueError(f"stage {name!r} is not optional; cannot disable")

        state: dict[str, Any] = dict(initial or {})
        prefix_key: Any = None
        use_cache = not initial  # caching only valid for the default (empty) initial state
        for i, stage in enumerate(self.stages):
            stage_over = dict(overrides.get(stage.name, {}))
            key = (prefix_key, stage.name, stage.name in disabled, _freeze(stage_over))
            if use_cache and i < len(self._cache_keys) and self._cache_keys[i] == key:
                state = self._cache_states[i]
            else:
                if stage.name in disabled:
                    state = dict(state)
                else:
                    state = stage.run(state, stage_over)
                if use_cache:
                    del self._cache_keys[i:], self._cache_states[i:]
                    self._cache_keys.append(key)
                    self._cache_states.append(state)
            prefix_key = key
            if stage.name == upto:
                return dict(state)
        if upto is not None:
            raise KeyError(f"unknown stage {upto!r}")
        return dict(state)
