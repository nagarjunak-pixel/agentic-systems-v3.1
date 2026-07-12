import os
import sys

# Configure python path dynamically for pytest execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
phase0_dir = os.path.abspath(os.path.join(current_dir, "../phase0"))
phase1_dir = os.path.abspath(os.path.join(current_dir, "../phase1"))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if phase0_dir not in sys.path:
    sys.path.insert(0, phase0_dir)
if phase1_dir not in sys.path:
    sys.path.insert(0, phase1_dir)
