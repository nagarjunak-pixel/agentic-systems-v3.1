import os
import sys

# Configure python path dynamically for pytest execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
phase0_dir = os.path.abspath(os.path.join(current_dir, "../phase0"))
phase1_dir = os.path.abspath(os.path.join(current_dir, "../phase1"))
phase2_dir = os.path.abspath(os.path.join(current_dir, "../phase2"))
phase3_dir = os.path.abspath(os.path.join(current_dir, "../phase3"))
phase4_dir = os.path.abspath(os.path.join(current_dir, "../phase4"))
phase5_dir = os.path.abspath(os.path.join(current_dir, "../phase5"))
phase6_dir = os.path.abspath(os.path.join(current_dir, "."))

for path in [current_dir, parent_dir, phase0_dir, phase1_dir, phase2_dir, phase3_dir, phase4_dir, phase5_dir, phase6_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)
