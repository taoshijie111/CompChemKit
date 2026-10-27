---
name: hpc-cluster
description: Use when running computational-chemistry jobs on an SSH HPC cluster — connecting and setting up passwordless SSH, choosing partition/QOS/core count, writing Slurm batch scripts that survive the cluster's quirks, submitting/monitoring/cancelling jobs, transferring files with checksum verification, or watching a long multi-stage batch from the local machine and getting woken when a job ends. Cluster addresses, accounts, scheduler names and software paths live in a LOCAL config file (~/.compchemkit/config.json), never in this repo: on first use the skill asks the user for them and writes them. Per-cluster gotchas live in platforms/<name>.md.
whenToUse: 需要连接一台超算（SSH）做量化计算、上传下载数据、提交或监控 Slurm 作业、给几天级/多层级任务挂本地看门狗、或者遇到 CRLF 报错、脚本秒退且 .err 里是 /var/spool/slurm、--mem 不可用、作业长期 PD (Priority)、ORCA 读不了 xyz、mpirun not found、not enough slots、隐式 OOM（Slurm 说 COMPLETED 但频率没算完）等问题时。
---

# 超算集群：连接、提交、监控、下载

一套**与具体集群无关**的流程。集群地址、账号、调度器名字、软件路径全部放在
本机配置文件里（`~/.compchemkit/config.json`），仓库里不含任何私有信息。
这个集群特有的坑写在 `platforms/<name>.md`。

本 skill 只负责「怎么在这台集群上把任务提交并跑起来」，**不规定计算方法**；
算什么样的体系、用什么泛函/基组属于 `methods/` 下其它 skill 的事。

---

## 0. 首次使用：先建配置（必做）

如果还没有配置文件，**先问用户**下面这些，然后用一条命令写进去。不要猜测，不要从别处复制。

| # | 要问的 | 示例 | 写进 |
|---|---|---|---|
| 1 | 登录节点（域名或 IP） | `hpc.example.edu` | `host` |
| 2 | SSH 端口 | `22` | `port` |
| 3 | 账号 | `your_username` | `user` |
| 4 | 认证方式：key / password | 推荐 key | `auth.method` |
| 5 | 私钥路径（key 模式） | `~/.ssh/id_ed25519` | `auth.key_path` |
| 6 | 密码放在哪个**环境变量**里（password 模式） | `HPC_PASS` | `auth.password_env` |
| 7 | 本机 ssh 别名 | `hpc` | `ssh_alias` |
| 8 | 调度器 + 分区 + QOS 名字 + 每节点核数 | Slurm / `cpu192` / `regular`,`premium` / 192 | `scheduler.*` |
| 9 | 远程项目根目录 | `/path/to/project` | `workdir` |
| 10 | 软件绝对路径 | orca、xtb、multiwfn、python | `software.*` |
| 11 | 登录后需要的 `module load` / `export` | `module load openmpi/4.1.5` | `env_setup` |
| 12 | 已知的平台特殊设置 | 见第 6 节 | `platforms/<name>.md` |

**密码本身永远不进文件**：只记环境变量名；需要长期保存时用系统凭据管理器。

```bash
python scripts/hpc_config.py init \
    --platform mycluster --host hpc.example.edu --user your_username --alias hpc \
    --partition cpu192 --qos-default regular --qos-fast premium --qos-debug debug \
    --cores 192 --workdir /path/to/project \
    --software orca=/opt/orca/orca --software xtb=/opt/xtb/bin/xtb \
    --env-setup 'module load openmpi/4.1.5' --make-default

python scripts/hpc_config.py check       # 字段齐全性
python scripts/hpc_config.py show        # 看最终生效的值（密码打码）
```

> **Windows / git-bash 注意**：MSYS 会把 `/opt/orca/orca` 这类**远端** POSIX 路径悄悄改写成
> `C:/.../opt/orca/orca`。用 `init` 传路径时要加 `MSYS_NO_PATHCONV=1`：
>
> ```bash
> MSYS_NO_PATHCONV=1 python scripts/hpc_config.py init --platform mycluster \
>     --software orca=/opt/orca/orca ...
> ```
>
> 或者直接编辑 `~/.compchemkit/config.json`（更稳）。`init` 检测到这种改写会打印 WARNING。

**配置冒烟测试（三步都要过）**

