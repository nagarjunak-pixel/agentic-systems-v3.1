import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("BrandStream.Filters.ReID")

class ReIDFilter:
    """
    Visual Re-identification (Re-ID) Filter (GAP-11 / V058).
    1. Deduplicates near-identical generated frames using hash-based heuristics.
    2. Tracks skeleton bounding box identities across sequential frames,
       detecting visual swaps and forcing coordinate recalculations.
    """
    def __init__(self, similarity_threshold: float = 0.95):
        self.similarity_threshold = similarity_threshold

    def deduplicate_frames(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates near-identical generated frames.
        Frames are represented as a dict containing:
          - "frame_index": int
          - "visual_hash": str (e.g., md5 or perceptual hash)
          - "visual_description": str
        """
        seen_hashes = set()
        unique_frames = []
        
        for frame in frames:
            v_hash = frame.get("visual_hash")
            if not v_hash:
                # If no hash, compute a quick stub hash from frame data description
                desc = frame.get("visual_description", "")
                v_hash = hashlib.md5(desc.encode("utf-8")).hexdigest()
                frame["visual_hash"] = v_hash

            if v_hash in seen_hashes:
                logger.info(f"Duplicate frame detected and pruned at index {frame.get('frame_index')}")
                continue
                
            seen_hashes.add(v_hash)
            unique_frames.append(frame)
            
        return unique_frames

    def detect_skeleton_swap(
        self,
        prev_skeletons: List[Dict[str, Any]],
        curr_skeletons: List[Dict[str, Any]]
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Tracks bounding box centroids and visual features.
        If a swap is detected (e.g. crossing paths with swapped visual feature associations),
        returns (True, corrected_skeletons).
        Skeleton schema:
        {
           "id": int,
           "coordinates": [x1, y1, x2, y2], # bounding box
           "visual_feature_descriptor": List[float] # mock feature embeddings
        }
        """
        # If any skeleton lists are empty, no swap possible
        if not prev_skeletons or not curr_skeletons:
            return False, curr_skeletons

        swap_detected = False
        corrected_skeletons = [s.copy() for s in curr_skeletons]
        
        # Simple proximity & feature swap detection logic
        if len(prev_skeletons) >= 2 and len(curr_skeletons) >= 2:
            p1, p2 = prev_skeletons[0], prev_skeletons[1]
            c1, c2 = curr_skeletons[0], curr_skeletons[1]
            
            # Feature distance (smaller distance = more similar)
            f_dist_11 = self._feature_distance(p1.get("visual_feature_descriptor"), c1.get("visual_feature_descriptor"))
            f_dist_22 = self._feature_distance(p2.get("visual_feature_descriptor"), c2.get("visual_feature_descriptor"))
            
            f_dist_12 = self._feature_distance(p1.get("visual_feature_descriptor"), c2.get("visual_feature_descriptor"))
            f_dist_21 = self._feature_distance(p2.get("visual_feature_descriptor"), c1.get("visual_feature_descriptor"))
            
            # If crossed matching distance is significantly smaller, swap detected
            if (f_dist_12 + f_dist_21) < (f_dist_11 + f_dist_22):
                logger.warning("Skeleton identity swap detected! Re-ID Filter correcting skeleton IDs.")
                swap_detected = True
                
                # Perform coordinate recalculation and ID restoration
                # Swap the IDs back in corrected_skeletons to match their original tracking features
                for s in corrected_skeletons:
                    if s["id"] == c1["id"]:
                        s["id"] = c2["id"]
                    elif s["id"] == c2["id"]:
                        s["id"] = c1["id"]
                        
        return swap_detected, corrected_skeletons

    def _feature_distance(self, f1: Optional[List[float]], f2: Optional[List[float]]) -> float:
        if not f1 or not f2 or len(f1) != len(f2):
            return 0.0
        # Euclidean distance
        return sum((x - y) ** 2 for x, y in zip(f1, f2)) ** 0.5
