#!/usr/bin/env python3
"""Regenerate only Figure 1 and Figure 7 (arrow + y-axis fixes)."""
import sys
from pathlib import Path

from generate_manuscript_outputs import load_logs, make_fig1, make_fig7
import generate_manuscript_outputs as g

g.OUT_DIR = Path("manuscript_outputs")

log_path = sys.argv[1] if len(sys.argv) > 1 else "algorithm_logs.json"
print(f"Loading {log_path} ...")
logs = load_logs(log_path)
print(f"  {len(logs)} entries")
print("Figure 1 ...")
for p in make_fig1():
    print(f"  {p}")
print("Figure 7 ...")
for p in make_fig7(logs):
    print(f"  {p}")
print("Done.")
