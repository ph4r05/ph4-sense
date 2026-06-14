# Blinds policy engine — refactor handover

This document is the post-refactor reference for the blinds AppDaemon app. It
explains the new architecture, the YAML schema, how to change behavior, how
to debug it, and how to roll back.

## Why we changed it

Before this refactor, `ph4ha/apps/blinds.py` had roughly 25 per-scene Python
methods (`blinds_morning`, `blinds_morning_context`, `blinds_living_morning`,
`blinds_all_up`, etc.). Each one was a string of hard-coded
`blinds_pos_tilt(BLIND_X, pos, tilt)` calls. Per-blind exceptions
(`if not self.guest_mode`, `if self.bedroom_automation_enabled and not early`,
`if self.winter_mode`) were scattered as `if` branches inside the handlers.

Every behavior tweak — "Sklad should go up on `good morning` instead of being
vented", for example — required editing Python. There was no single place to
ask "what does Sklad do at dusk in winter mode under guest mode?".

The refactor moves all per-scene, per-room behavior into a declarative YAML
file. The Python becomes a small executor. Adding a new scene or tweaking a
room's behavior is now a YAML edit and an AppDaemon reload.

## What changed (file-by-file)

| File | Status | Purpose |
|------|--------|---------|
| `ph4ha/apps/blinds_policy.py`        | **new**  | Pure-Python policy engine. AppDaemon-free so it can be unit-tested. |
| `ph4ha/config/blinds_policy.yaml`    | **new**  | Declarative scene policy — the source of truth for what each room does in each scene. |
| `ph4ha/apps/blinds.py`               | refactor | ~25 per-scene methods removed; dispatch goes through the policy engine. Time-based scheduling, Shelly RPC, and the per-blind scene-template fallback are unchanged. |
| `ph4ha/config/apps.yaml`             | edit     | Added `policy_file: blinds_policy.yaml` under the `blinds:` app. |
| `ph4ha/config/apps.example.yaml`     | edit     | Same — for the publishable template. |
| `tests/blinds_policy_tests/`         | **new**  | 49 pytest cases covering the engine plus a regression class that loads the in-repo YAML. |

Nothing in the Home Assistant config (`config-ha/`) had to change. Every scene
referenced by the existing cards (`config-ha/blinds-card-*.yml`) and
`config-ha/scenes.yaml` still works — the dispatcher key is still the scene
ID, and the YAML defines a policy for every name HA used to invoke.

## Architecture

### Two layers

```
                       ┌──────────────────────────────────┐
   HA scene.turn_on ──▶│ Blinds.scene_activated           │
                       │   → Blinds.handle_scene(scene_id)│
                       └──────────────┬───────────────────┘
                                      │
                       ┌──────────────▼───────────────────┐
                       │   BlindsPolicy.has_scene?        │
                       └───────┬──────────────────┬───────┘
                          yes  │                  │  no
                               │                  │
                ┌──────────────▼─────────┐   ┌────▼───────────────────┐
                │ Blinds.apply_scene()   │   │ handle_scene_template  │
                │   → policy.evaluate()  │   │   (per-blind dynamic   │
                │   → _apply_action()    │   │    scenes only)        │
                │   → _run_hooks()       │   └────────────────────────┘
                └────────────────────────┘
```

### Where each concern lives

- **`blinds_policy.py`** is *pure*. It depends only on stdlib + PyYAML, knows
  nothing about AppDaemon, Shelly, or HTTP. It takes a YAML config + a list
  of blind names; it gives back `{blind_name: Action(pos, tilt)}` for a given
  scene + context. Unit tests run against it directly.

- **`blinds.py`** owns everything that touches the world:
  - Loading the policy file at `initialize()`.
  - Building the runtime context (mode flags, slider values) and feeding it
    to `policy.evaluate()`.
  - Translating each resolved `Action` into the right `blinds_pos_tilt` /
    `blinds_tilt` / Shelly RPC call.
  - Running `on_apply:` hooks (`mark_morning`, `mark_morning_context`).
  - Time-based scheduling (sun events, daily timers) — unchanged.
  - Listening to `input_*` state changes — unchanged.
  - The per-blind template fallback (see below).

