#!/usr/bin/env python3
"""Run a command or transfer a file on an HPC login node over SSH.

Two ways to pick the target
    --platform NAME        read host/port/user/auth from ~/.compchemkit/config.json
                           (created by `hpc_config.py init`, see the SKILL)
    --host/--user ...      explicit flags, config not needed

Usage
    python remote.py exec  --platform mycluster "squeue -u $USER"
    python remote.py exec  --platform mycluster --timeout 60 "hostname"
    python remote.py put   --platform mycluster ./local.xyz /path/to/project/local.xyz
    python remote.py get   --platform mycluster /path/to/project/out.tar.gz ./out.tar.gz
    python remote.py exec  --host hpc.example.edu --user your_username "hostname"
    HPC_PASS=xxx python remote.py exec --platform mycluster --auth password "hostname"

Exit code of `exec` is the remote exit code (so it composes in shell pipelines).
Requires: pip install paramiko
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover
    sys.exit("paramiko is required:  python -m pip install paramiko")

sys.path.insert(0, str(Path(__file__).resolve().parent))


def platform_defaults(args) -> dict:
    """Resolve host/port/user/auth, from the config file when --platform is used."""
    if args.platform:
        import hpc_config
        plat, name = hpc_config.load(args.config, args.platform)
        auth = plat.get("auth") or {}
        return {
            "host": plat["host"], "port": int(plat.get("port") or 22), "user": plat["user"],
            "auth": args.auth or auth.get("method") or "key",
            "key": args.key or auth.get("key_path"),
            "password_env": args.password_env or auth.get("password_env") or "HPC_PASS",
            "password": args.password or auth.get("password"),
            "platform": name,
        }
    missing = [f for f in ("host", "user") if not getattr(args, f)]
    if missing:
        sys.exit(f"need either --platform or --host/--user (missing: {', '.join(missing)})")
    return {"host": args.host, "port": args.port, "user": args.user, "auth": args.auth,
            "key": args.key, "password_env": args.password_env, "password": args.password,
            "platform": None}


def connect(cfg: dict):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = dict(hostname=cfg["host"], port=cfg["port"], username=cfg["user"],
                  timeout=25, banner_timeout=30, auth_timeout=30,
                  allow_agent=False, look_for_keys=False)
    if cfg["auth"] == "password":
        pw = os.environ.get(cfg["password_env"] or "") or cfg.get("password")
        if not pw:
            pw = getpass.getpass(f"password for {cfg['user']}@{cfg['host']}: ")
        kwargs["password"] = pw
    else:
        kwargs["look_for_keys"] = True
        kwargs["key_filename"] = os.path.expanduser(cfg["key"]) if cfg.get("key") else None
    client.connect(**kwargs)
    return client


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="config.json path (default ~/.compchemkit/config.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--platform", default=None, help="platform name from the config file")
        p.add_argument("--host", default=None)
        p.add_argument("--user", default=None)
        p.add_argument("--port", type=int, default=None)
        p.add_argument("--auth", choices=["key", "password"], default=None)
        p.add_argument("--key", default=None, help="private key path")
        p.add_argument("--password-env", default=None, help="env var holding the password")
        p.add_argument("--password", default=None, help="avoid: visible in shell history")

    p = sub.add_parser("exec"); common(p)
    p.add_argument("command")
    p.add_argument("--timeout", type=float, default=600)

    p = sub.add_parser("put"); common(p)
    p.add_argument("local"); p.add_argument("remote")

    p = sub.add_parser("get"); common(p)
    p.add_argument("remote"); p.add_argument("local")

    args = ap.parse_args()
    cfg = platform_defaults(args)
    if cfg["port"] is None:
        cfg["port"] = 22
    client = connect(cfg)
    try:
        if args.cmd == "exec":
            _, out, err = client.exec_command(args.command, timeout=args.timeout)
            sys.stdout.write(out.read().decode(errors="replace"))
            sys.stderr.write(err.read().decode(errors="replace"))
            return out.channel.recv_exit_status()
        sftp = client.open_sftp()
        try:
            if args.cmd == "put":
                sftp.put(args.local, args.remote)
                print(f"uploaded {args.local} -> {args.remote} ({sftp.stat(args.remote).st_size} bytes)")
            else:
                sftp.get(args.remote, args.local)
                print(f"downloaded {args.remote} -> {args.local} ({os.path.getsize(args.local)} bytes)")
        finally:
            sftp.close()
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
