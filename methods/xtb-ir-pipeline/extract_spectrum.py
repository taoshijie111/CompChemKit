#!/usr/bin/env python3
"""
【终极优化版】光谱展宽流水线 - 针对 HDD 机械硬盘 IOPS 瓶颈优化

优化点：
1. I/O 并发：使用 ThreadPoolExecutor (8线程) 并行读取文件，填满硬盘命令队列。
2. 计算并行：使用 Multiprocessing Pool 并行解压和 Numba 计算。
3. 进度可视化：分阶段显示 I/O 读取进度和 计算进度。
4. 内存安全：分批次流式写入 HDF5。

数据格式:
    - smiles: 字符串，从XYZ文件第二行读取 (必须)
    - coords: 优化后的原子坐标数组 [[x1, y1, z1], [x2, y2, z2], ...] (必须)
    - atomnos: 原子序号数组 [Z1, Z2, ...] (必须)
    - atom_counts: 原子数量 (必须)
    - frequency: 振动频率数组 [freq1, freq2, ...] (可选)
    - intensity: 红外强度数组 [intensity1, intensity2, ...] (可选)
    - spectrum: 展宽后的光谱数组 [intensity_at_1, intensity_at_2, ...] (可选)

用法:
    python3 extract_spectrum.py --xyz-dir <xyz_dir> -w 20 --batch-size 20000
    python3 extract_spectrum.py --xyz-dir <xyz_dir> -o output.h5 --include-frequency --include-intensity --include-spectrum
"""

import argparse
import gzip
import os
import pickle
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool, cpu_count
from typing import Iterator, Optional

import h5py
import numpy as np
from tqdm import tqdm  # pip install tqdm

# ==================== Numba 核心 ====================
try:
    from numba import njit, prange
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    print("\033[91m警告: Numba 未安装，速度将非常慢！\033[0m")

if HAS_NUMBA:
    @njit(cache=True, fastmath=True)
    def _voigt_kernel(x, pos, fwhm, amp, shape):
        n = len(x)
        result = np.zeros(n, dtype=np.float32)
        sigma = fwhm / 2.35482
        gamma = fwhm / 2.0
        for i in prange(n):
            dx = x[i] - pos
            g = np.exp(-(dx * dx) / (2 * sigma * sigma))
            l = gamma * gamma / (dx * dx + gamma * gamma)
            result[i] = amp * ((1.0 - shape) * g + shape * l)
        return result

    @njit(cache=True, fastmath=True)
    def broaden_spectrum(freqs, intensities, spec_length=4000, fwhm=20.0):
        y = np.zeros(spec_length, dtype=np.float32)
        x = np.arange(1, spec_length + 1, dtype=np.float32)  # 1-4000
        n_modes = len(freqs)
        for i in range(n_modes):
            freq = freqs[i]
            intensity = intensities[i]
            if freq <= 0 or freq > spec_length or intensity <= 0: continue
            y += _voigt_kernel(x, freq, fwhm, intensity, 0.5)
        return y

    @njit(cache=True, fastmath=True)
    def lorentzian_convolution(frequencies, intensities, spec_length=4000, fwhm=20.0):
        result = np.zeros(spec_length, dtype=np.float32)
        half_width = fwhm / 2.0
        half_width_sq = half_width * half_width
        scale = 100.0 * half_width / np.pi
        n_modes = len(frequencies)
        for i in range(n_modes):
            freq = frequencies[i]
            intensity = intensities[i]
            if freq < 0.0:
                continue
            amp = intensity * scale
            for j in range(spec_length):
                x = j + 1.0
                dx = x - freq
                denom = dx * dx + half_width_sq
                result[j] += amp / denom
        return result