### Policy engine surface (`blinds_policy.py`)

```python
class BlindsPolicy:
    @classmethod
    def from_yaml_file(cls, path: str, all_blinds: list[str]) -> "BlindsPolicy"

    def has_scene(self, name: str) -> bool
    def hooks(self, name: str) -> list[str]
    def evaluate(self, name: str, ctx: Mapping[str, Any]) -> dict[str, Action]

@dataclass
class Action:
    pos: Optional[float]   # 0..100, or None (don't change)
    tilt: Optional[float]  # 0..1,  or None (don't change)
    skip: bool             # explicit skip — overrides pos/tilt
```

`evaluate()` is pure: same config + same context => same result. It does no
I/O. It raises `PolicyError` on schema problems (unknown blind / preset /
identifier in a `when:` expression).

## YAML schema

The single source of truth lives at
[`ph4ha/config/blinds_policy.yaml`](../config/blinds_policy.yaml). The schema
has five top-level sections.

### `inputs` — bind `$names` to runtime values

```yaml
inputs:
  living_position: input_number.blinds_living_position
  living_tilt:     input_number.blinds_living_tilt
```

Each entry names an identifier the YAML can refer to as `$name`. The host
(`blinds.py`) reads the bound HA entity (or class attribute) at evaluation
time and stuffs the current value into the context dict under that name. The
engine itself just sees a dict; the binding layer lives in
`Blinds._build_context()`.

### `tilts` — semantic names for slat positions

```yaml
tilts:
  closed:       0.0
  open_privacy: 0.7
  open_half:    0.9
  open:         1.0
```

These were Python constants before (`OPEN_HALF = 0.9`, `OPEN_PRIVACY = 0.7`).
Use them wherever a tilt is expected: `tilt: open_half`.

### `blind_groups` — named subsets

```yaml
blind_groups:
  all:     [LivBig, LivDoor, Bedroom, Study, Sklad]
  windows: [LivBig, Bedroom, Study, Sklad]   # everything except LivDoor
```

Reference a group with `@name` in the `blinds:` section of a scene. `*`
expands to *all blinds known to the app* (from `apps.yaml`), independent of
any group definition.

### `presets` — named (pos, tilt) bundles

```yaml
presets:
  closed_up:    { pos: 100, tilt: closed }       # fully retracted
  fully_down:   { pos: 0,   tilt: closed }       # fully closed
  vented:       { pos: 0,   tilt: open_half }    # down + tilted for airflow
  living_morning: { pos: $living_position, tilt: open_half }
```

Pos / tilt may each be:
- a number literal (`0`, `100`, `0.7`),
- a tilt-alias string (`closed`, `open_half`) — tilt only,
- a `$name` reference resolved against the context at evaluate-time.

A scene action that uses a preset can override individual fields:
`{ preset: closed_up, tilt: 0.5 }` applies `closed_up` then overrides tilt.

### `scenes` — per-scene policy

A scene maps blind keys to action specs. Three kinds of key:
- `BlindName` — one specific blind (`LivBig`, `Sklad`, etc.).
- `"*"` — every blind known to the app.
- `"@groupname"` — expand a named group.

Each action spec is one of:

1. **Single mapping** — applies unconditionally:
   ```yaml
   LivBig: { preset: living_morning }
   LivDoor: { pos: 100, tilt: closed }
   ```

2. **`"skip"` string** — leave this blind alone:
   ```yaml
   LivDoor: skip
   ```

3. **Rule list** (first-match wins) — for context-dependent behavior:
   ```yaml
   Sklad:
     - when: "guest_mode"
       action: skip
     - when: "winter_mode"
       action: { preset: fully_down }
     - default: { preset: closed_up }
   ```

Scene-level fields:
- `requires:` — boolean expression; if it evaluates falsey the scene is a
  no-op (used for the `automation_enabled` / `dusk_automation_enabled` gates
  that used to be `if` branches in Python).
- `on_apply:` — list of hook names the host runs after the scene applies
  (`mark_morning`, `mark_morning_context`).
- `inherits:` — name of another scene to inherit from; `blinds:` and `set:`
  are merged dict-wise, other fields are replaced.
