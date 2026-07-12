import os
import sys
import json
import time
import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional

# Dynamically add Phase 0 to path to import MemoryEngine
PHASE0_PATH = "/Users/venkataswaraswamy/Desktop/agentic_core/phase0"
if PHASE0_PATH not in sys.path:
    sys.path.append(PHASE0_PATH)

try:
    from core.memory.engine import MemoryEngine
except ImportError:
    # Fallback for isolated testing where phase0 is imported differently
    MemoryEngine = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CommandAuditLogger")

class CommandAuditLogger:
    def __init__(self, memory_engine: Any, log_filename: str = "audit/command_audit.jsonl"):
        self.memory_engine = memory_engine
        self.log_filename = log_filename
        self.prev_hash = "0" * 64
        self.next_index = 0
        
        # Load last hash and index from existing log file
        self._load_last_state()

    def _load_last_state(self):
        """Reads the existing log file to reconstruct the last hash and index of the chain."""
        if not self.memory_engine:
            return
            
        full_path = os.path.join(self.memory_engine.root_dir, self.log_filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_line = lines[-1]
                    entry = json.loads(last_line)
                    self.prev_hash = entry.get("hash", "0" * 64)
                    self.next_index = entry.get("index", 0) + 1
            except Exception as e:
                logger.error(f"Failed to read existing audit log for state reconstruction: {e}")

    def _calculate_hash(self, entry: Dict[str, Any]) -> str:
        """Computes the SHA-256 hash of a log entry, excluding the hash field itself."""
        data = entry.copy()
        data.pop("hash", None)
        # Use sort_keys=True for deterministic serialization
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def log_execution(self, command: str, syscalls: List[str], network: List[str], exit_code: int) -> Dict[str, Any]:
        """
        Records a sandbox command execution event to the tamper-proof write-ahead log.
        Integrates with MemoryEngine to persist the log.
        """
        entry = {
            "index": self.next_index,
            "timestamp": time.time(),
            "command": command,
            "syscalls": syscalls,
            "network": network,
            "exit_code": exit_code,
            "prev_hash": self.prev_hash
        }
        
        # Compute current hash
        current_hash = self._calculate_hash(entry)
        entry["hash"] = current_hash
        
        # Update logger states
        self.prev_hash = current_hash
        self.next_index += 1
        
        # Persist entry to MemoryEngine in append mode
        entry_str = json.dumps(entry) + "\n"
        if self.memory_engine:
            try:
                self.memory_engine.write_file_sync(self.log_filename, entry_str, mode="a")
            except Exception as e:
                logger.error(f"Failed to persist audit log to MemoryEngine: {e}")
        else:
            logger.warning("MemoryEngine not attached. Log execution not persisted.")
            
        return entry

    def verify_integrity(self) -> Tuple[bool, List[int]]:
        """
        Traverses the log file, computes the hash chain, and identifies any modified/tampered entries.
        Returns:
            (is_valid: bool, tampered_indices: List[int])
        """
        if not self.memory_engine:
            return True, []
            
        full_path = os.path.join(self.memory_engine.root_dir, self.log_filename)
        if not os.path.exists(full_path):
            return True, []
            
        tampered_indices = []
        expected_prev_hash = "0" * 64
        
        try:
            with open(full_path, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
                
            for i, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                except Exception:
                    logger.error(f"Corruption: Line {i} is not valid JSON.")
                    tampered_indices.append(i)
                    continue
                
                # 1. Verify index sequence
                entry_index = entry.get("index")
                if entry_index != i:
                    logger.warning(f"Integrity check failed: index mismatch at line {i} (got {entry_index})")
                    tampered_indices.append(i)
                    
                # 2. Verify hash value matches computed hash
                recorded_hash = entry.get("hash")
                computed_hash = self._calculate_hash(entry)
                if recorded_hash != computed_hash:
                    logger.warning(f"Integrity check failed: hash mismatch at index {entry_index}")
                    if entry_index not in tampered_indices:
                        tampered_indices.append(entry_index)
                
                # 3. Verify prev_hash link matches previous entry hash
                recorded_prev_hash = entry.get("prev_hash")
                if recorded_prev_hash != expected_prev_hash:
                    logger.warning(f"Integrity check failed: chain broken at index {entry_index}")
                    if entry_index not in tampered_indices:
                        tampered_indices.append(entry_index)
                
                # Set expected_prev_hash for next iteration to current computed_hash
                expected_prev_hash = computed_hash
                
        except Exception as e:
            logger.error(f"Error reading audit log for verification: {e}")
            return False, [-1]
            
        is_valid = len(tampered_indices) == 0
        return is_valid, tampered_indices
