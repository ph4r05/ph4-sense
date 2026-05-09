"""Tests for ph4ha/apps/blinds_policy.py — the declarative blinds policy engine."""

from __future__ import annotations

import os

import pytest
import yaml
from blinds_policy import Action, BlindsPolicy, PolicyError, eval_expr

# ---------------------------------------------------------------------------
# eval_expr
# ---------------------------------------------------------------------------


class TestEvalExpr:
    def test_none_and_empty_are_truthy(self):
        assert eval_expr(None, {}) is True
        assert eval_expr("", {}) is True
        assert eval_expr("   ", {}) is True

    def test_basic_boolean_logic(self):
        assert eval_expr("a and b", {"a": True, "b": True}) is True
        assert eval_expr("a and b", {"a": True, "b": False}) is False
        assert eval_expr("a or b", {"a": False, "b": True}) is True
        assert eval_expr("not a", {"a": False}) is True
        assert eval_expr("not a", {"a": True}) is False

    def test_comparisons(self):
        assert eval_expr("x == 5", {"x": 5}) is True
        assert eval_expr("x != 5", {"x": 5}) is False
        assert eval_expr("x < 10", {"x": 5}) is True
        assert eval_expr("x >= 5", {"x": 5}) is True
        assert eval_expr("a in xs", {"a": 1, "xs": [1, 2, 3]}) is True
        assert eval_expr("a not in xs", {"a": 0, "xs": [1, 2, 3]}) is True

    def test_short_circuit(self):
        # If short-circuit failed, looking up `b` would raise.
        assert eval_expr("a or b", {"a": True}) is True
        assert eval_expr("a and b", {"a": False}) is False

    def test_compound_expression(self):
        ctx = {"guest_mode": False, "winter_mode": True, "early": False}
        assert eval_expr("not guest_mode and (winter_mode or early)", ctx) is True

    def test_unknown_identifier_raises(self):
        with pytest.raises(PolicyError, match="Unknown identifier"):
            eval_expr("missing", {})

    def test_function_calls_rejected(self):
        with pytest.raises(PolicyError, match="Disallowed expression"):
            eval_expr("foo()", {})

    def test_attribute_access_rejected(self):
        with pytest.raises(PolicyError, match="Disallowed expression"):
            eval_expr("a.b", {"a": object()})

    def test_arithmetic_rejected(self):
        with pytest.raises(PolicyError, match="Disallowed expression"):
            eval_expr("1 + 1", {})

    def test_invalid_syntax_raises_policy_error(self):
        with pytest.raises(PolicyError, match="Invalid expression"):
            eval_expr("a and", {"a": True})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


ALL_BLINDS = ["LivBig", "LivDoor", "Bedroom", "Study", "Sklad"]


def _base_cfg():
    """A minimal but realistic config used across many tests."""
    return {
        "tilts": {
            "closed": 0.0,
            "open_privacy": 0.7,
            "open_half": 0.9,
            "open": 1.0,
        },
        "blind_groups": {
            "all": list(ALL_BLINDS),
            "windows": ["LivBig", "Bedroom", "Study", "Sklad"],
        },
        "presets": {
            "closed_up": {"pos": 100, "tilt": "closed"},
            "fully_down": {"pos": 0, "tilt": "closed"},
            "vented": {"pos": 0, "tilt": "open_half"},
            "privacy_down": {"pos": 0, "tilt": "open_privacy"},
            "living_morning": {"pos": "$living_position", "tilt": "open_half"},
        },
        "scenes": {},
    }


@pytest.fixture
def base_cfg():
    return _base_cfg()


@pytest.fixture
def base_ctx():
    """Default runtime context with all flags off and inputs bound."""
    return {
        "guest_mode": False,
        "winter_mode": False,
        "automation_enabled": True,
        "bedroom_automation_enabled": True,
        "dusk_automation_enabled": True,
        "full_open_automation_enabled": True,
        "close_on_dawn_enabled": True,
        "early": False,
        "living_position": 40,
        "living_tilt": 0.2,
    }


# ---------------------------------------------------------------------------
# Action resolution
# ---------------------------------------------------------------------------


class TestActionResolution:
    def test_inline_pos_tilt(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"pos": 50, "tilt": 0.5}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result == {"LivBig": Action(pos=50.0, tilt=0.5)}

    def test_preset_resolves_alias(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"preset": "closed_up"}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result["LivBig"] == Action(pos=100.0, tilt=0.0)

    def test_dollar_reference_resolves_from_context(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"preset": "living_morning"}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result["LivBig"] == Action(pos=40.0, tilt=0.9)

    def test_preset_overrides(self, base_cfg, base_ctx):
        # preset says closed_up (pos=100, tilt=closed); override tilt to 0.5
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"preset": "closed_up", "tilt": 0.5}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result["LivBig"] == Action(pos=100.0, tilt=0.5)

    def test_tilt_only_preserves_pos_none(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"tilt": "open_half"}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result["LivBig"] == Action(pos=None, tilt=0.9)

    def test_string_skip_action(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": "skip"}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result == {}

    def test_unknown_preset_raises(self, base_cfg):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"preset": "nope"}}}
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        with pytest.raises(PolicyError, match="Unknown preset"):
            p.evaluate("s", {})

    def test_unbound_dollar_var_raises(self, base_cfg):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"pos": "$missing"}}}
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        with pytest.raises(PolicyError, match="not bound in context"):
            p.evaluate("s", {})