- `set:` — context overrides applied for the duration of this scene's
  evaluation (used by `blinds_early_morning_context` to set `early: true`).

### Expression mini-language

Used in `when:` and `requires:`. Implemented in `eval_expr()` via an
AST walk; the allowed nodes are explicitly enumerated. Anything else raises
`PolicyError`.

| Allowed                            | Not allowed             |
|------------------------------------|--------------------------|
| identifiers (from context)         | function calls          |
| `True`, `False`, numbers, strings  | attribute access        |
| `and`, `or`, `not`                 | arithmetic (`+`, `-`, …) |
| `==`, `!=`, `<`, `<=`, `>`, `>=`   | indexing, slicing       |
| `in`, `not in`                     | lambdas, comprehensions |

Unknown identifiers raise `PolicyError("Unknown identifier: …")` rather than
silently being `False`. That's intentional — a typo in `when: guest_modee`
becomes a loud error at first activation, not a silent mis-behavior.

The grammar is deliberately tiny. If you need arithmetic, do it in the host
context construction (`Blinds._build_context()`) and expose the result as a
named flag.

## How to change behavior

### Make Sklad go up on morning (the trigger for this work)

This is now a one-line edit. In `blinds_policy.yaml`:

```yaml
scenes:
  blinds_morning:
    blinds:
      Sklad:
        - when: "guest_mode"
          action: skip
        - default: { preset: closed_up }   # was: vented
```

Reload the AppDaemon `blinds` app. The next `scene.blinds_morning` activation
sends Sklad to `pos=100, tilt=0`.

### Add a new scene

1. Pick a name (must match the HA scene entity ID minus the `scene.` prefix,
   e.g. `blinds_afternoon_relax`).
2. Add a `scenes.blinds_afternoon_relax:` entry to `blinds_policy.yaml` with
   a `blinds:` block.
