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


def _post_transfer_envrc_flake(
    src: ParsedTarget,
    dst: ParsedTarget,
    args: Any,
    ctx: ExecutionContext,
) -> None:
    """Post-transfer hook: sync .envrc and flake files if detected."""
    import sft.env as env_mod

    if src.is_remote:
        probe = None
        envrc_dir = env_mod.find_envrc_dir_remote(src, ctx, allow_dry_run_execute=True)
    else:
        envrc_dir = env_mod.find_envrc_dir_local(src.path)

    if not envrc_dir:
        return

    Theme.info("Envrc", f"Found in {envrc_dir}")

    if src.is_remote:
        flake_path = env_mod.parse_envrc_flake_path_remote(src, envrc_dir, ctx)
    else:
        flake_path = env_mod.parse_envrc_flake_path_local(envrc_dir)

    if not flake_path:
        Theme.warning("Could not parse flake path from .envrc")
        return

    Theme.info("Flake Path", flake_path)

    from sft.transfer import copy_single_file

    def _prepare_and_transfer_stub(stub: str) -> None:
        if src.is_remote:
            assert src.host
            if flake_path.startswith("/") or flake_path.startswith("~"):
                p = os.path.join(flake_path, stub)
                p = os.path.expanduser(p)
                check_script = textwrap.dedent(
                    """
                    import os, sys
                    if os.path.isfile(os.path.expanduser(%s)):
                        print(os.path.realpath(os.path.expanduser(%s)))
                        sys.exit(0)
                    sys.exit(1)
                    """
                ) % (json.dumps(p), json.dumps(p))
                try:
                    src_flake_file = ctx.run_ssh(
                        src.host,
                        f"python3 - <<'PY'\n{check_script}\nPY",
                        capture=True,
                    )
                    if not src_flake_file:
                        Theme.warning(f"Source flake file not found: {flake_path}/{stub}")
                        return
                except RuntimeError:
                    Theme.warning(f"Source flake file not found: {flake_path}/{stub}")
                    return
            else:
                resolve_script = textwrap.dedent(
                    """
                    import os, sys
                    envrc_dir = os.path.expanduser(%s)
                    flake_path = %s
                    if not flake_path.startswith("/") and not flake_path.startswith("~"):
                        flake_path = os.path.join(envrc_dir, flake_path)
                    p = os.path.join(flake_path, %s)
                    p = os.path.expanduser(p)
                    p = os.path.realpath(p)
                    if os.path.isfile(p):
                        print(p)
                        sys.exit(0)
                    sys.exit(1)
                    """
                ) % (
                    json.dumps(envrc_dir),
                    json.dumps(flake_path),
                    json.dumps(stub),
                )
                try:
                    src_flake_file = ctx.run_ssh(
                        src.host,
                        f"python3 - <<'PY'\n{resolve_script}\nPY",
                        capture=True,
                    )
                    if not src_flake_file:
                        Theme.warning(f"Source flake file not found: {flake_path}/{stub}")
                        return
                except RuntimeError:
                    Theme.warning(f"Source flake file not found: {flake_path}/{stub}")
                    return

            resolved_flake_base = flake_path
            if not resolved_flake_base.startswith("/") and not resolved_flake_base.startswith("~"):
                resolved_flake_base = os.path.join(envrc_dir, resolved_flake_base)
            dst_flake_base = env_mod.compute_envrc_target_dir(
                src.path, resolved_flake_base, dst.path
            )
            dest_flake_file = os.path.join(dst_flake_base, stub)
        else:
            local_flake_base = flake_path
            if not local_flake_base.startswith("/") and not local_flake_base.startswith("~"):
                local_flake_base = os.path.join(envrc_dir, local_flake_base)
            src_flake_file = os.path.expanduser(os.path.join(local_flake_base, stub))
            if not os.path.exists(src_flake_file):
                Theme.warning(f"Source flake file not found: {src_flake_file}")
                return
            dst_flake_base = env_mod.compute_envrc_target_dir(
                src.path, local_flake_base, dst.path
            )
            dest_flake_file = os.path.join(dst_flake_base, stub)

        copy_single_file(src, src_flake_file, dst, dest_flake_file, ctx)

    Theme.step(Theme.XFER, "Syncing flake files", "parallel")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_prepare_and_transfer_stub, stub)
            for stub in ("flake.nix", "flake.lock")
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                Theme.error(f"Error transferring flake file: {e}")

    # Also copy .envrc itself — it may be absent after git bundle transfer
    # since .envrc is commonly git-ignored.
    #
    # When the user runs "sft <dir> host:<parent>" and <parent> is an
    # existing directory, git-bundle clones into <parent>/<basename>.
    # The dst ParsedTarget still points at <parent>, so we must compute
    # the real destination the same way transfer_git_bundle does.
    _effective_dst = _resolve_effective_dst(src, dst, ctx)
    src_envrc = os.path.join(envrc_dir, ".envrc")
    dst_envrc_dir = env_mod.compute_envrc_target_dir(
        src.path, envrc_dir, _effective_dst
    )
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


def register() -> None:
    """Apply overrides and register hooks."""
    from sft_nix._overrides import apply_overrides

    apply_overrides()
    from sft.plugins import register_post_transfer_hook

    register_post_transfer_hook(_post_transfer_envrc_flake)


# Auto-register on import so that discover_plugins() via ep.load() activates us.
register()
