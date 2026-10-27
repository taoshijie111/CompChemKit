# xtb 批量 IR 光谱计算流水线

[English](README.md) | **中文**

基于 [xtb](https://xtb-docs.readthedocs.io/) 的自动化**批量红外（IR）光谱计算**工作流：只需一个 SMILES 文件，即可自动完成 3D 构象生成 → 结构优化与频率计算 → 虚频消除 → 结果归档清理 → 光谱展宽，最终产出统一的 HDF5 光谱数据库。

## 流水线总览

```
SMILES 文件 (.smi)
  │  ① generate_xyz_openbabel_single.py   Open Babel 构象搜索生成 3D 结构
  ▼
XYZ 目录  batch_k/molecule_i/molecule_i.xyz
  │  ② run_xtb_ir.py                      xtb 优化 + 频率计算 + 消虚频迭代
  ▼
批量结果归档  <task>_batch_results.pkl.gz  +  CONVERGED 标记（中间文件已清理）
  │  ③ extract_spectrum.py                 多线程读盘 + 多进程/Numba 展宽
  ▼
光谱 HDF5 数据库  spectra.h5
  │  ④ rebroaden_spectra.py（可选）        用不同方法/展宽参数重新计算光谱
  │  ⑤ dedup_h5_by_smiles.py（可选）       按 SMILES 去重
  ▼
最终数据集
```

## 目录结构

```
.
├── data/                               # 示例输入：SMILES 分片文件（每行一个 SMILES）
│   └── part_00.smi
├── xyz_out/                            # 示例输出：XYZ 构象 + xtb 结果
│   └── batch_0/
│       ├── xtb_ir_batch_results.pkl.gz # 该 batch 全部分子的 xtb 结果归档（gzip pickle 流）
│       └── molecule_0/
│           ├── molecule_0.xyz          # 3D 构象（第 2 行为 SMILES，后续流程依赖）
│           └── xtb_ir/                 # xtb 任务目录（清理后仅保留标记）
│               └── CONVERGED
├── generate_xyz_openbabel_single.py    # ① SMILES → XYZ 3D 构象（Open Babel 构象搜索）
├── run_xtb_ir.py                       # ② xtb 优化 + 频率 + 消虚频 + 结果归档
├── xtbgaussian_parser.py               # 解析 xtb 输出的 Gaussian 格式结果 (g98.out)
├── extract_spectrum.py                 # ③ 结果归档 → 展宽 → HDF5 光谱数据库
├── rebroaden_spectra.py                # ④ 基于 HDF5 中的频率/强度重新展宽
├── dedup_h5_by_smiles.py               # ⑤ HDF5 按 SMILES 去重
├── submit_generate_xyz_openbabel.sh    # SLURM 提交脚本（步骤①，阵列任务）
├── submit_run_xtb_ir.sh                # SLURM 提交脚本（步骤②，阵列任务）
├── spectrum_extract.sh                 # SLURM 提交脚本（步骤③）
└── spectra_lorentzian_fwhm8.h5         # 示例产物：展宽后的光谱数据库
```

## 环境依赖

- Python ≥ 3.9（开发环境 3.11）
- `numpy`、`h5py`、`tqdm`
- `openbabel`（含 `pybel`）、`periodictable`
- `numba`（可选但强烈建议：展宽核心计算加速数十倍；缺失时自动回退到纯 Python，速度极慢）
- `rdkit`（可选：用于从 SMILES 推断电荷/自旋多重度；缺失时回退到正则表达式解析）
- `xtb` 可执行文件（需支持 `--ohess`，输出 Gaussian 格式的 `g98.out`）

## 使用步骤

### 第 1 步：SMILES → 3D 构象（XYZ）

```bash
python generate_xyz_openbabel_single.py \
    --input-smi data/part_00.smi \
    --output-root xyz_out \
    --processes 16 \
    --force-field mmff94 \
    --timeout 600
```

- 输入为 `.smi` 文件：每行一个 SMILES，`#` 开头的行被跳过，取每行第一个空白分隔字段。
- 用 Open Babel 加氢、`OBBuilder` 构建初始结构，然后做力场构象搜索（`WeightedRotorSearch` + `ConjugateGradients` + `SteepestDescent`，力场可选 `uff`/`mmff94`/`mmff94s`）。
- 输出布局：`<output-root>/batch_{i//batch_size}/molecule_{i}/molecule_{i}.xyz`，默认每 1000 个分子一个 batch 目录。
- 多进程并行；`--timeout` 开启时每个分子通过独立子进程强制超时（防止个别分子卡死）。
- 失败分子记录到 `<output-root>/error.log`（`index\tsmiles\treason`），可用 `--overwrite` 重算已存在的分子。

### 第 2 步：xtb 优化 + 频率计算 + 消虚频

```bash
python run_xtb_ir.py \
    --root-dir xyz_out \
    --task-name xtb_ir \
    --max-workers 16 \
    --cores-per-task 4 \
    --max-iterations 10 \
    --disp-scale 1 \
    --imag-threshold 0 \
    --skip-completed
```

- 对每个 `molecule_*.xyz`，在 `<root>/batch_k/molecule_i/<task-name>/` 目录下执行：

  ```
  xtb molecule_i.xyz --ohess extreme -P <cores> --chrg <charge> --uhf <uhf> [--ptb] [--raman]
  ```

- **消虚频迭代**：解析 `g98.out` 得到频率和简振模位移，若最低频率低于 `--imag-threshold`（如 0），沿该简振模方向扰动几何（`coords + disp_scale × 位移`）后重跑，最多 `--max-iterations` 轮；仍有虚频则该分子记为失败。
- **归档与清理**：成功后把结果（见下文数据格式）追加写入 batch 级归档 `batch_k/<task-name>_batch_results.pkl.gz`，写入 `CONVERGED` 标记，随后删除该分子任务目录下的全部中间文件（日志、hessian 等），整个流程磁盘占用很低。
- **断点续算**：`--skip-completed` 跳过已完成分子；兼容旧版逐分子 `result.pkl.gz` 格式，自动迁移并补写归档。
- 并行度：线程池调度分子任务，worker 数取 `--max-workers`，缺省为 `CPU数 // cores_per_task`。

### 第 3 步：提取结果并展宽 → HDF5

```bash
python extract_spectrum.py --xyz-dir xyz_out -o spectra.h5 --fwhm 20
# 或洛伦兹展宽：
python extract_spectrum.py --xyz-dir xyz_out -o spectra_lorentzian.h5 --method lorentzian --fwhm 8
```

- 递归发现数据源：新格式 batch 归档 `*_batch_results.pkl.gz`，以及旧格式逐分子 `result.pkl.gz`（自动兼容）。
- I/O 与计算分离：8 个线程负责并发读盘（针对机械硬盘优化），多进程 + Numba 负责解压与展宽计算；分批流式写入 HDF5，支持追加。
- 光谱网格固定为 1–4000 cm⁻¹（`--spec-length`），默认 Voigt 式展宽（50% 高斯 + 50% 洛伦兹），`--fwhm` 默认 20。
- 输出字段可用 `--no-frequency` / `--no-intensity` / `--no-spectrum` 裁剪。

### 第 4 步（可选）：重新展宽

```bash
python rebroaden_spectra.py spectra.h5 -m lorentzian_convolution --width 8
```

只依赖 HDF5 中已有的 `frequency`/`intensity`，无需原始归档即可用不同方法/宽度重算光谱；输出文件名为 `<原文件名>_<method>_w<width>.h5`，并写入展宽参数与来源等溯源属性。

### 第 5 步（可选）：按 SMILES 去重

```bash
python dedup_h5_by_smiles.py spectra.h5               # 生成 <name>.dedup.h5
python dedup_h5_by_smiles.py spectra.h5 --replace     # 原地替换，原文件备份为 .bak
```

保留每个 SMILES 的第一条记录。

### SLURM 示例

- `submit_generate_xyz_openbabel.sh`：按 `part_XX.smi` 分片的阵列任务（64 进程、mmff94、600 s 超时）。
- `submit_run_xtb_ir.sh`：对应阵列任务（64 worker、消虚频 10 轮、`disp_scale=1`、`imag_threshold=0`）。
- `spectrum_extract.sh`：步骤③ 的提交脚本。

## 数据格式

### XYZ 文件

```
42
C1CCC=CCCCCCCCCCC1=O
C  -1.709744  -6.176910  -0.224917
...
```

第 1 行原子数，第 2 行 SMILES（`run_xtb_ir.py` 与 `extract_spectrum.py` 均依赖这一行），之后为 `元素 X Y Z`。

### batch 归档（gzip 压缩的 pickle 流）

`gzip.open(path, "ab")` 顺序追加多个 pickle 记录（记录间无分隔符，按 EOF 判断结束），每个记录为 dict：

| 字段 | 形状 | dtype | 说明 |
| --- | --- | --- | --- |
| `molecule` | — | str | 如 `molecule_0`（batch 内编号） |
| `smiles` | — | str | 原始 SMILES |
| `atomnos` | (N,) | int16 | 原子序数 |
| `atomcoords` | (N, 3) | float32 | 优化后坐标（Å） |
| `vibfreqs` | (3N-6,) | float32 | 振动频率（cm⁻¹） |
| `vibirs` | (3N-6,) | float32 | IR 强度（km/mol） |

### HDF5 数据库结构（`extract_spectrum.py` 输出）

| dataset | shape | dtype | 说明 |
| --- | --- | --- | --- |
| `smiles` | (N,) | utf-8 str | 分子数 N |
| `coords` | (N,) | vlen float32 | 每分子 N_atom×3 展平坐标 |
| `atom_counts` | (N,) | int32 | 每分子原子数 |
| `atomnos` | (N,) | vlen int32 | 每分子原子序数 |
| `frequency` | (N,) | vlen float32 | 筛选排序后的频率（可选字段） |
| `intensity` | (N,) | vlen float32 | 对应 IR 强度（可选字段） |
| `spectrum` | (N, 4000) | float32, lzf | 展宽后的光谱 |

## 关键实现细节

- **电荷与多重度推断**：优先用 RDKit 计算形式电荷之和与未成对电子数（`uhf = 自由基数`，多重度 = uhf+1）；RDKit 不可用时回退到正则解析 SMILES 中的 `[...]` 电荷片段，此时 `uhf=0`。
- **消虚频**：解析 `g98.out` 中的频率块与位移向量块（形状 3N-6 × N × 3）；扰动基于 xtb 优化后的坐标（`parser.atomcoords`），重跑前删除 `hessian` 文件避免缓存。
- **结果归档的线程安全**：batch 归档通过 per-file 锁保证多线程追加原子性；数据以 float32/int16 存储以压缩体积。
- **断点续算判定**：`CONVERGED` 标记合法性校验（格式、归档文件名、分子名）→ 旧格式 `result.pkl.gz` 迁移 → 日志尾部含 `normal termination of xtb` 且 `g98.out` 无虚频时做补归档（retro_cleaned）。
- **展宽**：仅保留 `freq > 0` 且 `intensity ≥ 0` 的振动模并按频率升序排序；洛伦兹核为面积归一形式 `amp = intensity × 100 × (fwhm/2) / π`；Voigt 式为 50% 高斯 + 50% 洛伦兹（FWHM 定义）。
- **`xtbgaussian_parser.py`**：解析 xtb 输出的 Gaussian 格式文件，提供 `atomnos` / `atomcoords` / `vibfreqs` / `vibirs` / `vibramans` / `vibrmasses` / `vibdisps`（位移，M×N×3）。