else:
    def broaden_spectrum(freqs, intensities, spec_length=4000, fwhm=20.0):
        x = np.arange(1, spec_length + 1, dtype=np.float32)  # 1-4000
        y = np.zeros(spec_length, dtype=np.float32)
        valid_mask = (freqs > 0) & (freqs <= spec_length) & (intensities > 0)
        vf, vi = np.asarray(freqs)[valid_mask], np.asarray(intensities)[valid_mask]
        if len(vf) == 0: return y
        dx = vf[:, None] - x[None, :]
        sigma, gamma = fwhm / 2.35482, fwhm / 2.0
        voigt = 0.5 * np.exp(-(dx**2)/(2*sigma**2)) + 0.5 * (gamma**2)/(dx**2+gamma**2)
        return (vi @ voigt).astype(np.float32)

    def lorentzian_convolution(frequencies, intensities, spec_length=4000, fwhm=20.0):
        output_range = np.arange(1, spec_length + 1, dtype=np.float32)
        result = np.zeros(spec_length, dtype=np.float64)
        half_width = fwhm / 2.0
        scale = 100.0 * half_width / np.pi
        for freq, intensity in zip(frequencies, intensities):
            if freq < 0.0:
                continue
            denom = (output_range - freq) ** 2 + half_width**2
            result += intensity * scale / denom
        return result.astype(np.float32)


# ==================== I/O 模块 (重点优化) ====================

BATCH_ARCHIVE_SUFFIX = "_batch_results.pkl.gz"
LEGACY_RESULT_NAME = "result.pkl.gz"


def expected_batch_archive_for_legacy(result_path: Path) -> Optional[Path]:
    try:
        task_dir = result_path.parent
        batch_dir = result_path.parents[2]
    except IndexError:
        return None
    return batch_dir / f"{task_dir.name}{BATCH_ARCHIVE_SUFFIX}"


def resolve_legacy_xyz_path(result_path: Path) -> Optional[Path]:
    try:
        molecule_dir = result_path.parents[1]
    except IndexError:
        return None

    preferred_path = molecule_dir / f"{molecule_dir.name}.xyz"
    if preferred_path.is_file():
        return preferred_path

    xyz_candidates = sorted(
        child for child in molecule_dir.iterdir()
        if child.is_file() and child.suffix == ".xyz"
    )
    if not xyz_candidates:
        return None
    return xyz_candidates[0]


def get_data_sources(xyz_base_dir: str) -> Iterator[tuple]:
    """
    递归发现数据源:
    1. 新格式: *_batch_results.pkl.gz
    2. 旧格式: result.pkl.gz

    对旧格式，如果对应 batch 级归档文件已存在，则跳过以避免重复读取。
    若当前目录已存在 batch 级归档文件，则不再深入其子目录，避免无意义的深层扫描。
    """
    root_dir = Path(xyz_base_dir.rstrip('/'))
    if not root_dir.exists():
        return

    batch_archives = []
    legacy_results = []

    for current_root, dirnames, filenames in os.walk(root_dir, topdown=True):
        dirnames.sort()
        filenames = sorted(filenames)
        current_dir = Path(current_root)

        batch_paths_in_dir = [
            current_dir / name
            for name in filenames
            if name.endswith(BATCH_ARCHIVE_SUFFIX)
        ]
        if batch_paths_in_dir:
            batch_archives.extend(batch_paths_in_dir)
            dirnames[:] = []

        for name in filenames:
            if name != LEGACY_RESULT_NAME:
                continue

            path = current_dir / name
            task_dir = path.parent
            if not (task_dir / "CONVERGED").exists():
                continue

            expected_batch_archive = expected_batch_archive_for_legacy(path)
            if expected_batch_archive is not None and expected_batch_archive.exists():
                continue

            xyz_path = resolve_legacy_xyz_path(path)
            if xyz_path is None:
                continue

            legacy_results.append((path, xyz_path))

    for path in batch_archives:
        yield ("batch_archive", str(path))

    for result_path, xyz_path in legacy_results:
        yield ("legacy_result", (str(result_path), str(xyz_path)))


def read_raw_files_threaded(source: tuple) -> list:
    """
    [线程安全] 读取函数
    兼容两种数据源:
    1. 旧格式: 逐分子 result.pkl.gz，读取 xyz 头和原始压缩字节
    2. 新格式: batch 级压缩包，顺序解出其中的多条记录
    """
    source_type, source_path = source
    try:
        if source_type == "legacy_result":
            result_file, xyz_file = source_path
            if not os.path.exists(result_file) or not os.path.exists(xyz_file):
                return []

            with open(result_file, 'rb') as f:
                pkl_gz_bytes = f.read()

            with open(xyz_file, 'rb') as f:
                xyz_header_bytes = f.read(1000)

            return [("legacy", (pkl_gz_bytes, xyz_header_bytes))]

        if source_type == "batch_archive":
            records = []
            with gzip.open(source_path, 'rb') as f:
                while True:
                    try:
                        record = pickle.load(f)
                    except EOFError:
                        break
                    if isinstance(record, dict):
                        records.append(("batch", record))
            return records

        return []
    except Exception:
        return []


