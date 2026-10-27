# 平台专属说明：中科大超算（Slurm 的 CPU 集群）

> 这是本 skill 最早沉淀下来的那个集群。下面的内容都与该集群的实现细节有关，
> 换成别的集群请不要照搬；配置项（地址、账号、软件路径）一律走
> `~/.compchemkit/config.json`，**不写在这里**。
>
> 实测日期：2026-08 ~ 2026-10。

## 0. 基本信息

| 项 | 值 |
|---|---|
| 调度器 | Slurm 20.11.9 |
| 登录节点 | `login01`（CentOS 8，OpenSSH 8.0，只允许 publickey / password 认证，**无** sshpass） |
| 计算分区 | `cpu192`：节点 `cuNN`，每节点 **192 核**（2 × AMD EPYC 9A14 96 核），内存 755 GB |
| 备用分区 | `cpu192-mem-64G`：长期 down/maint，实际排不上 |
| 外网 | **登录节点和计算节点都不能访问 GitHub**；pip/conda 镜像也不通 → 要联网的东西在本机下载后上传 |
| 文件系统 | `/public` 是并行文件系统，容量很大、无明显配额限制；家目录也在 `/public/home/<user>` |
| 节点本地盘 | 计算节点的 `/tmp` 是**节点本地**的，不和登录节点共享。作业写到 `/tmp` 的输出跑完就没了；测试输出一律写 `$HOME` 或 `$SLURM_SUBMIT_DIR` |

## 1. 队列与 QOS

| QOS | 优先级 | 墙钟上限 | 单用户并发 | 说明 |
|---|---|---|---|---|
| `regular` | 1000 | 1 天 | 50 | 默认；额度宽，但优先级低 |
| `premium` | 10000 | 2 天 | **5** | 加急；5 个并发名额是硬限制 |
| `debug` | 10 | 1 小时 | 2 | **是 QOS 不是分区**：`-p debug` 会报 `invalid partition name`，要写 `-p cpu192 --qos=debug` |
| `custom` | 10 | 无限制 | — | 能跑完，但排队很靠后 |

**选队列判据（先看核数，再看墙钟）**

| 单片作业需求 | 用哪个 | 理由 |
|---|---|---|
| ≤ 64 核且 ≤ 24 h | `regular` | 空闲核常以 32/64 碎片出现，regular 容易排上，50 并发可一次铺开二三十个 |
| ≥ 96 核（要几乎整节点） | `premium` | regular 优先级低，抢不到大块，会长期 `PD (Priority)` |
| > 24 h（不管几核） | `premium` | regular 硬上限 1 天，超了必被杀 |

**踩过的坑（2026-10-22）**：把 12 个 192 原子复合物的 Freq 从 64 核提到 96 核但**仍留在 regular**，
以为"并发多就快"，结果 96 核在 regular 下几乎排不上；正确做法是核数 ≥96 就走 premium。

### 1.1 `squeue` 看不到别人的作业

集群默认 **`PrivateData=jobs`**：`squeue -a` 也只能看到自己的作业。所以

- 判断"集群忙不忙"只能看 `sinfo`（节点/核的分配情况），不要指望看到谁在跑；
- 自己的作业长期 `PD (Priority)` 时，很可能是**别人大量 pending 作业**在排队（你看不见），
  不是你的作业有问题。

**实测（2026-10-27）**：6 个 32 核 / 24 h 的作业全 `PD (Priority)`，`squeue --start` 给的预计开始时间是 **+37 h**，
而当时有 3 个节点各空着 100+ 核。原因不是核数：同样 32 核但 `-t 5min` 的测试作业**立刻**起飞，
同样 32 核但 `-t 24h` 的一直挂着——**长墙钟作业挤不进 backfill 的空隙**。
把作业 `scontrol update jobid=<id> qos=premium` 后**立刻**上机。
（注：`StartTime` 为 `Unknown` 或 +N 天时，先怀疑这个，别怀疑自己的脚本。）

## 2. 节点与硬件特性

- 每节点 2 socket × 96 核：**CPU id 0–95 = socket0，96–191 = socket1**。
- 节点 `RealMemory` 被配成 `1`（MB），所以 **`--mem` 不可用**（报
  `sbatch: error: Memory specification can not be satisfied`），也意味着 **Slurm 不跟踪内存**，
  同节点共置的作业会互挤物理内存。
- 内存核算只能靠自己：`%maxcore × nprocs` 是名义值，实际峰值可到名义值的 1.4 倍
  （见 §3.2 隐式 OOM）。

## 3. 已知坑

### 3.1 作业 2–6 秒就失败，`.err` 里是 `/var/spool/slurm/d/...` 不存在

