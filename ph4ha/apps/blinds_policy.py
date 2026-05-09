"""
Declarative blinds policy engine.

Parses a YAML configuration that describes:
  - inputs        - bind $names to runtime-resolved values (HA input_number entities,
                    AppDaemon class attributes, etc.); the host wires them into the context
  - tilts         - semantic names for slat positions (0..1)
  - blind_groups  - named subsets of all blinds (referenced as @groupname)
  - presets       - named (pos, tilt) bundles; pos/tilt may be a literal or $name reference
  - scenes        - per-blind action with optional `when:` branching and `skip` action

Evaluation is pure: feed in a context dict (runtime flag values + bound $inputs)
and get back the concrete (pos, tilt) action per blind.

This module deliberately depends only on the standard library + PyYAML so it can be
imported from unit tests without pulling AppDaemon.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """Resolved concrete action for a single blind.

    pos   - 0..100 or None to leave that axis untouched
    tilt  - 0..1 or None to leave that axis untouched
    skip  - explicit skip flag (overrides pos/tilt; nothing is sent)
    """

    pos: Optional[float] = None
    tilt: Optional[float] = None
    skip: bool = False

    @classmethod
    def skip_action(cls) -> "Action":
        return cls(skip=True)

    def is_noop(self) -> bool:
        return self.skip or (self.pos is None and self.tilt is None)


class PolicyError(ValueError):
    """Raised on schema, reference, or expression problems."""


# ---------------------------------------------------------------------------
# Safe expression evaluator (used for `when:` and `requires:`)
# ---------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


def eval_expr(expr: Optional[str], context: Mapping[str, Any]) -> Any:
    """Safely evaluate a boolean/comparison expression against a context.

    Supports: identifiers (looked up in context), and/or/not, comparisons,
    boolean/numeric/string literals, in/not in. No function calls, attribute
    access, or arithmetic. Missing identifiers raise PolicyError.

    Returns: the evaluated value (truthy/falsey expected for guards).
    Empty / None expression -> True (treated as "no guard").
    """
    if expr is None:
        return True
    expr = str(expr).strip()
    if not expr:
        return True
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise PolicyError(f"Invalid expression: {expr!r}: {e}")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise PolicyError(
                f"Disallowed expression construct {type(node).__name__} in: {expr!r}"
            )
    return _eval_node(tree.body, context)


def _eval_node(node: ast.AST, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise PolicyError(f"Unknown identifier in expression: {node.id!r}")
        return context[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, context)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for v in node.values:
                result = _eval_node(v, context)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for v in node.values:
                result = _eval_node(v, context)
                if result:
                    return result
            return result
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp, context)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.In):
                ok = left in right
            elif isinstance(op, ast.NotIn):
                ok = left not in right
            else:
                raise PolicyError(f"Unsupported compare op: {type(op).__name__}")
            if not ok:
                return False
            left = right
        return True
    raise PolicyError(f"Unsupported expression node: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class BlindsPolicy:
    """Loaded policy. Stateless w.r.t. evaluation — feed runtime context per call."""

    def __init__(self, config: Mapping[str, Any], all_blinds: Sequence[str]):
        if not isinstance(config, Mapping):
            raise PolicyError("Top-level policy config must be a mapping")
        self.all_blinds: List[str] = list(all_blinds)
        self.tilts: Dict[str, float] = {
            k: float(v) for k, v in (config.get("tilts") or {}).items()
        }
        self.input_bindings: Dict[str, str] = dict(config.get("inputs") or {})
        self.groups: Dict[str, List[str]] = {
            k: list(v) for k, v in (config.get("blind_groups") or {}).items()
        }
        self.presets: Dict[str, dict] = {
            k: dict(v) for k, v in (config.get("presets") or {}).items()
        }
        raw_scenes = dict(config.get("scenes") or {})
        self.scenes: Dict[str, dict] = self._resolve_inheritance(raw_scenes)
        self._validate()

    # ----- factories -----

    @classmethod
    def from_yaml_file(
        cls, path: str, all_blinds: Sequence[str]
    ) -> "BlindsPolicy":
        if not os.path.isfile(path):
            raise PolicyError(f"Policy file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cls(cfg, all_blinds)

    @classmethod
    def from_dict(
        cls, cfg: Mapping[str, Any], all_blinds: Sequence[str]
    ) -> "BlindsPolicy":
        return cls(cfg, all_blinds)

    # ----- public API -----

    @property
    def scene_names(self) -> List[str]:
        return list(self.scenes.keys())

    def has_scene(self, scene: str) -> bool:
        return scene in self.scenes

    def hooks(self, scene: str) -> List[str]:
        if scene not in self.scenes:
            return []
        return list(self.scenes[scene].get("on_apply") or [])

    def evaluate(
        self, scene: str, context: Mapping[str, Any]
    ) -> Dict[str, Action]:
        """Resolve a scene to per-blind concrete actions.

        Returns a dict mapping blind name -> Action. Blinds that resolve to
        skip or have no rule match are omitted from the result.

        If the scene's `requires:` clause evaluates falsey, returns {} (no-op).
        Raises PolicyError on unknown scene or schema problems.
        """
        if scene not in self.scenes:
            raise PolicyError(f"Unknown scene: {scene}")
        spec = self.scenes[scene]

        # local context = caller context overlaid with scene's `set:`
        ctx = dict(context)
        for k, v in (spec.get("set") or {}).items():
            ctx[k] = v

        req = spec.get("requires")
        if req is not None and not eval_expr(str(req), ctx):
            return {}

        # Walk blinds in declaration order. Group/wildcard expansions are
        # filled in early so per-blind explicit entries can still override.
        results: Dict[str, Action] = {}
        for blind_key, action_spec in (spec.get("blinds") or {}).items():
            for blind in self._resolve_blind_key(blind_key):
                action = self._resolve_action(action_spec, ctx)
                if action is None:
                    # rule list with no match and no default -> skip
                    continue
                if action.skip or action.is_noop():
                    # Explicit skip removes any previously-set action on this blind
                    results.pop(blind, None)
                    continue
                results[blind] = action
        return results

    # ----- internals -----

    def _resolve_blind_key(self, key: str) -> List[str]:
        if key == "*":
            return list(self.all_blinds)
        if isinstance(key, str) and key.startswith("@"):
            group_name = key[1:]
            if group_name not in self.groups:
                raise PolicyError(f"Unknown blind group: {key!r}")
            return list(self.groups[group_name])
        if key not in self.all_blinds:
            raise PolicyError(f"Unknown blind: {key!r}")
        return [key]

    def _resolve_action(
        self, spec: Any, ctx: Mapping[str, Any]
    ) -> Optional[Action]:
        if spec is None:
            return None
        if isinstance(spec, list):
            return self._resolve_rule_list(spec, ctx)
        if isinstance(spec, str):
            if spec.lower() == "skip":
                return Action.skip_action()
            raise PolicyError(f"Unknown action shorthand: {spec!r}")
        if isinstance(spec, Mapping):
            return self._resolve_action_mapping(spec, ctx)
        raise PolicyError(f"Unsupported action spec: {spec!r}")

    def _resolve_rule_list(
        self, rules: list, ctx: Mapping[str, Any]
    ) -> Optional[Action]:
        for rule in rules:
            if not isinstance(rule, Mapping):
                raise PolicyError(f"Rule must be a mapping: {rule!r}")
            if "default" in rule:
                return self._resolve_action(rule["default"], ctx)
            if "when" not in rule:
                raise PolicyError(
                    f"Rule must have either 'when' or 'default': {rule!r}"
                )
            if eval_expr(rule["when"], ctx):
                if "action" not in rule:
                    raise PolicyError(
                        f"Rule with 'when' must specify 'action': {rule!r}"
                    )
                return self._resolve_action(rule["action"], ctx)
        return None  # no match, no default

    def _resolve_action_mapping(
        self, spec: Mapping[str, Any], ctx: Mapping[str, Any]
    ) -> Action:
        if spec.get("skip"):
            return Action.skip_action()

        pos: Any = None
        tilt: Any = None
        if "preset" in spec:
            preset_name = spec["preset"]
            if preset_name not in self.presets:
                raise PolicyError(f"Unknown preset: {preset_name!r}")
            preset = self.presets[preset_name]
            pos = preset.get("pos")
            tilt = preset.get("tilt")
        if "pos" in spec:
            pos = spec["pos"]
        if "tilt" in spec:
            tilt = spec["tilt"]

        return Action(
            pos=self._resolve_pos(pos, ctx),
            tilt=self._resolve_tilt(tilt, ctx),
        )

    def _resolve_pos(self, pos: Any, ctx: Mapping[str, Any]) -> Optional[float]:
        if pos is None:
            return None
        if isinstance(pos, str):
            if pos.startswith("$"):
                return self._resolve_var(pos[1:], ctx)
            try:
                return float(pos)
            except ValueError as e:
                raise PolicyError(f"Cannot parse pos: {pos!r}: {e}")
        return float(pos)

    def _resolve_tilt(self, tilt: Any, ctx: Mapping[str, Any]) -> Optional[float]:
        if tilt is None:
            return None
        if isinstance(tilt, str):
            if tilt.startswith("$"):
                return self._resolve_var(tilt[1:], ctx)
            if tilt in self.tilts:
                return float(self.tilts[tilt])
            try:
                return float(tilt)
            except ValueError as e:
                raise PolicyError(f"Cannot parse tilt: {tilt!r}: {e}")
        return float(tilt)

    def _resolve_var(self, name: str, ctx: Mapping[str, Any]) -> float:
        if name not in ctx:
            raise PolicyError(f"Variable not bound in context: ${name}")
        val = ctx[name]
        if val is None:
            raise PolicyError(f"Variable ${name} resolved to None")
        try:
            return float(val)
        except (TypeError, ValueError) as e:
            raise PolicyError(f"Variable ${name} is not numeric: {val!r}: {e}")

    # ----- inheritance -----

    def _resolve_inheritance(self, scenes: Mapping[str, Any]) -> Dict[str, dict]:
        resolved: Dict[str, dict] = {}
        for name, spec in scenes.items():
            if not isinstance(spec, Mapping):
                raise PolicyError(f"Scene {name!r} must be a mapping")
            resolved[name] = self._inherit(name, spec, scenes, set())
        return resolved

    def _inherit(
        self,
        name: str,
        spec: Mapping[str, Any],
        scenes: Mapping[str, Any],
        seen: set,
    ) -> dict:
        if name in seen:
            raise PolicyError(f"Circular inheritance involving scene {name!r}")
        seen = set(seen) | {name}
        if "inherits" not in spec:
            return dict(spec)
        parent_name = spec["inherits"]
        if parent_name not in scenes:
            raise PolicyError(
                f"Scene {name!r} inherits from unknown scene {parent_name!r}"
            )
        parent_spec = scenes[parent_name]
        if not isinstance(parent_spec, Mapping):
            raise PolicyError(f"Parent scene {parent_name!r} must be a mapping")
        parent = self._inherit(parent_name, parent_spec, scenes, seen)
        merged = dict(parent)
        for k, v in spec.items():
            if k == "inherits":
                continue
            if (
                k in ("blinds", "set")
                and isinstance(v, Mapping)
                and isinstance(merged.get(k), Mapping)
            ):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged

    # ----- validation -----

    def _validate(self) -> None:
        for pname, p in self.presets.items():
            if not isinstance(p, Mapping):
                raise PolicyError(f"Preset {pname!r} must be a mapping")
        for gname, members in self.groups.items():
            for m in members:
                if m not in self.all_blinds:
                    raise PolicyError(
                        f"Group {gname!r} contains unknown blind: {m!r}"
                    )
        for sname, spec in self.scenes.items():
            if not isinstance(spec, Mapping):
                raise PolicyError(f"Scene {sname!r} must be a mapping")
            blinds = spec.get("blinds") or {}
            if not isinstance(blinds, Mapping):
                raise PolicyError(f"Scene {sname!r}: blinds must be a mapping")
            for k in blinds.keys():
                if k == "*":
                    continue
                if isinstance(k, str) and k.startswith("@"):
                    if k[1:] not in self.groups:
                        raise PolicyError(
                            f"Scene {sname!r}: unknown group {k!r}"
                        )
                    continue
                if k not in self.all_blinds:
                    raise PolicyError(f"Scene {sname!r}: unknown blind {k!r}")


__all__ = ["Action", "BlindsPolicy", "PolicyError", "eval_expr"]