def build_result(smiles, freqs, intensities, atomcoords, atomnos,
                 spec_length, fwhm, include_frequency, include_intensity, include_spectrum,
                 method="voigt"):
    if smiles is None or atomcoords is None or atomnos is None:
        return None

    atomcoords = np.asarray(atomcoords, dtype=np.float32)
    atomnos = np.asarray(atomnos, dtype=np.int32)

    if atomcoords.ndim == 2 and atomcoords.shape[1] == 3:
        coords = atomcoords
    elif atomcoords.ndim == 3:
        coords = atomcoords[-1]
    else:
        return None

    if atomnos.ndim != 1 or len(atomnos) != len(coords):
        return None

    freqs = np.asarray(freqs, dtype=np.float32)
    intensities = np.asarray(intensities, dtype=np.float32)

    valid_mask = (freqs > 0) & (intensities >= 0)
    freqs = freqs[valid_mask]
    intensities = intensities[valid_mask]

    if len(freqs) == 0:
        return None

    sort_idx = np.argsort(freqs)
    freqs = freqs[sort_idx]
    intensities = intensities[sort_idx]

    result = {
        'smiles': smiles,
        'coords': coords,
        'atomnos': atomnos,
    }

    if include_spectrum:
        if method == "lorentzian":
            result['spectrum'] = lorentzian_convolution(freqs, intensities, spec_length, fwhm)
        else:
            result['spectrum'] = broaden_spectrum(freqs, intensities, spec_length, fwhm)
    if include_frequency:
        result['frequency'] = freqs
    if include_intensity:
        result['intensity'] = intensities

    return result


def process_bytes_in_worker(args: tuple) -> Optional[tuple]:
    """[进程 Worker] CPU 密集型计算"""
    source_kind, payload, spec_length, fwhm, include_frequency, include_intensity, include_spectrum, method = args
    try:
        if source_kind == "legacy":
            pkl_gz_bytes, xyz_header_bytes = payload
            lines = xyz_header_bytes.split(b'\n')
            if len(lines) < 2:
                return None
            smiles = lines[1].strip().decode('utf-8')
            data = pickle.loads(gzip.decompress(pkl_gz_bytes))
        elif source_kind == "batch":
            data = payload
            smiles = data.get('smiles')
        else:
            return None

        freqs = data.get('vibfreqs')
        intensities = data.get('vibirs')
        atomcoords = data.get('atomcoords')
        atomnos = data.get('atomnos')

        if freqs is None or intensities is None or atomcoords is None or atomnos is None:
            return None

        return build_result(
            smiles, freqs, intensities, atomcoords, atomnos,
            spec_length, fwhm, include_frequency, include_intensity, include_spectrum,
            method=method,
        )
    except Exception:
        return None


