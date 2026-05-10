"""Plugin hooks for sft-nix.

This module is loaded via the ``sft.plugins`` entry point when sft starts.
It applies env stub overrides and registers the post-transfer hook for
.envrc/flake file syncing.
"""

from __future__ import annotations

import json
import os
import shlex
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from sft.config import ParsedTarget
from sft.context import ExecutionContext
from sft.ui import Theme


def _resolve_effective_dst(
    src: ParsedTarget, dst: ParsedTarget, ctx: ExecutionContext
) -> str:
    """Compute the actual destination path after transfer.

    When ``dst.path`` is an existing directory, the transfer logic
    (git-bundle / archive) appends the source basename to it.
    The ``dst`` ParsedTarget is not updated, so we replicate the
    same logic here.
    """
    if dst.is_remote:
        assert dst.host
        try:
            ctx.run_ssh(
                dst.host,
                f"test -d {shlex.quote(dst.path)}",
                allow_dry_run_execute=True,
            )
            is_dir = True
        except RuntimeError:
            is_dir = False
        if is_dir:
            return os.path.join(dst.path, os.path.basename(src.path.rstrip("/")))
    else:
        if Path(dst.path).is_dir():
            return os.path.join(dst.path, os.path.basename(src.path.rstrip("/")))
    return dst.path


def _resolve_flake_path_local(envrc_dir: str, raw_path: str) -> Optional[str]:
    """Turn a raw ``use flake`` path into an absolute local path."""
    if raw_path.startswith("/") or raw_path.startswith("~"):
        return os.path.expanduser(raw_path)
    return os.path.normpath(os.path.join(envrc_dir, raw_path))


def _resolve_flake_path_remote(
    src: ParsedTarget,
    envrc_dir: str,
    raw_path: str,
    ctx: ExecutionContext,
) -> Optional[str]:
    """Turn a raw ``use flake`` path into an absolute remote path."""
    assert src.host
    script = textwrap.dedent(
        """
        import os, sys
        envrc_dir = os.path.expanduser(%s)
        raw_path = %s
        if raw_path.startswith("/") or raw_path.startswith("~"):
            print(os.path.realpath(os.path.expanduser(raw_path)))
            sys.exit(0)
        print(os.path.realpath(os.path.join(envrc_dir, raw_path)))
        """
    ) % (json.dumps(envrc_dir), json.dumps(raw_path))
    try:
        return ctx.run_ssh(
            src.host,
            f"python3 - <<'PY'\n{script}\nPY",
            capture=True,
        )
    except RuntimeError:
        return None


def _sync_one_envrc(
    envrc_dir: str,
    src: ParsedTarget,
    dst: ParsedTarget,
    effective_dst: str,
    ctx: ExecutionContext,
) -> None:
    """Sync flake files and .envrc for a single envrc directory."""
    import sft.env as env_mod

    # --- 1. Parse flake path from .envrc ---
    if src.is_remote:
        flake_path_raw = env_mod.parse_envrc_flake_path_remote(
            src, envrc_dir, ctx
        )
    else:
        flake_path_raw = env_mod.parse_envrc_flake_path_local(envrc_dir)

    if not flake_path_raw:
        return

    # --- 2. Resolve flake path to absolute ---
    if src.is_remote:
        flake_abs = _resolve_flake_path_remote(src, envrc_dir, flake_path_raw, ctx)
    else:
        flake_abs = _resolve_flake_path_local(envrc_dir, flake_path_raw)

    if not flake_abs:
        Theme.warning(f"Could not resolve flake path: {flake_path_raw}")
        return

    Theme.info("Flake Path", flake_path_raw)

    # --- 3. Sync flake.nix + flake.lock ---
    from sft.transfer import copy_single_file

    dst_flake_base = env_mod.compute_envrc_target_dir(
        src.path, envrc_dir, effective_dst
    )

    def _transfer_stub(stub: str) -> None:
        if src.is_remote:
            assert src.host
            remote_file = os.path.join(flake_abs, stub)
            try:
                ctx.run_ssh(
                    src.host,
                    f"test -f {shlex.quote(remote_file)}",
                )
            except RuntimeError:
                Theme.warning(f"Source flake file not found: {remote_file}")
                return
            src_file = remote_file
        else:
            src_file = os.path.join(flake_abs, stub)
            if not os.path.exists(src_file):
                Theme.warning(f"Source flake file not found: {src_file}")
                return

        dst_file = os.path.join(dst_flake_base, stub)
        copy_single_file(src, src_file, dst, dst_file, ctx)

    Theme.step(Theme.XFER, "Syncing flake files", f"{flake_path_raw}")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_transfer_stub, stub): stub
            for stub in ("flake.nix", "flake.lock")
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                Theme.error(f"Error transferring {futures[future]}: {e}")

    # --- 4. Sync .envrc itself ---
    dst_envrc_dir = env_mod.compute_envrc_target_dir(
        src.path, envrc_dir, effective_dst
    )
    src_envrc = os.path.join(envrc_dir, ".envrc")
    dst_envrc = os.path.join(dst_envrc_dir, ".envrc")

    if not src.is_remote:
        if os.path.exists(src_envrc):
            Theme.step(Theme.XFER, "Syncing .envrc", src_envrc)
            copy_single_file(src, src_envrc, dst, dst_envrc, ctx)
        else:
            Theme.warning(f"Source .envrc not found: {src_envrc}")
    else:
        assert src.host
        try:
            ctx.run_ssh(src.host, f"test -f {shlex.quote(src_envrc)}")
            Theme.step(Theme.XFER, "Syncing .envrc", src_envrc)
            copy_single_file(src, src_envrc, dst, dst_envrc, ctx)
        except RuntimeError:
            Theme.warning(f"Source .envrc not found: {src_envrc}")


def _post_transfer_envrc_flake(
    src: ParsedTarget,
    dst: ParsedTarget,
    args: Any,
    ctx: ExecutionContext,
) -> None:
    """Post-transfer hook: sync .envrc and flake files for all envrc dirs."""
    import sft.env as env_mod

    # 1. Find all .envrc directories in the source tree
    if src.is_remote:
        envrc_dirs = env_mod.find_all_envrc_dirs_remote(
            src, ctx, allow_dry_run_execute=True
        )
    else:
        envrc_dirs = env_mod.find_all_envrc_dirs_local(src.path)

    if not envrc_dirs:
        return

    Theme.info("Envrc", f"{len(envrc_dirs)} found")

    # 2. Compute effective destination (accounts for dst being an existing dir)
    effective_dst = _resolve_effective_dst(src, dst, ctx)

    # 3. Sync each .envrc + its flake files
    for envrc_dir in envrc_dirs:
        _sync_one_envrc(envrc_dir, src, dst, effective_dst, ctx)


def register() -> None:
    """Apply overrides and register hooks."""
    from sft_nix._overrides import apply_overrides

    apply_overrides()
    from sft.plugins import register_post_transfer_hook

    register_post_transfer_hook(_post_transfer_envrc_flake)


# Auto-register on import so that discover_plugins() via ep.load() activates us.
register()