```bash
python scripts/ssh_bootstrap_key.py --platform mycluster   # ① 打通免密（password 模式）
ssh hpc "hostname; whoami; sinfo -o '%P %a %F'"            # ② 能进、能看到分区
python scripts/remote.py exec --platform mycluster "squeue -u \$USER"   # ③ 能远程执行
```

④ 再交一个 **1 核小作业**走通整条链路（见 §3.4）。这四步过了，再碰大作业。

---

## 1. 配置文件

| 项 | 说明 |
|---|---|
| 默认位置 | `~/.compchemkit/config.json`（Windows `%USERPROFILE%\.compchemkit\config.json`） |
| 覆盖 | `$HPC_CONFIG` 环境变量，或单次 `--config PATH` |
| 模板 | `config/platforms.example.json` |
| 说明 | `config/README.md`（完整字段表 + 三种写法） |
| 敏感 | 不进 git；`.gitignore` 已排除 `*.local.json`、`.env`、`*.key`、`*.pem` |

常用命令：

```bash
python scripts/hpc_config.py show                       # 全部平台（密码打码）
python scripts/hpc_config.py get scheduler.partition    # 单个值，便于脚本拼接
python scripts/hpc_config.py env > env.sh               # 生成作业用的 export 片段
python scripts/hpc_config.py check --platform mycluster # 体检
```

多集群：`platforms` 下可以并列多份，`default_platform` 指定默认，任何脚本都能用
`--platform <name>` 临时切换。

---

## 2. 连接与传输

### 2.1 免密登录

`scripts/ssh_bootstrap_key.py` 做四件事：密码登录 → 把公钥追加到远端
`~/.ssh/authorized_keys`（幂等、700/600 权限）→ 在本机 `~/.ssh/config` 写别名块 →
`ssh -o BatchMode=yes <alias>` 验证。

```bash
python scripts/ssh_bootstrap_key.py --platform mycluster
HPC_PASS=xxx python scripts/ssh_bootstrap_key.py --platform mycluster   # 密码从环境变量取
```

集群禁止装公钥时，用 `scripts/remote.py`（paramiko，支持 exec/put/get）兜底。

### 2.2 传文件

```bash
scp -r ./inputs/*  hpc:/path/to/project/inputs/
scp -O ./script.sh hpc:/path/to/project/            # -O：老集群不支持 SFTP 扩展时用
# 多文件/大文件先打包再传（更快，可断点）
ssh hpc "tar czf - -C /path/to project/sub" > sub.tgz
tar czf - ./sub | ssh hpc "tar xzf - -C /path/to/project"
```

**传完必须校验**（结构文件尤其）：

```powershell
$local  = (Get-FileHash .\x.xyz -Algorithm MD5).Hash.ToLower()
$remote = ssh hpc "md5sum /path/to/project/x.xyz | cut -d' ' -f1"
"$local == $remote"
```

### 2.3 文本文件的三个硬规则

1. **LF 换行**。Windows 写的 `.slurm` / `.inp` 如果是 CRLF，`sbatch` 直接报
   `Batch script contains DOS line breaks`；某些程序只是悄悄读错。用 `write` 工具
   或 `[System.IO.File]::WriteAllText($p, $t, [System.Text.UTF8Encoding]::new($false))` 生成，
   **不要**用会写 CRLF 的 `Set-Content`。
2. **文件末尾必有一个换行**。ORCA 读最后一行 `* xyzfile ... start.xyz` 时若没有结尾 `\n`，
   会报 `ORCA_ReadXYZFile::Error` 并打印一长串乱码文件名。PowerShell here-string
   的结尾换行不会进字符串，生成后要显式补。自检：`[System.IO.File]::ReadAllBytes($f)[-1] -eq 10`。
3. **不要在远端用一行 `python -c "..."`**。引号要过本地 shell + ssh 两层转义，
   极易坏。改成「本地写脚本 → scp → 远端 `python3 file.py`」。

---

## 3. Slurm 提交

### 3.1 通用坑（与集群无关，先看这个）