# ---------------------------------------------------------------------------
# Rule list with when/default/skip
# ---------------------------------------------------------------------------


class TestRuleList:
    def test_when_match_first(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {
            "blinds": {
                "Sklad": [
                    {"when": "guest_mode", "action": "skip"},
                    {"default": {"preset": "closed_up"}},
                ]
            }
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)

        # guest_mode = False -> default branch
        r = p.evaluate("s", {**base_ctx, "guest_mode": False})
        assert r == {"Sklad": Action(pos=100.0, tilt=0.0)}

        # guest_mode = True -> skip branch
        r = p.evaluate("s", {**base_ctx, "guest_mode": True})
        assert r == {}

    def test_first_match_wins(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {
            "blinds": {
                "Sklad": [
                    {"when": "guest_mode", "action": "skip"},
                    {"when": "winter_mode", "action": {"preset": "fully_down"}},
                    {"default": {"preset": "closed_up"}},
                ]
            }
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        ctx = {**base_ctx, "guest_mode": True, "winter_mode": True}
        # both guards true; first wins (skip)
        assert p.evaluate("s", ctx) == {}

    def test_no_match_no_default_is_skip(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"Sklad": [{"when": "winter_mode", "action": {"preset": "fully_down"}}]}}
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        # winter_mode = False, no default -> blind omitted
        assert p.evaluate("s", base_ctx) == {}

    def test_rule_without_when_or_default_raises(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"Sklad": [{"action": "skip"}]}}
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        with pytest.raises(PolicyError, match="'when' or 'default'"):
            p.evaluate("s", base_ctx)

    def test_when_requires_action(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"Sklad": [{"when": "True"}, {"default": "skip"}]}}
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        with pytest.raises(PolicyError, match="must specify 'action'"):
            p.evaluate("s", base_ctx)


# ---------------------------------------------------------------------------
# Wildcards & groups
# ---------------------------------------------------------------------------


