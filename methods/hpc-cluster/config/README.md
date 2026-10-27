# 配置：让这套 skill 适配你自己的超算

> 仓库里**没有任何**集群地址、账号、密码、真实路径。第一次使用某个集群时，
> Agent 会先问你几个问题，然后把答案写进**本机**的配置文件；之后所有脚本都从这里读。

## 1. 配置放在哪里

| 位置 | 说明 |
|---|---|
| `~/.compchemkit/config.json` | 默认位置（Windows：`%USERPROFILE%\.compchemkit\config.json`） |
| `$HPC_CONFIG` | 环境变量指向别的路径时优先用它 |
| `--config PATH` | 单次覆盖，优先级最高 |

**永远不要**把它放进本仓库或任何 git 仓库：`.gitignore` 已经排除了 `config.local.*`、`*.local.json`、`.env`、`*.key`、`*.pem`。

## 2. 首次配置要问用户什么

Agent 按顺序问（能一次问完最好）：

1. **登录节点**：host（域名或 IP）、端口（默认 22）
2. **账号**：用户名
3. **认证方式**：key（推荐，需要已有或新生成的私钥）还是 password
   - password 只写入**环境变量名**（如 `HPC_PASS`），**不要把密码本身写进文件**；真的需要时可以放系统凭据管理器
4. **调度器**：Slurm / PBS / LSF；分区名、默认 QOS、快速 QOS、调试 QOS、每节点核数
5. **工作根目录**：远程项目根路径（例子里用 `/path/to/project`）
6. **软件位置**：orca、xtb、multiwfn、python 的绝对路径（同一集群不同账号也可能不同）
7. **环境准备**：登录后需要 `module load` 什么，或者要 `export` 哪些变量（`env_setup`，一段 bash 片段）
8. **平台特殊设置**：有没有已知坑（队列上限、`--mem` 不可用、节点的 NUMA 结构…）→ 让 Agent 在 `platforms/<name>.md` 里记下来

## 3. 三种写法（等价的）

```bash
# ① 一条命令建好
python scripts/hpc_config.py init \
    --platform mycluster --host hpc.example.edu --user your_username \
    --alias hpc --partition cpu192 --qos-default regular --qos-fast premium \
    --cores 192 --workdir /path/to/project \
    --software orca=/opt/orca/orca --software xtb=/opt/xtb/bin/xtb \
    --env-setup 'module load openmpi/4.1.5' --make-default

# ② 复制模板再改
cp config/platforms.example.json ~/.compchemkit/config.json   # 然后编辑

# ③ 让 Agent 帮你写（它会在你回答第 2 节的问题之后调用 ①）
```

> **Windows / git-bash 的路径改写**：MSYS 会把命令行里的 `/opt/orca/orca` 当成 Unix 路径
> 改写成 `C:/.../opt/orca/orca`。所以 `init` 传远端路径时必须关掉转换：
>
> ```bash
> MSYS_NO_PATHCONV=1 python scripts/hpc_config.py init --platform mycluster \
>     --software orca=/opt/orca/orca --workdir /public/home/you/project ...
> ```
>
> 最稳的做法是直接编辑 JSON 文件。`init` 识别到被改写的路径会打印 WARNING。

## 4. 字段说明

| 字段 | 必填 | 含义 |
|---|---|---|
| `host` | ✅ | 登录节点域名 / IP |
| `port` | | SSH 端口，默认 22 |
| `user` | ✅ | 远程账号 |
| `ssh_alias` | | 本机 `~/.ssh/config` 里的别名（默认=平台名），脚本用它 `ssh` |
| `auth.method` | | `key`（默认）或 `password` |
| `auth.key_path` | | 私钥路径（`--platform` 模式下的 `remote.py`/`ssh_bootstrap_key.py` 用它） |
| `auth.password_env` | | 保存密码的**环境变量名**，不是密码本身 |
| `scheduler.type` | | `slurm` / `pbs` / `lsf` / `none`（脚本目前按 Slurm 语义生成命令） |
| `scheduler.partition` | | 默认分区 |
| `scheduler.qos_default` / `qos_fast` / `qos_debug` | | 普通/加急/调试队列名；没有 QOS 的集群留空 |
| `scheduler.cores_per_node` | | 每节点核数，用来判断"要不要整节点" |
| `workdir` | | 远程项目根，示例命令里替换 |
| `software.*` | | 可执行文件绝对路径；`hpc_config.py env` 会导出成 `$HPC_ORCA` 等 |
| `env_setup` | | 一段 bash，粘到作业脚本开头（`module load` / `PATH`） |
| `notes_file` | | 平台专属说明文件，相对 skill 目录，例如 `platforms/precision.md` |

## 5. 自检

```bash
python scripts/hpc_config.py check                      # 字段是否齐全
python scripts/ssh_bootstrap_key.py --platform mycluster # 打通免密（password 模式）
ssh <alias> "hostname; whoami; sinfo"                    # 连通性
python scripts/remote.py exec --platform mycluster "sinfo -o '%P %a %F'"
```

`check` 通过 + `ssh <alias>` 能进 + 交一个 1 核小作业能跑完 = 配置完成。

## 6. 平台专属说明怎么长出来

第一次在某个集群踩到坑时，**当场**写进 `platforms/<name>.md`（照 `platforms/_TEMPLATE.md` 的格式）：
现象 → 原因 → 处理。只写这个集群特有的东西，通用的坑写在 `SKILL.md` 里，避免两边重复。