| 现象 | 原因 | 处理 |
|---|---|---|
| 作业 2–6 秒就失败，`.err` 里是 `/var/spool/slurm/...` 不存在 | Slurm 把批处理脚本**复制到 spool 目录**再执行，`$0`/`BASH_SOURCE`/`dirname` 指向 spool | 用 `$SLURM_SUBMIT_DIR`，或 `sbatch --export=ALL,STAGE="$PWD"`；**永远不要用 `BASH_SOURCE` 推项目根** |
| `Batch script contains DOS line breaks` | CRLF | 转 LF（§2.3） |
| `Memory specification can not be satisfied` | 节点 `RealMemory` 配置异常（有的集群是 1 MB） | 先查 `platforms/<name>.md`，多半要**删掉 `--mem`** |
| 作业长期 `PD (Priority)`，`squeue --start` 说几小时后 | 优先级/回填（backfill）挤不进空隙；有些集群还有大量你看不见的别人作业（`PrivateData=jobs`） | 核数大或墙钟长就换高优先级 QOS；判据见 §3.2 |
| `squeue` 看不到别人的作业 | `PrivateData=jobs` | 正常；判断空闲看 `sinfo`，别指望看到谁在跑 |
| 32 核也要排很久 | 需要**同一节点上连续 32 个空闲核**，空闲核常被碎片化 | 先看每节点空闲数（`sinfo -N -o '%N %t %C'`）再定核数 |
| 短作业秒起、长作业一直挂着 | 短作业能回填进空隙，长作业不能 | 要么缩短墙钟，要么升优先级 QOS |
| `scontrol show job 1,2,3` 报 `Invalid job id` | 它不接受逗号列表 | 批量查用 `sacct -j 1,2,3` |
| 作业"成功"但输出没算完 | 见 §3.3 隐式 OOM | 永远不要只信 Slurm 的 `COMPLETED` |

### 3.2 选 QOS / 核数

不同集群的 QOS 名字与上限不同，从配置里读（`scheduler.qos_default` / `qos_fast` / `qos_debug`），
并在 `platforms/<name>.md` 里记下它们的真实语义。通用判据：

- **先看核数，再看墙钟**：要几乎整节点（≥50% 核）或墙钟接近默认 QOS 上限 → 走快速 QOS；
  小的、短的 → 走默认 QOS（并发名额多，能一次铺开几十个）。
- 两个 QOS 的并发名额通常**互不占用**，所以正确用法是"小的撒默认、关键路径的放快速"，
  而不是全塞快速（快速 QOS 往往只有个位数并发）。
- 提交前先看空闲分布：

```bash
sinfo -p <partition> -N -o '%N %t %C'          # 每节点 分配/空闲/其它/总
sinfo -p <partition> -o '%C'                   # 分区汇总
squeue -u $USER --start -o '%.10i %.16j %.20S %R'
```

### 3.3 隐式 OOM：Slurm 说 COMPLETED，其实没算完

**这是最容易误判的坑。** 表现：`sacct` 里 `COMPLETED`、exit 0，但输出文件里没有
`ORCA TERMINATED NORMALLY`，或者解析 Hessian 出现 −8000 cm⁻¹ 这种离谱虚频。

原因：某个 rank 被内核 `signal 9` 杀掉，但批处理脚本继续往下走并 `exit 0`。

诊断与处理：

```bash
sacct -j <id> --format=JobID,State,ExitCode,Elapsed,MaxRSS   # 看 MaxRSS 是否爆到几百 GB
grep -c "ORCA TERMINATED NORMALLY" freq.out                  # =0 就是没算完
grep -E "signal 9|error termination in" freq.out
```

- 降并发（99 → 64 → 48）往往比加内存更有效；
- 作业开始时按 `/proc/meminfo` 的 `MemAvailable` **动态**算每进程内存：
  `%maxcore = MemAvailable × 55% / nprocs`（并设上下限）；
- 名义内存 ≠ 实际峰值，实测可以到名义值的 1.4 倍。

### 3.4 大作业之前先跑 1 核自检（强烈推荐）

大作业排队几小时到几天，脚本问题（路径、关键词、换行、退出码）排在后面才发现很亏。
先用调试 QOS 交一个 **1 核、小体系** 的作业，几分钟把整条链路走通：

```bash
sbatch -p <partition> --qos=<debug> -c 1 -t 00:30:00 \
       --export=ALL,STAGE="$PWD" smoke_1core.slurm
```

它验证：路径解析、二进制与动态库、关键词解析、几何循环、退出码、输出落盘位置。
**测不到的只有 N 核 MPI 启动**——那只能靠真实作业，所以失败要看第一个作业头几分钟的输出。

