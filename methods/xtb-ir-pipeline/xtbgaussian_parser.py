import numpy as np
import re


class XTBGaussianParser:
    def __init__(self, file_path: str):
        with open(file_path, "r") as f:
            content = f.read()
        self.raw_lines = content.splitlines()
        
        self._atomnos = []
        self._coords = []
        self._vibfreqs = []
        self._vibrmasses = []
        self._vibirs = []
        self._vibramans = []
        self._vibdisps = [] # shape will be (M, N, 3)
    
        self._parse()

    def _parse(self):
        iterator = iter(self.raw_lines)
        num_atoms = 0
        
        # 1. "Standard orientation"
        found_coords = False
        while True:
            try:
                line = next(iterator)
                if "Standard orientation" in line:
                    found_coords = True
                    # (------, Center Number..., ------)
                    for _ in range(4):
                        next(iterator)

                    while True:
                        line = next(iterator)
                        if "----------------" in line:
                            break
                        parts = line.strip().split()
                        # Gaussian 98 format: CenterNumber AtomicNumber AtomicType X Y Z
                        if len(parts) >= 6:
                            self._atomnos.append(int(parts[1]))
                            self._coords.append([float(parts[3]), float(parts[4]), float(parts[5])])
                    break
            except StopIteration:
                break
        
        if found_coords:
            self._atomnos = np.array(self._atomnos, dtype=np.int32)
            self._coords = np.array(self._coords, dtype=float)
            num_atoms = len(self._atomnos)

        # 2. Harmonic frequencies

        while True:
            try:
                line = next(iterator)

                if "Frequencies --" in line:
                    freqs = [float(x) for x in line.split()[2:]]
                    n_modes_in_block = len(freqs)
                    self._vibfreqs.extend(freqs)
                    
                    # Reduced masses
                    line = next(iterator)
                    if "Red. masses --" in line:
                        self._vibrmasses.extend([float(x) for x in line.split()[3:]])
                        
                    # Force constants 
                    line = next(iterator)
                    
                    # IR Intensities
                    line = next(iterator)
                    if "IR Inten    --" in line:
                        for s in line.split()[3:]:
                            try:
                                self._vibirs.append(float(s))
                            except ValueError:
                                self._vibirs.append(0.)
                        
                    # Raman Activities
                    line = next(iterator)
                    if "Raman Activ --" in line:
                        for s in line.split()[3:]:
                            try:
                                self._vibramans.append(float(s))
                            except ValueError:
                                self._vibramans.append(0.)
                        line = next(iterator)
                    else:
                        pass

                    # Depolarization ratios
                    if "Depolar     --" in line:
                        line = next(iterator)

                    # Atom AN X Y Z ...
                    if "Atom AN" in line:
                        # [n_modes, n_atoms, 3]
                        block_disps = np.zeros((n_modes_in_block, num_atoms, 3))
                        
                        for i in range(num_atoms):
                            line = next(iterator)
                            parts = line.strip().split()
                            raw_values = [float(x) for x in parts[2:]]
                            
                            for m in range(n_modes_in_block):
                                block_disps[m, i, 0] = raw_values[m*3 + 0]
                                block_disps[m, i, 1] = raw_values[m*3 + 1]
                                block_disps[m, i, 2] = raw_values[m*3 + 2]
                        for m in range(n_modes_in_block):
                            self._vibdisps.append(block_disps[m])

            except StopIteration:
                break

    @property
    def converged_geometries(self) -> np.ndarray:
        """返回 [N, 3] 的 array，包含原子坐标 (Angstroms)"""
        return self._coords

    @property
    def atomcoords(self) -> np.ndarray:
        """返回 [N, 3] 的 array，包含原子坐标 (Angstroms)"""
        return self._coords
    
    @property
    def atomnos(self) -> np.ndarray:
        """返回 [N] 的 int32 array，包含原子序数"""
        return self._atomnos

    @property
    def vibfreqs(self) -> np.ndarray:
        """返回 [3N-6/5] 的 array，包含振动频率 (cm**-1)"""
        return np.array(self._vibfreqs)

    @property
    def vibirs(self) -> np.ndarray:
        """返回 [3N-6/5] 的 array，包含红外强度 (km/mol)"""
        return np.array(self._vibirs)
    
    @property
    def vibramans(self) -> np.ndarray:
        """返回 [3N-6/5] 的 array，包含拉曼活性 (A**4/amu)"""
        if not self._vibramans and len(self._vibfreqs) > 0:
            return np.zeros_like(self.vibfreqs)
        return np.array(self._vibramans)

    @property
    def vibrmasses(self) -> np.ndarray:
        """返回 [3N-6/5] 的 array，包含约化质量 (AMU)"""
        return np.array(self._vibrmasses)

    @property
    def vibdisps(self) -> np.ndarray:
        """返回 [3N-6/5, N, 3] 的 array，包含简振模位移矢量"""
        if not self._vibdisps:
            return np.empty((0, 0, 3))
        return np.array(self._vibdisps)



