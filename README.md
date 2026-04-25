# sft-nix

Nix environment plugin for [sft](https://github.com/pulcerto/sft).

Provides:
- `.envrc` / `flake.nix` detection (local and remote)
- Flake directory syncing (full or stub mode)
- `nix develop` command wrapping for remote execution
- Post-transfer flake file syncing

## Installation

```bash
pip install sft-nix
```

## How it works

When installed, `sft-nix` replaces the stub functions in `sft.env` with real Nix-aware implementations via monkey-patching at import time. This allows `sft run` and `sft sync-run` to detect Nix environments and wrap commands in `nix develop`.

## License

MIT