### 3.5 提交与监控

```bash
ssh hpc "cd /path/to/project/jobs/sys1 && sbatch ../slurm_generic.sh"
ssh hpc 'squeue -u $USER -o "%.10i %.14j %.9P %.2t %.10M %R"'
ssh hpc 'scontrol show job <id> | tr " " "\n" | grep -E "JobState|Reason|RunTime|NumCPUs|CPU_IDs"'
ssh hpc 'sacct -j <id> --format=JobID,State,ExitCode,Elapsed,MaxRSS'
ssh hpc 'sacct -j <id1>,<id2> --format=JobID,JobName%12,State,ExitCode,Elapsed,NodeList'
ssh hpc "scancel <id>"
```

模板：`templates/slurm_generic.sh`（通用）、`templates/slurm_orca_optfreq.sh`
（Opt→Freq 串接，收敛才接着算）、`templates/slurm_xtb_ohess.sh`。

---

## 4. 长时间 / 多层级任务：本地看门狗

排队几小时到几天、又有"优化 → 频率 → 单点"这种层级依赖时，既不能靠对话里反复轮询，
也不该让脚本替人做决策（失败/未收敛需要判断，自动重投容易把错误结构传下去）。
用 `scripts/watch_jobs.ps1`：

- **只在本地跑**，只 `ssh` 查 `squeue` / `sacct`；不占集群 CPU、不占队列槽位、不提交任何作业。
- **监视范围用正则从 `squeue` 现发现**（配置里的 `patterns` 匹配**作业名**），
  所以重投的作业、`_a2` 新 attempt、新加的体系都会自动纳入，**不用改 job id**。
- **退出即通知**：任一被监视作业离开队列就退出，报告里给
  ① 哪个作业结束 ② `sacct` 的 State/ExitCode/Elapsed ③ 还在跑的清单 ④ `status_command` 的输出。

```powershell
pwsh -File scripts/watch_jobs.ps1 -Status                  # 一次性状态，立即返回
pwsh -File scripts/watch_jobs.ps1 -WakeOnlyOnTrouble       # 启动（必须 run_in_background）
pwsh -File scripts/watch_jobs.ps1 -Config .\watch\jobs.json -Platform mycluster
```

**机制与限制（必须知道）**

- harness 的"作业完成通知"绑在**它启动的那个后台进程**上；脚本自己 `Start-Process` 起的
  子进程不在跟踪列表里，所以**看门狗不能自动重挂**——每次被叫醒后，在同一个回合里重新启动一次。
- 唤醒粒度二选一：默认**每个作业结束都叫**（多层级任务的下一步未必自动接续，需要人衔接）；
  加 `-WakeOnlyOnTrouble` 只在异常/全部完成时叫（下游已用 `--dependency=afterok` 自动接续时用）。
- 本地进程随会话关闭而消失；`watch_jobs.log` 是持久记录，随时可查。
- 集群侧的等价物是 `scripts/watch_queue.sh`（等到队列空再打印，**无人通知**），两者互补。

典型回合：

```
看门狗退出 (exit 0)
  → 读报告：哪个作业结束、收敛还是 exit N、进度如何
  → 决策：优化收敛 → 提交下游；优化未收敛 → 从最后一帧续跑；异常退出 → 读输出定位
  → 同一个回合里重新以 run_in_background 启动看门狗
```

**"决策"永远由人/agent 做，脚本只负责叫醒**——这是刻意设计。

---

## 5. 软件环境注入

不同集群、同一集群不同账号的软件路径都不一样，**不要写死在作业脚本里**。
用配置生成一个 `env.sh`，跟着项目上传一次，所有作业脚本 source 它：

```bash
python scripts/hpc_config.py env > env.sh
scp -O env.sh hpc:/path/to/project/env.sh
```

`env.sh` 里是 `env_setup`（`module load` / `PATH`）+ `export HPC_ORCA=...`、`HPC_XTB=...`，
作业脚本开头：

```bash
if [ -f "$SLURM_SUBMIT_DIR/env.sh" ]; then source "$SLURM_SUBMIT_DIR/env.sh"; fi
```

ORCA / xTB 的**关键词**属于方法层（见 `methods/` 下其它 skill），这里只保证
"能启动、能用对核数、能拿到正确退出码"。