3. (If the scene doesn't exist yet in HA) add a stub to
   `config-ha/scenes.yaml` and a button to a `blinds-card-*.yml`.
4. Reload AppDaemon. No Python change needed.

### Change what `open_half` means

Edit the `tilts:` section of `blinds_policy.yaml`. Every preset and inline
`tilt: open_half` reference picks it up on reload.

### Add a new mode flag

Currently bool flags come from HA `input_boolean` entities and live as
attributes on the `Blinds` class (`guest_mode`, `winter_mode`, etc.). To add
a new one (e.g. `siesta_mode`):

1. Add an `input_boolean.blinds_siesta_mode` to HA's `configuration.yaml`.
2. Add corresponding `field_siesta_mode` / `siesta_mode` attrs, the
   `update_siesta_mode` listener, and the init wiring in `Blinds.__init__` /
   `initialize()` (the surrounding code shows the pattern).
3. Add the flag to `Blinds._build_context()` so the YAML can see it.
4. Use it in YAML: `when: "siesta_mode"`.

### Add a new slider input ($-reference)

1. Add the `input_number` to HA.
2. Add the listener + attr in `Blinds` (same pattern as `living_position`).
3. Add a binding in `inputs:` for documentation / discoverability.
4. Add the name to `Blinds._build_context()` under the bound key.
5. Use it in a preset: `pos: $my_new_input`.

## What stayed in Python (and why)

### Per-blind scene templates

Scenes named `scene.blinds_open_<blindname>`, `_close_<blindname>`,
`_vent_<blindname>`, `_tilt_open_<blindname>`, `_tilt_close_<blindname>`
are dispatched by `Blinds.handle_scene_template()`. These are uniform
"one specific blind, fixed pos/tilt" actions and there are 5 blinds × 5
verbs = 25 of them. Expanding them to YAML would be pure repetition.

The dispatcher tries the policy first, then falls back to the template
matcher. If a future need argues for moving them into YAML (e.g. you want
per-blind `when:` rules), do it.

### Time-based scheduling

`on_morning_recompute`, `on_dusk_recompute`, `on_pre_dusk_recompute`,
`on_dawn_recompute` plus the `run_at()` machinery — unchanged. The timer
callbacks (`blinds_morning_context_automated`, `blinds_on_dusk_event`,
`blinds_on_pre_dusk_event`, `blinds_on_pre_dawn_event`) call
`apply_scene("blinds_morning_context" | "blinds_dusk" | …)` after their
existing guards.

### Dedup guards on morning automation

`blinds_morning_context_automated` still runs the same three guards before
applying the scene:
- `not morning_automation_enabled` → no-op
- `happened_recently(last_morning_context_event)` → no-op
- `happened_recently(last_morning_event)` → no-op

These are *timer-entry* concerns (don't re-run if a manual press already did
it). They don't belong in the scene itself — if you manually press
`scene.blinds_morning_context`, you want it to run.

### Shelly RPC plumbing

`blinds_pos_tilt`, `blinds_tilt`, `blinds_pos_tilt_v1`, `blinds_pos_tilt_v2`,
`blinds_req`, `tilt2slat`, `is_blind_v2` — unchanged. The new
`_apply_action(blind, Action)` is a thin shim:

```
Action.skip                       → no-op
pos is None, tilt set             → blinds_tilt(blind, tilt)
pos and tilt set                  → blinds_pos_tilt(blind, pos, tilt)
pos set, tilt is None             → v2 pos-only; v1 fallback uses OPEN_HALF
```

The last branch isn't used by any current scene; it's there so future YAML
that says `{ pos: 100 }` without a tilt doesn't crash.

## How `apply_scene` flows end-to-end

```
scene.blinds_morning activated in HA
  ▼
Blinds.scene_activated  (listens to call_service for domain=scene)
  ▼
Blinds.handle_scene("scene.blinds_morning")
  ▼ policy.has_scene("blinds_morning") is True
Blinds.apply_scene("blinds_morning")
  ▼
ctx = Blinds._build_context()   # {guest_mode, winter_mode, …, $living_position, …}
  ▼
actions = policy.evaluate("blinds_morning", ctx)
  → {
       LivBig:  Action(pos=40, tilt=0.9),    # from preset living_morning
       LivDoor: Action(pos=100, tilt=0.0),   # from preset closed_up
       Bedroom: Action(pos=100, tilt=0.0),
       Study:   Action(pos=0,   tilt=0.9),
       Sklad:   Action(pos=100, tilt=0.0),   # default branch (no guest_mode)
     }
  ▼
for blind, action in actions:
    Blinds._apply_action(blind, action)
        → blinds_pos_tilt(...) → Shelly RPC
  ▼
Blinds._run_hooks("blinds_morning")
    → on_apply: ["mark_morning"]
    → self.last_morning_event = datetime.now()
```

## Tests

49 tests in `tests/blinds_policy_tests/test_blinds_policy.py`. Run with:

```bash
pytest tests/blinds_policy_tests/
```

Test classes (covered scope):

| Class | What it pins |
|-------|---------------|
| `TestEvalExpr`         | Expression evaluator — operators, short-circuit, rejection of unsafe nodes |
| `TestActionResolution` | Inline pos/tilt, presets, tilt aliases, `$`-refs, preset+override, error paths |
| `TestRuleList`         | `when:`/`action:`/`default:` semantics, first-match-wins, malformed rules |
| `TestBlindKeys`        | `*`, `@group`, explicit override of wildcards, explicit skip pruning, validation errors |
| `TestSceneFeatures`    | `requires:` gate, `on_apply:` hooks, inheritance with `set:`, circular-inheritance |
| `TestMorningSceneSpec` | The user-facing change: Sklad fully up unless `guest_mode` |
| `TestYamlFileLoading`  | Round-trip through a real YAML file + missing-file error |
| `TestRepoPolicyYaml`   | Regression class loading the in-repo YAML, asserting every expected scene exists and behaves correctly |

`TestRepoPolicyYaml` is the canary: any change to `blinds_policy.yaml` that
breaks the user-facing scene set (`blinds_morning`, `blinds_dusk`,
`blinds_all_up`, etc.) fails the test. Treat a failure as either a real
regression or an explicit intent to retire / rename a scene.

`tests/blinds_policy_tests/conftest.py` adds `ph4ha/apps/` to `sys.path` so
the policy module is importable; the apps directory is *not* turned into a
Python package because AppDaemon discovers modules by directory scan and a
stray `__init__.py` can confuse it.

## Operational notes

### Reloading after a YAML edit

AppDaemon watches the apps directory by default. After editing
`blinds_policy.yaml`, restart the `blinds` app from the AppDaemon admin UI
(or touch `blinds.py`). The `Blinds.initialize()` log line will show how
many scenes loaded:

```
Loaded blinds policy from /conf/blinds_policy.yaml: 25 scene(s)
```

### Debugging a misbehaving scene

The host logs every `apply_scene` outcome:

```
apply_scene('blinds_morning') applied 5 action(s)
```

If the gates fire, you get the gate-specific message
(`Dusk automation disabled, …`) instead. If the YAML's `requires:` is what
filtered the scene, you get:

```
apply_scene('blinds_dusk'): no-op (gated by 'requires:' or all blinds skipped)
```

If you suspect the policy YAML disagrees with what you think it should do,
run the engine directly in a REPL:

```python
import sys; sys.path.insert(0, "ph4ha/apps")
from blinds_policy import BlindsPolicy
p = BlindsPolicy.from_yaml_file(
    "ph4ha/config/blinds_policy.yaml",
    ["LivBig", "LivDoor", "Bedroom", "Study", "Sklad"],
)
ctx = {"guest_mode": True, "winter_mode": False, "automation_enabled": True,
       "bedroom_automation_enabled": True, "dusk_automation_enabled": True,
       "full_open_automation_enabled": True, "close_on_dawn_enabled": True,
       "morning_automation_enabled": True, "morning_weekend_automation_enabled": True,
       "night_venting_enabled": True, "early": False,
       "living_position": 40, "living_tilt": 0.2, "tilt_default": 0.9}
print(p.evaluate("blinds_morning", ctx))
```

This is exactly what `Blinds.apply_scene()` does at runtime, minus the
RPC call.

### Logging side-effects

`apply_scene` returns the resolved `{blind: Action}` mapping. This is useful
for ad-hoc scripts and for the tests; the production code path only relies
on the side effects (`blinds_pos_tilt`, hook updates).

## Rollback

If you need to bail out of the YAML approach:

1. The first commit that introduced this work is
   `e4582c2 blinds: add declarative policy engine module`.
2. The previous-style hard-coded handlers live unchanged in the git history
   on `tech` before that commit.
3. To rollback fully, revert the commits that touch `ph4ha/apps/blinds.py`
   and `ph4ha/config/apps.yaml`. The policy engine module and YAML can stay
   on disk — `blinds.py` only uses them when `policy_file` is set in
   `apps.yaml`.

A *partial* rollback — keep the engine, ignore the YAML — is also possible:
remove `policy_file:` from `apps.yaml`. `Blinds._load_policy()` logs
`No policy_file configured; running without declarative scenes` and the
template fallback handles any per-blind scenes. But all scene-level
behavior (`blinds_morning`, `blinds_all_up`, etc.) will be unrouted and log
`Scene scene.X not found`. So a partial rollback only makes sense if you've
re-added the Python handlers too.

## Future work (not done in this pass)

These were considered and deliberately deferred:

- **Use the dormant `BlindsState` enum.** It exists in `blinds.py` but is
  unused. A state machine that knows "what *should* the blinds be doing right
  now?" (post-reboot, after disabling automation for a while, etc.) would
  let the new `on_change_from_time` hook actually do something.
- **Tilt aliases as HA input_numbers.** The schema already supports a future
  `tilts: { open_half: { input: input_number.blinds_open_half, default: 0.9 }}`
  form, but it isn't wired yet. Today the aliases are YAML literals.
- **YAML templates** for the per-blind dynamic scenes (`blinds_open_<bld>`,
  etc.). The engine doesn't parse template strings; the host's
  `handle_scene_template` covers them in code. Add template support to the
  engine only if you start needing per-blind `when:` rules on those scenes.
- **Live reload without an AppDaemon restart.** Add an `os.stat()` poll or
  inotify watch on the YAML file and reload the policy when it changes.
  Trivial to add; not worth it until edits become frequent.
