"""sft-nix: Nix environment detection and syncing for sft.

When installed, this plugin replaces the stub functions in ``sft.env`` with
real implementations that detect ``.envrc`` / ``flake.nix`` files and wrap
remote commands in ``nix develop``.

The overrides are applied when the plugin is loaded via the entry point
mechanism in ``hooks.py``.
"""