- **现象**：`Elapsed 00:00:02~06`、`ExitCode 2:0`，作业目录里什么输出都没有。
- **原因**：Slurm 把批处理脚本**复制到 `/var/spool/slurm/d` 再执行**，所以 `$0`、`BASH_SOURCE`、
  `dirname` 都指向 spool，而不是你提交时的目录；用它们推项目根必然算错。
- **处理**：用 `$SLURM_SUBMIT_DIR`，或提交时显式传 `--export=ALL,STAGE="$PWD"`，
  脚本里 `STAGE_DIR="${STAGE:-${SLURM_SUBMIT_DIR}}"`。**永远不要用 `BASH_SOURCE` 推项目根。**

### 3.2 隐式 OOM：Slurm 显示 COMPLETED，但频率根本没算完

- **现象**：`sacct` 里是 `COMPLETED`、exit 0；但 `freq.out` 里没有 `ORCA TERMINATED NORMALLY`，
  CP-SCF 停在某一轮；或者出现 −8000 cm⁻¹ 这种离谱虚频；ORCA 报
  `error termination in SCF RESPONSE`。
- **原因**：96 进程 × `%maxcore 4000` 名义 384 GB，`sacct` 的 `MaxRSS` 实测 **526–548 GB**，
  某个 rank 被内核 `signal 9` 杀掉；批处理脚本继续往下走并 `exit 0`，所以 Slurm 认为成功。
- **处理**：
  1. 诊断：`sacct -j <id> --format=JobID,State,MaxRSS`（看到 500 GB 级 MaxRSS 就是它）+
     `grep -c "ORCA TERMINATED NORMALLY" freq.out`（=0 就是没算完）。
  2. 降核数到 64，并在脚本启动时按 `/proc/meminfo` 的 `MemAvailable` 动态算
     `%maxcore = MemAvailable×55% / nprocs`（上限 4000，下限 1500）。
  3. **别只看 Slurm 的 COMPLETED 就以为算完了。**

### 3.3 单 socket 与 core binding：同一批任务快 14 倍

- **现象**：同一批工作量耗时在 7.6 min ~ 105 min 之间波动；`scontrol show job <id> -d` 看到
  `CPU_IDs=32-95,128-159` 这类**跨两个 socket**的分配。
- **原因**：OpenMPI 默认 `binding_policy=none` 时进程会在两个 socket 间迁移，内存落到远端 NUMA 域；
  而 meta-GGA 的 XC 格点 + RI-J + CPCM 是访存带宽密集型。
- **处理**：`export OMPI_MCA_hwloc_base_binding_policy=core` + `rmaps_base_mapping_policy=core`；
  作业启动时自查 `CPU_IDs`，若少数派 socket 上超过 6–8 个核就 `scontrol requeue`（给 2 次机会）。
  想看 96 核全在一个 socket，只能在空闲 ≥96 核的节点上 `-w <node>` 提交，启动后立刻核对。

### 3.4 其它

- `sbatch: error: Batch script contains DOS line breaks`：脚本是 CRLF，转 LF。
- 单用户 premium 并发 5 是**按账号**算的，同账号别的项目在跑也会占名额。
- `scontrol show job` **不接受逗号列表**，批量查用 `sacct -j 1,2,3`。

## 4. 软件位置

装在**每个用户自己的目录**里，所以必须写进 `~/.compchemkit/config.json` 的 `software.*`，
不要写死在脚本里。典型布局（换成你自己的路径）：

| 软件 | config 键 | 说明 |
|---|---|---|
| ORCA | `software.orca` | 解包即用，多核时必须用**绝对路径**调用（ORCA 会再用绝对路径重拉自己） |
| xTB | `software.xtb` | 需要 `source .../share/xtb/config_env.bash` 才能拿到 `XTBPATH` |
| OpenMPI | `env_setup` | 系统默认 PATH 里**没有** mpirun，要在 `env_setup` 里 `export PATH=.../bin:$PATH` 和 `LD_LIBRARY_PATH` |
| Multiwfn | `software.multiwfn` | noGUI 版；配合 `orca_2mkl` 从 `.gbw` 转 molden 再跑 |
| Python | `software.python` | 装了 numpy/scipy/rdkit/openbabel；**没有** h5py/numba |

## 5. 实测基准（32 核，r2SCAN-3c/SMD，DEFGRID3）

| 体系 | 步骤 | 耗时 |
|---|---|---|
| 90 原子单体 | Opt | ~1.6 h |
| 90 原子单体 | Freq（解析 Hessian） | ~1.6 h |
| 190 原子单体 | Opt | ~10 min/循环 × 50+ 循环 |
| 190 原子单体 | Freq | 10–20 h（必须 64 核 + 动态 `%maxcore`） |
| 97 原子复合物 | Opt | 0.5–5 h |
| 97 原子复合物 | Freq | 1–3 h |
| 90 原子（xTB GFN2 `--ohess`） | Opt+Freq | ~3 min |