class TestBlindKeys:
    def test_wildcard_expands_to_all(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"*": {"preset": "fully_down"}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert set(result.keys()) == set(ALL_BLINDS)
        for action in result.values():
            assert action == Action(pos=0.0, tilt=0.0)

    def test_group_reference(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"@windows": {"preset": "fully_down"}}}
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert "LivDoor" not in result
        assert set(result.keys()) == {"LivBig", "Bedroom", "Study", "Sklad"}

    def test_explicit_blind_overrides_wildcard(self, base_cfg, base_ctx):
        # later entries override earlier (Python dict insertion order)
        base_cfg["scenes"]["s"] = {
            "blinds": {
                "*": {"preset": "fully_down"},
                "LivBig": {"preset": "closed_up"},
            }
        }
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert result["LivBig"] == Action(pos=100.0, tilt=0.0)
        assert result["Bedroom"] == Action(pos=0.0, tilt=0.0)

    def test_explicit_skip_overrides_wildcard(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {
            "blinds": {
                "*": {"preset": "fully_down"},
                "LivBig": "skip",
            }
        }
        result = BlindsPolicy(base_cfg, ALL_BLINDS).evaluate("s", base_ctx)
        assert "LivBig" not in result
        assert "Bedroom" in result

    def test_unknown_blind_at_load_time(self, base_cfg):
        base_cfg["scenes"]["s"] = {"blinds": {"Ghost": {"preset": "fully_down"}}}
        with pytest.raises(PolicyError, match="unknown blind"):
            BlindsPolicy(base_cfg, ALL_BLINDS)

    def test_unknown_group_at_load_time(self, base_cfg):
        base_cfg["scenes"]["s"] = {"blinds": {"@nope": {"preset": "fully_down"}}}
        with pytest.raises(PolicyError, match="unknown group"):
            BlindsPolicy(base_cfg, ALL_BLINDS)


# ---------------------------------------------------------------------------
# requires gate, on_apply hooks, scene inheritance
# ---------------------------------------------------------------------------


class TestSceneFeatures:
    def test_requires_gate_skips_scene(self, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {
            "requires": "automation_enabled",
            "blinds": {"LivBig": {"preset": "closed_up"}},
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        assert p.evaluate("s", {**base_ctx, "automation_enabled": True}) != {}
        assert p.evaluate("s", {**base_ctx, "automation_enabled": False}) == {}

    def test_on_apply_hooks(self, base_cfg):
        base_cfg["scenes"]["s"] = {
            "on_apply": ["mark_morning", "ping"],
            "blinds": {"LivBig": {"preset": "closed_up"}},
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        assert p.hooks("s") == ["mark_morning", "ping"]
        assert p.hooks("missing") == []

    def test_inheritance_overrides_set(self, base_cfg, base_ctx):
        base_cfg["scenes"]["parent"] = {
            "blinds": {
                "Bedroom": [
                    {"when": "early", "action": "skip"},
                    {"default": {"preset": "closed_up"}},
                ]
            }
        }
        base_cfg["scenes"]["child"] = {
            "inherits": "parent",
            "set": {"early": True},
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        # parent: early=False (from base_ctx) -> default applies
        assert p.evaluate("parent", base_ctx)["Bedroom"] == Action(pos=100.0, tilt=0.0)
        # child sets early=True -> skip path
        assert p.evaluate("child", base_ctx) == {}

    def test_inheritance_merges_blinds_dict(self, base_cfg, base_ctx):
        base_cfg["scenes"]["parent"] = {"blinds": {"LivBig": {"preset": "closed_up"}}}
        base_cfg["scenes"]["child"] = {
            "inherits": "parent",
            "blinds": {"Sklad": {"preset": "fully_down"}},
        }
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        result = p.evaluate("child", base_ctx)
        assert "LivBig" in result and "Sklad" in result

    def test_circular_inheritance_raises(self, base_cfg):
        base_cfg["scenes"]["a"] = {"inherits": "b", "blinds": {}}
        base_cfg["scenes"]["b"] = {"inherits": "a", "blinds": {}}
        with pytest.raises(PolicyError, match="Circular inheritance"):
            BlindsPolicy(base_cfg, ALL_BLINDS)

    def test_unknown_scene_raises(self, base_cfg):
        p = BlindsPolicy(base_cfg, ALL_BLINDS)
        with pytest.raises(PolicyError, match="Unknown scene"):
            p.evaluate("nope", {})


# ---------------------------------------------------------------------------
# Realistic scene matching the user's request: Sklad fully up on morning
# ---------------------------------------------------------------------------


class TestMorningSceneSpec:
    """Pin the user's actual ask: Sklad fully up on morning, except in guest mode."""

    @pytest.fixture
    def cfg(self, base_cfg):
        base_cfg["scenes"]["blinds_morning"] = {
            "on_apply": ["mark_morning"],
            "blinds": {
                "LivBig": {"preset": "living_morning"},
                "LivDoor": {"preset": "closed_up"},
                "Bedroom": {"preset": "closed_up"},
                "Study": {"preset": "vented"},
                "Sklad": [
                    {"when": "guest_mode", "action": "skip"},
                    {"default": {"preset": "closed_up"}},
                ],
            },
        }
        return base_cfg

    def test_sklad_fully_up_default(self, cfg, base_ctx):
        p = BlindsPolicy(cfg, ALL_BLINDS)
        result = p.evaluate("blinds_morning", base_ctx)
        assert result["Sklad"] == Action(pos=100.0, tilt=0.0)
        assert result["LivBig"] == Action(pos=40.0, tilt=0.9)  # $living_position=40
        assert result["LivDoor"] == Action(pos=100.0, tilt=0.0)
        assert result["Bedroom"] == Action(pos=100.0, tilt=0.0)
        assert result["Study"] == Action(pos=0.0, tilt=0.9)

    def test_sklad_skipped_in_guest_mode(self, cfg, base_ctx):
        p = BlindsPolicy(cfg, ALL_BLINDS)
        result = p.evaluate("blinds_morning", {**base_ctx, "guest_mode": True})
        assert "Sklad" not in result
        # other blinds still apply
        assert "LivBig" in result and "LivDoor" in result


# ---------------------------------------------------------------------------
# YAML file loading round-trip
# ---------------------------------------------------------------------------


class TestYamlFileLoading:
    def test_from_yaml_file_round_trip(self, tmp_path, base_cfg, base_ctx):
        base_cfg["scenes"]["s"] = {"blinds": {"LivBig": {"preset": "closed_up"}}}
        path = tmp_path / "policy.yaml"
        path.write_text(yaml.safe_dump(base_cfg))

        p = BlindsPolicy.from_yaml_file(str(path), ALL_BLINDS)
        assert p.has_scene("s")
        assert p.evaluate("s", base_ctx)["LivBig"] == Action(pos=100.0, tilt=0.0)

    def test_missing_file_raises(self):
        with pytest.raises(PolicyError, match="not found"):
            BlindsPolicy.from_yaml_file("/nonexistent/path/x.yaml", ALL_BLINDS)


# ---------------------------------------------------------------------------
# Regression: the in-repo blinds_policy.yaml must always parse, validate, and
# behave per spec for the user-facing scenes.
# ---------------------------------------------------------------------------


_REPO_POLICY = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "ph4ha", "config", "blinds_policy.yaml")
)


def _full_ctx(**overrides):
    base = {
        "guest_mode": False,
        "winter_mode": False,
        "automation_enabled": True,
        "bedroom_automation_enabled": True,
        "dusk_automation_enabled": True,
        "full_open_automation_enabled": True,
        "close_on_dawn_enabled": True,
        "morning_automation_enabled": True,
        "morning_weekend_automation_enabled": True,
        "night_venting_enabled": True,
        "early": False,
        "living_position": 40,
        "living_tilt": 0.2,
        "tilt_default": 0.9,
    }
    base.update(overrides)
    return base


@pytest.mark.skipif(
    not os.path.isfile(_REPO_POLICY),
    reason="repo policy yaml not present",
)
class TestRepoPolicyYaml:
    @pytest.fixture(scope="class")
    def policy(self):
        return BlindsPolicy.from_yaml_file(_REPO_POLICY, ALL_BLINDS)

    def test_loads_all_expected_scenes(self, policy):
        # Every name referenced by the existing HA card / scenes file or by
        # the AppDaemon timer entry points must resolve.
        required = {
            "blinds_morning",
            "blinds_morning_context",
            "blinds_early_morning_context",
            "blinds_living_morning",
            "blinds_living_morning_hot",
            "blinds_living_morning_tilt",
            "blinds_living_privacy",
            "blinds_living_down_close",
            "blinds_living_down_open",
            "blinds_living_down_privacy",
            "blinds_all_up",
            "blinds_all_down",
            "blinds_all_window_down",
            "blinds_all_window_privacy",
            "blinds_down_open",
            "blinds_all_down_open",
            "blinds_tilt_open",
            "blinds_tilt_close",
            "blinds_vent",
            "blinds_vent_bedroom",
            "blinds_vent_livingroom",
            "blinds_vent_window",
            "blinds_dusk",
            "blinds_pre_dusk",
            "blinds_pre_dawn",
        }
        missing = required - set(policy.scene_names)
        assert not missing, f"Missing scenes: {missing}"

    def test_morning_sklad_fully_up(self, policy):
        """The user-facing change: Sklad fully retracted on morning."""
        result = policy.evaluate("blinds_morning", _full_ctx())
        assert result["Sklad"] == Action(pos=100.0, tilt=0.0)

    def test_morning_sklad_skip_in_guest_mode(self, policy):
        result = policy.evaluate("blinds_morning", _full_ctx(guest_mode=True))
        assert "Sklad" not in result

    def test_morning_context_all_rooms_default(self, policy):
        result = policy.evaluate("blinds_morning_context", _full_ctx())
        assert result["LivBig"] == Action(pos=40.0, tilt=0.9)
        assert result["LivDoor"] == Action(pos=100.0, tilt=0.0)
        assert result["Bedroom"] == Action(pos=100.0, tilt=0.0)
        assert result["Study"] == Action(pos=0.0, tilt=0.9)
        assert result["Sklad"] == Action(pos=100.0, tilt=0.0)

    def test_morning_context_skips_when_automation_disabled(self, policy):
        result = policy.evaluate("blinds_morning_context", _full_ctx(automation_enabled=False))
        assert result == {}

    def test_morning_context_skips_bedroom_when_early(self, policy):
        result = policy.evaluate("blinds_morning_context", _full_ctx(early=True))
        assert "Bedroom" not in result
        assert result["LivBig"] == Action(pos=40.0, tilt=0.9)

    def test_early_morning_context_inherits_with_early_set(self, policy):
        # The inheritance chain should yield the same result as
        # morning_context with early=True.
        early_ctx = _full_ctx()
        ctx_with_early = _full_ctx(early=True)
        assert policy.evaluate("blinds_early_morning_context", early_ctx) == policy.evaluate(
            "blinds_morning_context", ctx_with_early
        )

    def test_dusk_bedroom_only_in_winter(self, policy):
        summer = policy.evaluate("blinds_dusk", _full_ctx())
        winter = policy.evaluate("blinds_dusk", _full_ctx(winter_mode=True))
        assert "Bedroom" not in summer
        assert "Bedroom" in winter

    def test_pre_dawn_gate(self, policy):
        assert policy.evaluate("blinds_pre_dawn", _full_ctx()) != {}
        assert policy.evaluate("blinds_pre_dawn", _full_ctx(close_on_dawn_enabled=False)) == {}

    def test_morning_hooks(self, policy):
        assert policy.hooks("blinds_morning") == ["mark_morning"]
        assert policy.hooks("blinds_morning_context") == ["mark_morning_context"]
