"""Per-trial process RSS samples; unavailable data remains None."""

import threading
from pathlib import Path


class MemorySampler:
    def __init__(self):
        """Initialize an empty peak sample and the sampler stop event."""
        self.peak: int | None = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        """Poll worker RSS until stopped; leave the measurement missing when unavailable."""
        while not self.stop.is_set():
            try:
                for line in Path("/proc/self/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        value = int(line.split()[1]) * 1024
                        self.peak = max(self.peak or 0, value)
                        break
            except (OSError, ValueError):
                pass
            self.stop.wait(0.05)

    def __enter__(self):
        """Start the background RSS sampler and return its measurement holder."""
        self.thread.start()
        return self

    def __exit__(self, *_):
        """Stop and join the sampler after the measured block exits."""
        self.stop.set()
        self.thread.join(timeout=1)
