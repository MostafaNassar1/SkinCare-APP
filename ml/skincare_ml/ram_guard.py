"""RAM guard for training on the borrowed GPU laptop (decided 2026-11-23, the student's request).

In Step 3 the YOLO trainer's loader workers filled the GPU laptop's 16 GB RAM (100%). The U-Net
script already avoids the cause (one process, workers = 0, pictures read one at a time, nothing
cached); this guard is the safety net: training stops cleanly (resumable with --resume) when its
own memory goes above PROCESS_LIMIT of the laptop's RAM, or when the whole laptop goes above
SYSTEM_LIMIT (other programs). Memory is measured with psutil (BSD).
"""

import psutil

PROCESS_LIMIT = 0.60  # the student's limit: training uses at most 60% of the RAM
SYSTEM_LIMIT = 0.90  # never let the laptop itself run out of memory


class RamLimitReached(RuntimeError):
    pass


class RamGuard:
    def __init__(self, process_limit: float = PROCESS_LIMIT, system_limit: float = SYSTEM_LIMIT):
        self.process_limit, self.system_limit = process_limit, system_limit
        self.process = psutil.Process()
        self.total = psutil.virtual_memory().total
        self.peak = 0

    def used_by_training(self) -> int:
        """Bytes held by this process and any child it started."""
        used = self.process.memory_info().rss
        for child in self.process.children(recursive=True):
            try:
                used += child.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        return used

    def check(self) -> None:
        """Raise RamLimitReached when a limit is crossed; remember the peak."""
        used = self.used_by_training()
        self.peak = max(self.peak, used)
        system = psutil.virtual_memory().percent / 100
        if used > self.process_limit * self.total:
            raise RamLimitReached(
                f"training uses {used / 2**30:.1f} GB = {used / self.total:.0%} of the RAM "
                f"(limit {self.process_limit:.0%})")  # fmt: skip
        if system > self.system_limit:
            raise RamLimitReached(
                f"the laptop's RAM is {system:.0%} full (limit {self.system_limit:.0%}): close "
                "other programs")  # fmt: skip

    def take_peak(self) -> tuple[float, float]:
        """(peak GB, peak share of the RAM) since the last call, then start a new peak."""
        peak, self.peak = self.peak, 0
        return round(peak / 2**30, 2), round(peak / self.total, 3)
