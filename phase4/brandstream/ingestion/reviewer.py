import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("BrandStream.Reviewer")

class MLMSemanticReviewer:
    def __init__(self, model_router: Any, budget_manager: Optional[Any] = None):
        self.model_router = model_router
        self.budget_manager = budget_manager

    def review_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reviews and prunes scraped metadata.
        Uses ModelRouter/BudgetManager to run semantic pruning of metadata attributes (V023).
        If offline or router fails, falls back to a deterministic rule-based pruning engine.
        """
        prompt = f"""
You are an MLM Semantic Reviewer. Your task is to prune and clean the following web-scraped competitor campaign metadata.
Filter out low-quality tags (empty, too generic like 'stuff', or duplicates), prune irrelevant fields, and verify spatial coordinates syntax.

Input Metadata:
{json.dumps(metadata, indent=2)}

Output the cleaned metadata as a raw JSON object ONLY, containing:
1. "cleaned_title": a clean campaign title.
2. "pruned_tags": a list of high-quality campaign tags (filtered).
3. "quality_score": float between 0.0 and 1.0.
4. "valid_spatial_bounds": boolean (checks if bounding boxes [x1, y1, x2, y2] are within [0,1]).
5. "pruned": boolean (set true if the metadata is junk and should be ignored).

JSON output:
"""
        try:
            # Attempt LLM-based evaluation
            if self.budget_manager:
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "reviewer", "validation", prompt
                )
            else:
                response = self.model_router.route("validation", prompt)
            
            # Clean up JSON blocks
            import re
            match = re.search(r"({.*})", response, re.DOTALL)
            if match:
                cleaned_data = json.loads(match.group(1).strip())
                logger.info(f"MLM Reviewer pruned metadata successfully via LLM: {cleaned_data}")
                return cleaned_data
            else:
                raise ValueError("Could not find JSON object in LLM response")
        except Exception as e:
            logger.debug(f"LLM semantic review failed ({e}). Falling back to rule-based pruning engine.")
            return self._rule_based_prune(metadata)

    def _rule_based_prune(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback deterministic pruning engine."""
        title = metadata.get("title", "").strip() or "Untitled Campaign"
        raw_tags = metadata.get("tags", [])
        
        # Rule 1: Filter out short or generic tags
        generic_terms = {"stuff", "things", "test", "demo", "temp", "n/a", "none"}
        pruned_tags = []
        for tag in raw_tags:
            t = str(tag).strip().lower()
            if len(t) >= 2 and t not in generic_terms:
                pruned_tags.append(t)
                
        # Rule 2: Verify spatial bounds if present
        spatial_bounds = metadata.get("spatial_bounds", [])
        valid_spatial = False
        if isinstance(spatial_bounds, list) and len(spatial_bounds) == 4:
            try:
                valid_spatial = all(0.0 <= float(coord) <= 1.0 for coord in spatial_bounds)
            except (ValueError, TypeError):
                valid_spatial = False
                
        # Rule 3: Quality scoring
        quality_score = 0.1
        if title != "Untitled Campaign":
            quality_score += 0.3
        if len(pruned_tags) >= 2:
            quality_score += 0.3
        if valid_spatial:
            quality_score += 0.3
            
        pruned = quality_score < 0.4
        
        return {
            "cleaned_title": title,
            "pruned_tags": pruned_tags,
            "quality_score": round(quality_score, 2),
            "valid_spatial_bounds": valid_spatial,
            "pruned": pruned
        }
