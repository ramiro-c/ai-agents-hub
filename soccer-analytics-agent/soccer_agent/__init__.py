"""Soccer analytics agent package.

OpenMP guard: PyTorch (via `embeddings`) and XGBoost (via `predictor`) each ship
their own OpenMP runtime. When both are loaded in one process, the duplicate
runtime initialization segfaults on macOS (SIGSEGV, uncatchable by try/except).
Pinning OpenMP to a single thread before either library loads avoids the clash.
`setdefault` lets an explicit environment override still win. This runs first
because importing any `soccer_agent.*` submodule executes this file before it.
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
