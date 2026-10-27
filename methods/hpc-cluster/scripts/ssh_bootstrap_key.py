#!/usr/bin/env python3
"""Bootstrap passwordless SSH to an HPC login node, and write the ssh alias.

What it does
  1. logs in with a password (paramiko),
  2. installs your local PUBLIC key into ~/.ssh/authorized_keys on the cluster
     (idempotent, with correct 700/600 permissions),
  3. writes/updates an alias block in the local ~/.ssh/config,
  4. verifies that `ssh -o BatchMode=yes <alias>` really works.

The password is never stored or printed. Supply it via --password, the env var
named by --password-env (or the platform config), or an interactive prompt.

With --platform the parameters come from ~/.compchemkit/config.json:
    python ssh_bootstrap_key.py --platform mycluster
Without it, pass --host/--user explicitly:
    python ssh_bootstrap_key.py --host hpc.example.edu --user your_username --alias hpc
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover
    sys.exit("paramiko is required:  python -m pip install paramiko")

sys.path.insert(0, str(Path(__file__).resolve().parent))


def read_pubkey(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        sys.exit(f"public key not found: {p}\n"
                 f"create one with:  ssh-keygen -t ed25519 -f {p.with_suffix('')}")
    return p.read_text().strip()


def install_key(host: str, user: str, password: str, pubkey: str, port: int = 22) -> None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password,
                   timeout=25, banner_timeout=30, auth_timeout=30,
                   allow_agent=False, look_for_keys=False)
    # the public key contains spaces but no quotes, so single quoting is safe
    remote = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
        f"grep -qxF '{pubkey}' ~/.ssh/authorized_keys || echo '{pubkey}' >> ~/.ssh/authorized_keys; "
        "echo '--- authorized_keys entries:' $(grep -c . ~/.ssh/authorized_keys)"
    )
    _, out, err = client.exec_command(remote, timeout=40)
    print(out.read().decode().strip())
    msg = err.read().decode().strip()
    if msg:
        print("stderr:", msg)
    client.close()


def update_ssh_config(alias: str, host: str, user: str, keyfile: str, port: int = 22) -> Path:
    cfg = Path.home() / ".ssh" / "config"
    cfg.parent.mkdir(mode=0o700, exist_ok=True)
    text = cfg.read_text() if cfg.exists() else ""
    block = (f"Host {alias} {host}\n"
             f"    HostName {host}\n"
             f"    User {user}\n"
             f"    Port {port}\n"
             f"    IdentityFile {Path(keyfile).expanduser().as_posix()}\n"
             f"    IdentitiesOnly yes\n"
             f"    ServerAliveInterval 30\n"
             f"    ServerAliveCountMax 6\n")
    pattern = re.compile(rf"(?ms)^\s*Host\s+[^\n]*\b{re.escape(host)}\b[^\n]*\n(?:[ \t]+[^\n]*\n)*")
    if pattern.search(text):
        text = pattern.sub(block, text)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    cfg.write_text(text)
    print(f"updated {cfg}")
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="config.json path (default ~/.compchemkit/config.json)")
    ap.add_argument("--platform", default=None, help="platform name from the config file")
    ap.add_argument("--host", default=None)
    ap.add_argument("--user", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--pass-env", "--password-env", dest="password_env", default=None,
                    help="env var holding the password (default: from config, else HPC_PASS)")
    ap.add_argument("--password", default=None, help="password on the command line (avoid: shell history)")
    ap.add_argument("--key", default=None,
                    help="local key PAIR path (default: from config auth.key_path, else ~/.ssh/id_ed25519)")
    ap.add_argument("--alias", default=None, help="alias to write into ~/.ssh/config (default: platform name)")
    ap.add_argument("--no-config", action="store_true", help="do not touch ~/.ssh/config")
    args = ap.parse_args()

    if args.platform:
        import hpc_config
        plat, name = hpc_config.load(args.config, args.platform)
        auth = plat.get("auth") or {}
        host = args.host or plat["host"]
        user = args.user or plat["user"]
        port = args.port or int(plat.get("port") or 22)
        key = args.key or auth.get("key_path") or "~/.ssh/id_ed25519"
        password_env = args.password_env or auth.get("password_env") or "HPC_PASS"
        alias = args.alias or plat.get("ssh_alias") or name
    else:
        if not (args.host and args.user):
            sys.exit("need either --platform or --host and --user")
        host, user = args.host, args.user
        port = args.port or 22
        key = args.key or "~/.ssh/id_ed25519"
        password_env = args.password_env or "HPC_PASS"
        alias = args.alias or "hpc"

    password = args.password or os.environ.get(password_env) or getpass.getpass(f"password for {user}@{host}: ")
    pubkey_path = str(Path(key).expanduser()) + ".pub"
    pubkey = read_pubkey(pubkey_path)

    install_key(host, user, password, pubkey, port)
    if not args.no_config:
        update_ssh_config(alias, host, user, str(Path(key).expanduser()), port)

    print("verifying passwordless login ...")
    target = f"{user}@{host}" if args.no_config else alias
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", target,
                          "hostname; whoami; echo KEY_AUTH_OK"],
                         capture_output=True, text=True)
    print(res.stdout.strip() or res.stderr.strip())
    ok = "KEY_AUTH_OK" in res.stdout
    print("RESULT:", "OK - passwordless ssh works" if ok else
          "FAILED - check sshd AllowUsers / authorized_keys permissions")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