def append_to_hdf5(batch_results: list, h5_file_path: str, spec_length: int,
                   include_frequency: bool, include_intensity: bool, include_spectrum: bool):
    """HDF5 追加写入，统一格式与 pack_spectra_raw.py 一致"""
    if not batch_results: return
    
    count = len(batch_results)
    
    # 预准备数据，避免在文件打开时做复杂操作
    smiles_list = [r['smiles'] for r in batch_results]
    coords_list = [r['coords'].flatten() for r in batch_results]
    atom_counts_list = [len(r['coords']) for r in batch_results]
    atomnos_list = [r['atomnos'] for r in batch_results]
    
    if include_frequency:
        frequency_list = [r['frequency'] for r in batch_results]
    if include_intensity:
        intensity_list = [r['intensity'] for r in batch_results]
    if include_spectrum:
        spectrum_matrix = np.array([r['spectrum'] for r in batch_results], dtype=np.float32)
    
    with h5py.File(h5_file_path, 'a') as f:
        if 'smiles' not in f:
            # 创建数据集 - 必须字段
            dt = h5py.string_dtype(encoding='utf-8')
            f.create_dataset('smiles', shape=(0,), maxshape=(None,), dtype=dt, chunks=(1000,))
            
            # 创建变长数据集存储不同分子的坐标（不同分子有不同数量的原子）
            f.create_dataset('coords', shape=(0,), maxshape=(None,),
                             dtype=h5py.vlen_dtype(np.dtype('float32')))
            # 存储每个分子的原子数
            f.create_dataset('atom_counts', shape=(0,), maxshape=(None,),
                             dtype='int32', chunks=(1000,))
            # 创建变长数据集存储不同分子的原子序号
            f.create_dataset('atomnos', shape=(0,), maxshape=(None,),
                             dtype=h5py.vlen_dtype(np.dtype('int32')))
            
            # 可选字段
            if include_frequency:
                f.create_dataset('frequency', shape=(0,), maxshape=(None,),
                                 dtype=h5py.vlen_dtype(np.dtype('float32')))
            if include_intensity:
                f.create_dataset('intensity', shape=(0,), maxshape=(None,),
                                 dtype=h5py.vlen_dtype(np.dtype('float32')))
            if include_spectrum:
                f.create_dataset('spectrum', shape=(0, spec_length), maxshape=(None, spec_length), 
                                 dtype='float32', chunks=(1000, spec_length), compression="lzf")
                             
        d_smiles = f['smiles']
        d_coords = f['coords']
        d_atom_counts = f['atom_counts']
        d_atomnos = f['atomnos']
        
        curr_size = d_smiles.shape[0]
        
        # 扩展数据集
        d_smiles.resize((curr_size + count,))
        d_coords.resize((curr_size + count,))
        d_atom_counts.resize((curr_size + count,))
        d_atomnos.resize((curr_size + count,))
        
        if include_frequency:
            d_frequency = f['frequency']
            d_frequency.resize((curr_size + count,))
        if include_intensity:
            d_intensity = f['intensity']
            d_intensity.resize((curr_size + count,))
        if include_spectrum:
            d_spectrum = f['spectrum']
            d_spectrum.resize((curr_size + count, spec_length))
        
        # 批量写入数据 (使用切片赋值，比逐个元素快)
        d_smiles[curr_size:curr_size + count] = smiles_list
        d_coords[curr_size:curr_size + count] = coords_list
        d_atom_counts[curr_size:curr_size + count] = atom_counts_list
        d_atomnos[curr_size:curr_size + count] = atomnos_list
        
        if include_frequency:
            d_frequency[curr_size:curr_size + count] = frequency_list
        if include_intensity:
            d_intensity[curr_size:curr_size + count] = intensity_list
        if include_spectrum:
            d_spectrum[curr_size:curr_size + count] = spectrum_matrix


# ==================== 主程序 ====================

