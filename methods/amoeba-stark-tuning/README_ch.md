# Tinker/AMOEBA 计算 Stark 调谐率

[English](README.md) | [简体中文](README_ch.md)

这套脚本用来从 Tinker/AMOEBA 的分子动力学轨迹里标定化学键探针的振动 Stark 调谐率。探针上的
电场直接从 Tinker 每一步都会收敛的诱导偶极里还原出来，不需要额外的 MDI 或 ELECTRIC 作业，
也不用把轨迹 re-image：

$$
\mathbf{F}_i = \frac{299.79}{\alpha_i}
\left(\vec{\mu}^{\,\mathrm{ind,prod}}_i - \vec{\mu}^{\,\mathrm{ind,gas}}_i\right),
\qquad
F_{\mathrm{bond}} = \tfrac{1}{2}\left(\mathbf{F}_1 + \mathbf{F}_2\right)\cdot\hat{u}
$$

其中 $\vec{\mu}^{\,\mathrm{ind}}$ 是诱导偶极，单位 Debye；$\alpha_i$ 是原子极化率，单位 Å³；
$\hat{u}$ 从第一个探针原子指向第二个（羰基是 C→O，腈基是 C→N）。把孤立分子自己会产生的那份
减掉，再投影到键轴上，剩下的就是溶剂贡献。

我用它标定过苯甲醛的 C=O 在七种溶剂里的行为：每种溶剂三个独立盒子，每个盒子 5 ns，40 Å
立方盒。实验测得的频率对算出来的电场做回归，结果是 $b = 0.448302$ cm⁻¹/(MV cm⁻¹)、
$\bar{\nu}_0 = 1715.361$ cm⁻¹、$R^2 = 0.9725$。用同一批轨迹，这里的脚本能把这七个溶剂的
电场和这个拟合复现出来；具体设置和数字记在
[`reference/benzaldehyde_7solvents/CASE_STUDY.md`](reference/benzaldehyde_7solvents/CASE_STUDY.md)。

## 实验频率得自己提供

回归是每个溶剂一个点：横轴是 MD 算出来的电场，纵轴是测出来的频率。电场是算的，频率不是。
研究里用到的每种溶剂，都得有探针在该纯溶剂中的实测峰位，自己测（FTIR 或 Raman）或者从文献里
找，一个溶剂一行，一列溶剂名一列波数，格式见 `config/ir_shifts.example.csv`。苯甲醛案例用的
那张表在 [`reference/benzaldehyde_7solvents/ir_shifts.csv`](reference/benzaldehyde_7solvents/ir_shifts.csv)。

## 目录里有什么

```
SKILL.md                          完整流程：各阶段、参数设置、坑、怎么迁移到别的体系
README.md / README_ch.md          本文件与英文版
config/system_config.example.sh   复制成 config/system_config.sh 后修改
config/solvent_table.tsv          溶剂库模板
config/ir_shifts.example.csv      频率表模板
scripts/                          工具检查、建模、参数化、MD 各阶段、提电场、拟合
tools/                            Packmol/Tinker 构建、电场提取、analyze_uind wrapper
reference/benzaldehyde_7solvents/ 完整案例：设置、频率表、结果、图
reference/HAZARDS.md              我踩过的那些坑
```

## 怎么跑

```bash
cp config/system_config.example.sh config/system_config.sh   # 改 STUDY_DIR、溶质、探针、溶剂
cp config/solvent_table.tsv "$STUDY_DIR"/solvent_table.tsv
cp config/ir_shifts.example.csv "$STUDY_DIR"/ir_shifts.csv   # 换成你自己测的数
./scripts/00_check_tools.sh
./scripts/01_generate_molecules.sh
./scripts/02_parameterize.sh <溶质>  $STUDY_DIR/molecules/<溶质>.sdf  401
./scripts/02_parameterize.sh <溶剂>  $STUDY_DIR/molecules/<溶剂>.sdf  501   # 每种溶剂一次
./scripts/submit_md_stage.sh build_system
./scripts/submit_md_stage.sh minimize
./scripts/submit_md_stage.sh npt
./scripts/submit_md_stage.sh nvt
./scripts/submit_md_stage.sh production      # save-induced 要开着
./scripts/extract_fields.sh
./scripts/fit_stark_rate.py --root-dir <分析目录> --ir-csv "$STUDY_DIR"/ir_shifts.csv
```

MD 各阶段是丢到后台跑的，所有溶剂和重复会并行；只想跑一部分就加 `TARGET_SOLVENTS=` 或
`TARGET_REPLICATES=`，如果是在作业脚本里、希望它在前台跑，加 `MD_FOREGROUND=1`。

## 依赖

Tinker 要有 `minimize`、`dynamic`、`analyze`（v25、v26 我都用过），外加 Poltype2 和 xTB、
Packmol，拟合那一步要 numpy 和 matplotlib。脚本默认到 `${HOME}/miniconda3/envs/amoeba/bin`
下面找 Tinker 和 Packmol，装在别处就设 `AMOEBA_ENV_BIN`，或者单独改对应的 `*_CMD`。默认值都
在 `scripts/_defaults.sh` 里，`00_check_tools.sh` 会把它实际用到的路径打出来。

磁盘要留够：一次 5 ns 生产会写出 `md_start.arc` 和 `md_start.uind`，溶剂分子几百到几千个时
每个 8–22 GB，算下来一个重复大概 33 GB，七个溶剂三个重复是 700 GB。

## 容易踩的坑

- 生产阶段必须开 `save-induced`。不开就没有 `.uind`，后处理无东西可读，而且全程不会有任何提示。
- `ref.key` 里不能有盒子参数，也不能有 `ewald`。这个文件代表气相参考，多一行盒子，所有电场会
  整体平移大约 0.1 MV/cm，同样不会有警告。
- `.uind` 存的是诱导偶极，单位 Debye，但格式和坐标文件一模一样。当成坐标去读，电场会差好几个
  数量级。
- `slope_se` 只是下界。相邻帧高度相关，真正独立的信息来自那三个重复。

其它踩过的坑写在 [`reference/HAZARDS.md`](reference/HAZARDS.md)；整个流程、包括怎么换探针和
换溶剂，见 [`SKILL.md`](SKILL.md)。
