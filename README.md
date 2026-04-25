# sft-nix

Nix environment plugin for [sft](https://github.com/StarsInDmajor/sft). Provides `.envrc`/`flake.nix` detection, flake syncing, and `nix develop` command wrapping for remote execution.

## What It Does

When installed alongside `sft`, this plugin:

1. **Detects Nix environments** — walks up from the source directory looking for `.envrc` files with `use flake` directives
2. **Syncs flake files** — copies `.envrc`, `flake.nix`, and `flake.lock` to the remote host (stub mode) or the entire flake directory (full mode)
3. **Wraps remote commands** — injects `nix develop --command` around user commands so they run inside the Nix devShell
4. **Post-transfer sync** — automatically syncs `flake.nix` and `flake.lock` after every file transfer if `.envrc` is detected

## Installation

```bash
pip install sft-nix
```

For NixOS, it's built as part of the `packages.sft` derivation alongside the core and other plugins.

## How It Works

### Plugin Loading

When sft starts, it discovers plugins via `importlib.metadata.entry_points(group="sft.plugins")`. This plugin registers as `nix = "sft_nix.hooks"` in `pyproject.toml`.

### Monkey-Patching Stubs

The core `sft.env` module provides stub functions that return `None` by default:

- `find_envrc_dir_local()` / `find_envrc_dir_remote()`
- `parse_envrc_flake_path_local()` / `parse_envrc_flake_path_remote()`
- `sync_env_payload()`
- `build_remote_execution_command()`
- `find_project_root()`

At import time, `_overrides.apply_overrides()` replaces these with real Nix-aware implementations from `_overrides.py`.

### Environment Sync Flow

```
sft sync-run ./project my-server:~/project -- python train.py
  │
  ├── resolve_env_source()        # Walk up from ./project looking for .envrc
  │   └── find_envrc_dir_local()  # → /home/user/project (found .envrc)
  │   └── parse_envrc_flake_path_local()  # → "." or "./flake" from "use flake ."
  │
  ├── sync_env_payload()          # Copy .envrc + flake files to remote
  │   ├── .envrc → my-server:~/project/.envrc
  │   ├── flake.nix → my-server:~/project/.sft/flake-env/project/flake.nix
  │   └── flake.lock → my-server:~/project/.sft/flake-env/project/flake.lock
  │
  └── build_remote_execution_command()  # Wrap in nix develop
      └── nix develop ~/project/.sft/flake-env/project --command bash <tmpscript>
```

### Post-Transfer Hook

After every `sft src dst` transfer, the plugin checks whether `.envrc` exists in the source directory. If found, it syncs `flake.nix` and `flake.lock` to the destination in parallel.

## Sync Modes

| Mode         | Behavior                                              |
| ------------ | ----------------------------------------------------- |
| `full-flake` | Rsync entire flake directory (excludes `.git`, `.direnv`, `.venv`, `result`) |
| `stub`       | Only copy `flake.nix` + `flake.lock` (default)        |
| `none`       | Skip all env syncing                                  |

## File Layout

```
sft-nix/
├── src/sft_nix/
│   ├── __init__.py          # Imports hooks.register()
│   ├── hooks.py             # Entry point: registers post-transfer hook
│   └── _overrides.py        # Real implementations of sft.env stubs
├── tests/                   # (pending)
├── pyproject.toml
└── README.md
```

## Development

```bash
# Test with sft core
PYTHONPATH=~/Workspace/sft/src:~/Workspace/sft-nix/src \
  python3 -c "
from sft_nix._overrides import apply_overrides
apply_overrides()
from sft.env import find_project_root
print(find_project_root('.'))
"

# Test envrc detection
PYTHONPATH=~/Workspace/sft/src:~/Workspace/sft-nix/src \
  python3 -c "
from sft_nix._overrides import apply_overrides
apply_overrides()
from sft.env import find_envrc_dir_local
print(find_envrc_dir_local('.'))
"
```

See the main [sft README](https://github.com/StarsInDmajor/sft) for the NixOS development workflow (path: vs github: flake inputs).

## License

MIT
