#!/usr/bin/env python3
"""Platform configuration for the hpc-cluster skill.

Everything that differs between clusters (address, account, scheduler names,
software locations, environment setup) lives in ONE local JSON file, never in
this repository:

    ~/.compchemkit/config.json          (Windows: %USERPROFILE%\\.compchemkit\\config.json)

Resolution order for the config path:  --config  >  $HPC_CONFIG  >  ~/.compchemkit/config.json

Commands
    init      create/update one platform entry from command-line flags
    show      print the resolved configuration (secrets masked)
    get       print one dotted value, e.g.  get software.orca
    env       print the shell "export ..." block for a job script
    check     validate the file and test that the fields the other scripts need exist

Examples
    python hpc_config.py init --platform mycluster --host hpc.example.edu \\
        --user your_username --alias hpc --partition cpu192 --orca /opt/orca/orca
    python hpc_config.py show
    python hpc_config.py get software.orca
    python hpc_config.py env --platform mycluster > env.sh
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".compchemkit" / "config.json"

# fields the skill scripts rely on; missing ones are reported by `check`
REQUIRED = {
    "host": "login-node hostname or IP",
    "user": "remote account name",
}

DEFAULTS = {
    "port": 22,
    "ssh_alias": None,          # defaults to the platform name
    "auth": {"method": "key", "key_path": "~/.ssh/id_ed25519", "password_env": "HPC_PASS"},
    "scheduler": {"type": "slurm", "partition": None, "qos_default": None,
                  "qos_fast": None, "qos_debug": None, "cores_per_node": None},
    "workdir": None,
    "software": {},
    "env_setup": "",
    "notes_file": None,
}


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("HPC_CONFIG")
    if env:
        return Path(env).expanduser()
    return DEFAULT_CONFIG


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | None = None, platform: str | None = None) -> tuple[dict, str]:
    """Return (platform_dict, platform_name) with defaults filled in."""
    p = config_path(path)
    if not p.exists():
        sys.exit(f"config not found: {p}\n"
                 f"create it first, e.g.\n"
                 f"  python {Path(__file__).name} init --platform mycluster "
                 f"--host hpc.example.edu --user your_username\n"
                 f"or ask the agent: 'set up a new cluster for me' (it will ask the questions).")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    platforms = cfg.get("platforms") or {}
    name = platform or cfg.get("default_platform")
    if not name:
        sys.exit(f"{p} has no 'default_platform' and no --platform was given "
                 f"(available: {', '.join(platforms) or 'none'})")
    if name not in platforms:
        sys.exit(f"platform '{name}' is not in {p} (available: {', '.join(platforms) or 'none'})")
    plat = _deep_merge(DEFAULTS, platforms[name])
    if not plat.get("ssh_alias"):
        plat["ssh_alias"] = name
    plat["_name"] = name
    plat["_config_path"] = str(p)
    return plat, name


def mask(plat: dict) -> dict:
    """Copy of the platform dict with anything secret replaced by ***."""
    out = json.loads(json.dumps({k: v for k, v in plat.items() if not k.startswith("_")}))
    for key in ("password", "passphrase", "token"):
        if key in out:
            out[key] = "***"
    auth = out.get("auth")
    if isinstance(auth, dict) and auth.get("password"):
        auth["password"] = "***"
    return out


# --------------------------------------------------------------------- commands
def cmd_init(args) -> int:
    p = config_path(args.config)
    cfg = {}
    if p.exists():
        cfg = json.loads(p.read_text(encoding="utf-8"))
    platforms = cfg.setdefault("platforms", {})
    entry = platforms.get(args.platform, {})

    def put(dotted: str, value):
        keys = dotted.split(".")
        node = entry
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    mapping = {
        "host": args.host, "user": args.user, "port": args.port,
        "ssh_alias": args.alias, "workdir": args.workdir,
        "auth.method": args.auth, "auth.key_path": args.key,
        "auth.password_env": args.password_env,
        "scheduler.type": args.scheduler, "scheduler.partition": args.partition,
        "scheduler.qos_default": args.qos_default, "scheduler.qos_fast": args.qos_fast,
        "scheduler.qos_debug": args.qos_debug, "scheduler.cores_per_node": args.cores,
        "notes_file": args.notes,
    }
    for k, v in mapping.items():
        if v is not None:
            put(k, v)
    if args.software:
        for item in args.software:
            if "=" not in item:
                sys.exit(f"--software expects KEY=PATH, got '{item}'")
            k, v = item.split("=", 1)
            put(f"software.{k}", v)
    if args.env_setup is not None:
        put("env_setup", args.env_setup)

    platforms[args.platform] = entry
    cfg.setdefault("default_platform", args.platform)
    if args.make_default:
        cfg["default_platform"] = args.platform
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {p}  (platform '{args.platform}', default='{cfg['default_platform']}')")

    # Windows note: git-bash / MSYS silently rewrites remote POSIX paths such as
    # /opt/orca/orca into C:/.../opt/orca/orca. Detect the usual symptom so the
    # user is not left with a config that points at the local disk.
    flat = json.dumps(entry)
    if "node_modules" in flat or ":/" in flat and "/opt/" in flat:
        print("\nWARNING: some paths look like they were rewritten by the local shell\n"
              "         (git-bash/MSYS path conversion). Remote paths must be stored verbatim.\n"
              "         Re-run with:  MSYS_NO_PATHCONV=1 python hpc_config.py init ...\n"
              "         or edit the JSON file directly.")
    return 0


def cmd_show(args) -> int:
    plat, name = load(args.config, args.platform)
    print(f"# platform: {name}   (config: {plat['_config_path']})")
    print(json.dumps(mask(plat), indent=2, ensure_ascii=False))
    return 0


def cmd_get(args) -> int:
    plat, _ = load(args.config, args.platform)
    node = plat
    for k in args.key.split("."):
        if not isinstance(node, dict) or k not in node:
            sys.exit(f"'{args.key}' is not set for this platform")
        node = node[k]
    print("" if node is None else node)
    return 0


def cmd_env(args) -> int:
    """Shell snippet that a job script can `source` (or paste) to get the environment."""
    plat, _ = load(args.config, args.platform)
    lines = ["# generated by hpc-cluster/scripts/hpc_config.py -- source this in a job script"]
    if plat.get("env_setup"):
        lines.append(plat["env_setup"].rstrip())
    for k, v in (plat.get("software") or {}).items():
        if v:
            lines.append(f'export HPC_{k.upper()}="{v}"')
    print("\n".join(lines))
    return 0


def cmd_check(args) -> int:
    plat, name = load(args.config, args.platform)
    problems = []
    for field, why in REQUIRED.items():
        if not plat.get(field):
            problems.append(f"missing '{field}' ({why})")
    if not plat.get("env_setup") and not (plat.get("software") or {}):
        problems.append("neither 'env_setup' nor 'software' is set: job scripts will not find any binary")
    sched = plat.get("scheduler") or {}
    if not sched.get("partition"):
        problems.append("scheduler.partition is not set")
    if not sched.get("qos_default"):
        problems.append("scheduler.qos_default is not set (fine only if the cluster has no QOS)")
    print(f"platform '{name}' -> {plat.get('user')}@{plat.get('host')}:{plat.get('port')} "
          f"(alias: {plat.get('ssh_alias')})")
    print(f"  scheduler : {sched.get('type')} partition={sched.get('partition')} "
          f"qos_default={sched.get('qos_default')} qos_fast={sched.get('qos_fast')}")
    print(f"  workdir   : {plat.get('workdir')}")
    for k, v in (plat.get("software") or {}).items():
        print(f"  software  : {k:10s} {v}")
    if plat.get("notes_file"):
        print(f"  notes     : {plat['notes_file']}  (platform-specific gotchas, keep it next to this skill)")
    if problems:
        print("\nPROBLEMS:")
        for pr in problems:
            print("  - " + pr)
        return 1
    print("\nOK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="path to config.json (default: ~/.compchemkit/config.json)")
    ap.add_argument("--platform", default=None, help="platform name (default: default_platform)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create or update one platform entry")
    p.add_argument("--platform", required=True)
    p.add_argument("--host")
    p.add_argument("--user")
    p.add_argument("--port", type=int)
    p.add_argument("--alias", help="ssh config alias to use (default: the platform name)")
    p.add_argument("--auth", choices=["key", "password"])
    p.add_argument("--key", help="private key path for key auth")
    p.add_argument("--password-env", help="env var that holds the password (never store the password itself)")
    p.add_argument("--scheduler", choices=["slurm", "pbs", "lsf", "none"])
    p.add_argument("--partition")
    p.add_argument("--qos-default")
    p.add_argument("--qos-fast")
    p.add_argument("--qos-debug")
    p.add_argument("--cores", type=int, help="cores per node")
    p.add_argument("--workdir", help="remote project root used in examples")
    p.add_argument("--software", action="append", help="KEY=PATH, repeatable (orca, xtb, multiwfn, python, ...)")
    p.add_argument("--env-setup", help="shell snippet prepended in job scripts (module load / PATH exports)")
    p.add_argument("--notes", help="platform note file, e.g. platforms/mycluster.md")
    p.add_argument("--make-default", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("show", help="print the resolved config (secrets masked)")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("get", help="print one dotted value")
    p.add_argument("key")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("env", help="print the shell export block for job scripts")
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("check", help="validate the config")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
