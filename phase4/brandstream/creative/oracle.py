import re
import json
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("BrandStream.Oracle")

class VisualBlueprintAnalyzer:
    """
    Extracts spatial layout specifications, ratios, and coordinates
    from style-reference text (V024).
    """
    def __init__(self):
        pass

    def extract_layout_specs(self, style_ref_text: str) -> Dict[str, Any]:
        """
        Parses text references like 'layout: split-screen, aspect_ratio: 16:9, coordinates: [0.15, 0.2, 0.85, 0.5]'
        to return structured visual specs.
        """
        specs = {
            "layout": "default",
            "aspect_ratio": "16:9",
            "coordinates": [0.0, 0.0, 1.0, 1.0],
            "weathering": "none"
        }
        
        # 1. Parse layout
        layout_match = re.search(r"(?:layout|style):\s*([a-zA-Z0-9\-]+)", style_ref_text, re.IGNORECASE)
        if layout_match:
            specs["layout"] = layout_match.group(1).strip().lower()
            
        # 2. Parse aspect ratio
        ratio_match = re.search(r"(?:ratio|aspect_ratio|aspect):\s*(\d+:\d+)", style_ref_text, re.IGNORECASE)
        if ratio_match:
            specs["aspect_ratio"] = ratio_match.group(1).strip()
            
        # 3. Parse coordinates [x1, y1, x2, y2]
        coord_match = re.search(r"(?:coordinates|bounds|text_position):\s*\[([\d\.,\s]+)\]", style_ref_text, re.IGNORECASE)
        if coord_match:
            try:
                coords = [float(c.strip()) for c in coord_match.group(1).split(",")]
                if len(coords) == 4:
                    specs["coordinates"] = coords
            except ValueError:
                pass
                
        # 4. Parse weathering parameters (V024)
        weathering_match = re.search(r"weathering:\s*([a-zA-Z0-9]+)", style_ref_text, re.IGNORECASE)
        if weathering_match:
            specs["weathering"] = weathering_match.group(1).strip().lower()
            
        return specs


class DynamicLocalization:
    """
    Translates copy and scripts into N locales (V054).
    Uses ModelRouter if available, else falls back to prefix-based mock translation.
    """
    def __init__(self, model_router: Optional[Any] = None, budget_manager: Optional[Any] = None):
        self.model_router = model_router
        self.budget_manager = budget_manager

    def translate_copy(self, copy: str, locales: List[str]) -> Dict[str, str]:
        """
        Translates text to each locale in the list.
        """
        translations = {}
        for locale in locales:
            locale_clean = locale.strip().upper()
            if self.model_router:
                prompt = f"Translate the following promotional text into {locale_clean}. Output ONLY the direct translation:\n\n{copy}"
                try:
                    if self.budget_manager:
                        translated = self.budget_manager.wrap_router_call(
                            self.model_router, "localization", "validation", prompt
                        )
                    else:
                        translated = self.model_router.route("validation", prompt)
                    translations[locale_clean] = translated.strip()
                    continue
                except Exception as e:
                    logger.debug(f"LLM translation failed for {locale_clean}: {e}. Falling back to mock.")
            
            # Mock fallback translation
            translations[locale_clean] = self._mock_translation(copy, locale_clean)
            
        return translations

    def _mock_translation(self, text: str, locale: str) -> str:
        dict_mock = {
            "FR": {
                "competitor research": "recherche de concurrents",
                "premium visual styling": "style visuel haut de gamme",
                "overview": "aperçu",
                "hello": "bonjour",
                "welcome": "bienvenue"
            },
            "DE": {
                "competitor research": "Wettbewerberforschung",
                "premium visual styling": "erstklassiges visuelles Styling",
                "overview": "Übersicht",
                "hello": "hallo",
                "welcome": "willkommen"
            },
            "ES": {
                "competitor research": "investigación de competidores",
                "premium visual styling": "estilo visual premium",
                "overview": "resumen",
                "hello": "hola",
                "welcome": "bienvenido"
            }
        }
        
        # Simple word replacement if keywords present
        translated_text = text
        lang_dict = dict_mock.get(locale)
        if lang_dict:
            for k, v in lang_dict.items():
                translated_text = re.sub(re.escape(k), v, translated_text, flags=re.IGNORECASE)
                
        if translated_text == text:
            # Suffix if no match occurred
            return f"[{locale}] {text}"
        return translated_text


