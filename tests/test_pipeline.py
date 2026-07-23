"""Tests for the Stage/Pipeline contract (design-01 req.1, design-03)."""

import pytest

from lrlpr.pipeline import ParamSpec, Pipeline, Stage


def _counting_stage(name, key, calls, optional=False):
    def fn(state, params):
        calls.append(name)
        return {key: state.get(key, 0) + params["inc"]}

    return Stage(
        name=name,
        fn=fn,
        params=(ParamSpec("inc", 1, lo=0, hi=100),),
        provides=(key,),
        optional=optional,
    )


def test_stages_run_in_order_and_accumulate():
    calls = []
    p = Pipeline([_counting_stage("a", "x", calls), _counting_stage("b", "x", calls)])
    out = p.run()
    assert out["x"] == 2
    assert calls == ["a", "b"]


def test_param_override_and_validation():
    calls = []
    p = Pipeline([_counting_stage("a", "x", calls)])
    assert p.run({"a": {"inc": 5}})["x"] == 5
    with pytest.raises(ValueError):
        p.run({"a": {"inc": 999}})  # out of declared range
    with pytest.raises(KeyError):
        p.run({"a": {"nope": 1}})  # undeclared param


def test_prefix_caching_recomputes_only_downstream():
    calls = []
    p = Pipeline(
        [_counting_stage("a", "x", calls), _counting_stage("b", "x", calls),
         _counting_stage("c", "x", calls)]
    )
    p.run()
    calls.clear()
    p.run({"b": {"inc": 7}})  # a unchanged -> cached; b, c recompute
    assert calls == ["b", "c"]
    calls.clear()
    p.run({"b": {"inc": 7}})  # nothing changed -> full cache hit
    assert calls == []


def test_disable_optional_stage():
    calls = []
    p = Pipeline([_counting_stage("a", "x", calls, optional=True)])
    assert p.run(disabled={"a"})== {}
    with pytest.raises(ValueError):
        Pipeline([_counting_stage("m", "x", [], optional=False)]).run(disabled={"m"})


def test_upto_returns_intermediate_state():
    calls = []
    p = Pipeline([_counting_stage("a", "x", calls), _counting_stage("b", "x", calls)])
    assert p.run(upto="a")["x"] == 1


def test_stage_purity_no_mutation():
    def bad_free_rider(state, params):
        return {"y": 1}

    s = Stage("s", bad_free_rider)
    state_in = {"x": 42}
    out = s.run(state_in, {})
    assert state_in == {"x": 42}  # input untouched
    assert out == {"x": 42, "y": 1}  # state flows through