---

## 6. 平台专属说明（`platforms/`）

| 文件 | 内容 |
|---|---|
| `platforms/_TEMPLATE.md` | 新平台的写法模板 |
| `platforms/precision.md` | 精准 CPU 集群：QOS 表、`--mem` 不可用、`PrivateData=jobs`、spool 坑、隐式 OOM、NUMA/单 socket、实测基准 |

**规则**

- 通用的坑写在本文档，平台特有的写在 `platforms/<name>.md`，两边**不要重复**。
- 第一次在某个集群踩到坑时**当场**记进去：现象 → 原因 → 处理 + 实测日期。
- 配置里用 `"notes_file": "platforms/<name>.md"` 关联；换集群时先读它再动手。
- 新集群第一次用：先按 `_TEMPLATE.md` 建文件，把已知信息填上，剩下的边用边补。

---

## 7. 目录约定（好用）

```
项目/
├── inputs/<体系>/{start.xyz,opt.inp,freq.inp}   # 只放输入
├── jobs/*.slurm                                 # 只放提交脚本
├── watch/watch_jobs.json                        # 看门狗配置 + watch_jobs.log
└── results/<体系>/{opt.xyz,opt.out,freq.out,summary.csv}
```

服务器侧同一套：`<root>/<step>/<system>/`，在体系目录里 `sbatch ../xxx.slurm`
（这样 `$SLURM_SUBMIT_DIR` 就是体系目录）。中间文件（`*.tmp`、`*.gbw`、`hessian`）
确认收敛后清理，保留结构 + 原始输出 + 提交脚本即可。

---

## 8. 报错排查（通用部分）

| 报错/现象 | 处理 |
|---|---|
| `mpirun: command not found` | MPI 不在默认 PATH：在 `env_setup` 里加 `export PATH=<mpi>/bin:$PATH` |
| `There are not enough slots available`（OpenMPI 启动 ORCA） | Slurm 只给 1 个 task，OpenMPI 以为只有 1 个 slot：`export OMPI_MCA_rmaps_base_oversubscribe=1` |
| 作业跑得比预期慢一个数量级、且不同任务差异巨大 | 进程跨 NUMA/socket 迁移：`hwloc_base_binding_policy=core` + `rmaps_base_mapping_policy=core`，并检查 `CPU_IDs` |
| `ORCA_ReadXYZFile::Error` + 乱码文件名 | 输入文件末尾缺换行（§2.3） |
| `Batch script contains DOS line breaks` | 转 LF |
| 作业秒退、`.err` 指向 spool | 用 `$SLURM_SUBMIT_DIR`（§3.1） |
| `No memory left for COSX RHS` / `error termination in SCF RESPONSE` | 解析频率内存不够：降核数 + 按 `MemAvailable` 动态设 `%maxcore`（§3.3） |
| 远端 `python -c` 引号报错 | 写文件 → scp → 远端执行（§2.3） |
| `$var` 在本地就被展开 | 远端命令用**单引号** here-string；或把脚本传上去跑 |

平台特有的报错看 `platforms/<name>.md`。

---

## 9. 附带文件

```
config/platforms.example.json   配置模板（复制到 ~/.compchemkit/config.json）
config/README.md                配置字段表 + 首次配置问答清单
scripts/hpc_config.py           读写/校验配置，生成 env.sh
scripts/ssh_bootstrap_key.py    密码 → 装公钥 → 写 ssh 别名 → 验证免密
scripts/remote.py               paramiko 版 exec / put / get（无 key 时兜底）
scripts/watch_jobs.ps1          本地看门狗（只通知不决策）
scripts/watch_jobs_config.example.json  看门狗配置模板
scripts/watch_queue.sh          服务器端：等队列空再打印（无人通知）
platforms/_TEMPLATE.md          新平台说明的模板
platforms/precision.md               精准集群的专属说明
templates/slurm_generic.sh      通用 Slurm 作业模板
templates/slurm_orca_optfreq.sh ORCA Opt→Freq 串接模板
templates/slurm_xtb_ohess.sh    xTB 优化+频率模板
templates/orca_opt.inp          ORCA 优化输入（可直接用的起点）
templates/orca_freq.inp         ORCA 频率输入（QuasiRRHO）
```