class CreativeDirector:
    def __init__(self, model_router: Any, budget_manager: Optional[Any] = None, voice_guide: Optional[Dict[str, Any]] = None):
        self.model_router = model_router
        self.budget_manager = budget_manager
        
        # Set default voice guide configuration
        self.voice_guide = voice_guide or {
            "banned_terms": ["guaranteed success", "cheapest price ever", "100% risk free", "cheapest"],
            "tone": "professional, creative"
        }
        
        self.blueprint_analyzer = VisualBlueprintAnalyzer()
        self.localization = DynamicLocalization(model_router, budget_manager)

    def verify_voice_compliance(self, copy: str) -> Tuple[bool, List[str]]:
        """
        Enforces brand Voice Guide (V000).
        Checks for banned terms. Returns (is_compliant, violated_terms).
        """
        banned = self.voice_guide.get("banned_terms", [])
        violated = []
        copy_lower = copy.lower()
        
        for term in banned:
            if term.lower() in copy_lower:
                violated.append(term)
                
        return len(violated) == 0, violated

    def verify_factual_alignment(self, copy: str, research: str) -> Tuple[bool, str]:
        """
        Verifies that proposed script claims match research document metrics.
        Raises error or returns false on deviation (GAP-07 / V000).
        """
        prompt = f"""
Verify if the proposed advertising copy contains any factual deviations or hallucinations compared to the provided competitor research.
Specifically, pay close attention to any percentages, claims, or numerical metrics. If the copy states a claim not backed by the research, it should be rejected.

Research:
{research}

Proposed Copy:
{copy}

Output format:
DECISION: [APPROVED or REJECTED]
REASON: [If rejected, state the exact claim that is unsupported. If approved, write ALLOWED]
"""
        try:
            if self.budget_manager:
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "oracle", "validation", prompt
                )
            else:
                response = self.model_router.route("validation", prompt)
                
            decision_match = re.search(r"DECISION:\s*(APPROVED|REJECTED)", response, re.IGNORECASE)
            reason_match = re.search(r"REASON:\s*(.*)", response, re.IGNORECASE | re.DOTALL)
            
            approved = False
            if decision_match:
                approved = (decision_match.group(1).upper() == "APPROVED")
                
            reason = reason_match.group(1).strip() if reason_match else response
            return approved, reason
        except Exception as e:
            logger.debug(f"LLM factual alignment check failed: {e}. Falling back to rule-based comparison.")
            return self._rule_based_factual_check(copy, research)

    def _rule_based_factual_check(self, copy: str, research: str) -> Tuple[bool, str]:
        """Fallback numeric parser comparing all percentages and numbers in copy vs research."""
        # Find all numbers in copy
        copy_numbers = re.findall(r"(\d+(?:\.\d+)?%?)", copy)
        for num in copy_numbers:
            # If the number is a statistic (e.g. 35%), verify it is in research text
            if "%" in num or "." in num or int(float(num.replace("%", ""))) > 5:
                # Basic sub-string match check
                if num not in research:
                    return False, f"Rejected: The claim '{num}' was not found in competitor research."
        return True, "ALLOWED"

    def draft_script(self, research_data: str) -> Dict[str, Any]:
        """
        Drafts scripts/storyboards/narration from ingested research.
        Extracts visual layout specifications using VisualBlueprintAnalyzer.
        """
        prompt = f"""
Based on the following competitor research, write a high-converting promotional video script:
{research_data}

Provide:
1. Script narration (dialogue/audio script)
2. Storyboard descriptions (visual sequence of frames)
3. Style reference specifications (ratio: 16:9, layout: split, text_position: [0.1, 0.2, 0.8, 0.4])

Output inside a formatted JSON:
{{
  "narration": "...",
  "storyboard": [
     {{"frame": 1, "visual": "...", "audio": "..."}}
  ],
  "style_reference": "..."
}}
"""
        try:
            if self.budget_manager:
                response = self.budget_manager.wrap_router_call(
                    self.model_router, "oracle", "code_generation", prompt
                )
            else:
                response = self.model_router.route("code_generation", prompt)
                
            match = re.search(r"({.*})", response, re.DOTALL)
            if match:
                draft_data = json.loads(match.group(1).strip())
            else:
                raise ValueError("JSON block not found in output")
        except Exception as e:
            logger.debug(f"LLM script drafting failed ({e}). Falling back to rule-based compiler.")
            draft_data = self._rule_based_draft(research_data)

        # Apply VisualBlueprintAnalyzer to extract layout specs from the draft's style reference
        style_ref = draft_data.get("style_reference", "")
        layout_specs = self.blueprint_analyzer.extract_layout_specs(style_ref)
        draft_data["visual_blueprint"] = layout_specs
        
        return draft_data

    def _rule_based_draft(self, research_data: str) -> Dict[str, Any]:
        """Fallback script drafter."""
        # Simple extraction of key details
        claim_match = re.search(r"(\d+%?\s*higher\s*engagement)", research_data, re.IGNORECASE)
        claim = claim_match.group(1) if claim_match else "higher engagement and compliance"
        
        # Look for styling references
        style_match = re.search(r"style reference:\s*(.*)", research_data, re.IGNORECASE)
        style_ref = style_match.group(1).strip() if style_match else "layout: split, ratio: 16:9, text_position: [0.1, 0.2, 0.8, 0.4]"
        
        return {
            "narration": f"Are you ready for premium visual styling? Our tools deliver {claim}. Experience absolute compliance today!",
            "storyboard": [
                {"frame": 1, "visual": "Intro screen showing dynamic transition", "audio": "Are you ready for premium visual styling?"},
                {"frame": 2, "visual": "Highlighting performance metrics showing engagement metrics", "audio": f"Our tools deliver {claim}."},
                {"frame": 3, "visual": "Outro logo screen with trust indicators", "audio": "Experience absolute compliance today!"}
            ],
            "style_reference": style_ref
        }