def main():
    parser = argparse.ArgumentParser(description="HDD 极限优化版光谱处理脚本")
    parser.add_argument("-o", "--output", default="broadened_spectra.h5")
    parser.add_argument("-w", "--workers", type=int, default=max(1, cpu_count() - 2))
    parser.add_argument("--batch-size", type=int, default=20000)
    parser.add_argument("--spec-length", type=int, default=4000)
    parser.add_argument("--fwhm", type=float, default=20.0)
    parser.add_argument("--xyz-dir", default="xyz")
    parser.add_argument("--io-threads", type=int, default=8, help="读取文件的并发线程数 (HDD建议4-8)")
    parser.add_argument("--method", default="voigt", choices=["voigt", "lorentzian"],
                        help="展宽方法: voigt (默认) 或 lorentzian")
    
    # 可选输出字段控制
    parser.add_argument("--include-frequency", action="store_true", default=True,
                        help="是否包含原始频率数据 (默认: True)")
    parser.add_argument("--include-intensity", action="store_true", default=True,
                        help="是否包含原始强度数据 (默认: True)")
    parser.add_argument("--include-spectrum", action="store_true", default=True,
                        help="是否包含展宽后的光谱数据 (默认: True)")
    parser.add_argument("--no-frequency", action="store_true",
                        help="不包含原始频率数据")
    parser.add_argument("--no-intensity", action="store_true",
                        help="不包含原始强度数据")
    parser.add_argument("--no-spectrum", action="store_true",
                        help="不包含展宽后的光谱数据")
    
    args = parser.parse_args()
    
    # 处理布尔参数
    include_frequency = args.include_frequency and not args.no_frequency
    include_intensity = args.include_intensity and not args.no_intensity
    include_spectrum = args.include_spectrum and not args.no_spectrum
    
    print(f"=== HDD 极限优化版启动 ===")
    print(f"数据源: {args.xyz_dir}")
    print(f"I/O线程: {args.io_threads} (负责并发读盘)")
    print(f"CPU进程: {args.workers} (负责计算)")
    print(f"Batch : {args.batch_size}")
    print(f"展宽方法: {args.method}")
    print(f"输出字段: smiles(必须), coords(必须), atomnos(必须), atom_counts(必须), " + 
          f"frequency({'是' if include_frequency else '否'}), " +
          f"intensity({'是' if include_intensity else '否'}), " +
          f"spectrum({'是' if include_spectrum else '否'})")
    print("--------------------------")

    if os.path.exists(args.output):
        print(f"⚠️  注意: 输出文件 {args.output} 已存在，新数据将追加到尾部。")
        # os.remove(args.output) # 如果想每次重写，取消注释这行

    source_gen = iter(get_data_sources(args.xyz_dir))
    total_processed = 0
    total_success = 0
    batch_idx = 0
    found_any_source = False
    
    start_time = time.time()
    
    # 启动计算进程池 (常驻，避免反复创建销毁)
    with Pool(processes=args.workers) as cpu_pool:
        while True:
            batch_idx += 1
            current_sources = []
            
            # 1. 获取一批输入源
            try:
                for _ in range(args.batch_size):
                    current_sources.append(next(source_gen))
            except StopIteration:
                pass
            
            if not current_sources:
                break
            found_any_source = True
            
            print(f"\n[Batch {batch_idx}] 读取 {len(current_sources)} 个输入源:")

            # -------------------------------------------------
            # 阶段 1: 多线程并发 I/O 读取 (解决读取慢的关键!)
            # -------------------------------------------------
            raw_data_inputs = []
            
            with ThreadPoolExecutor(max_workers=args.io_threads) as io_pool:
                results_iter = io_pool.map(read_raw_files_threaded, current_sources)
                
                for source_records in tqdm(
                    results_iter,
                    total=len(current_sources),
                    desc="  Step 1: HDD并发读取",
                    unit="src",
                    ncols=80,
                ):
                    if not source_records:
                        continue
                    total_processed += len(source_records)
                    for source_kind, payload in source_records:
                        raw_data_inputs.append((
                            source_kind,
                            payload,
                            args.spec_length,
                            args.fwhm,
                            include_frequency,
                            include_intensity,
                            include_spectrum,
                            args.method,
                        ))

            # -------------------------------------------------
            # 阶段 2: 多进程并发计算
            # -------------------------------------------------
            valid_results = []
            if raw_data_inputs:
                # imap_unordered 配合 tqdm 显示计算进度
                calc_iter = cpu_pool.imap_unordered(process_bytes_in_worker, raw_data_inputs, chunksize=50)
                
                for res in tqdm(calc_iter, total=len(raw_data_inputs), desc="  Step 2: CPU并行计算", unit="mol", ncols=80):
                    if res is not None:
                        valid_results.append(res)
                        total_success += 1
            
            # -------------------------------------------------
            # 阶段 3: 写入 HDF5
            # -------------------------------------------------
            if valid_results:
                print(f"  Step 3: 写入 HDF5 ({len(valid_results)} 条数据)...", end=" ")
                append_to_hdf5(valid_results, args.output, args.spec_length,
                               include_frequency, include_intensity, include_spectrum)
                print("完成")
            
            # 显式内存清理
            del current_sources
            del raw_data_inputs
            del valid_results
            import gc
            gc.collect()

    end_time = time.time()
    duration = end_time - start_time
    print("\n" + "="*50)
    if not found_any_source:
        print(f"警告: 未在 {args.xyz_dir} 下发现可读取的数据源。")
        print(f"脚本会递归查找 *{BATCH_ARCHIVE_SUFFIX} 和 {LEGACY_RESULT_NAME}。")
    print(f"全部完成！")
    print(f"总耗时: {duration/3600:.2f} 小时")
    print(f"总扫描: {total_processed}")
    print(f"总成功: {total_success}")
    print(f"平均速率: {total_processed/duration:.1f} mol/s")

if __name__ == "__main__":
    main()
