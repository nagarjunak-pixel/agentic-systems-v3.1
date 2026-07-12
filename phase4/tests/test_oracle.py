import pytest
from brandstream.creative.oracle import CreativeDirector, VisualBlueprintAnalyzer

def test_oracle_voice_guide_compliance():
    # Configure voice guide with specific banned terms
    voice_guide = {
        "banned_terms": ["guaranteed success", "cheapest price", "100% risk free", "cheapest"]
    }
    director = CreativeDirector(model_router=None, voice_guide=voice_guide)

    # Clean copy should pass
    clean_copy = "We offer a premium aesthetic layout with coordinates. Check out our high engagement results."
    is_compliant, violated = director.verify_voice_compliance(clean_copy)
    assert is_compliant is True
    assert len(violated) == 0

    # Non-compliant copy with banned term
    bad_copy = "Get our product now! We provide guaranteed success at the cheapest price."
    is_compliant_bad, violated_bad = director.verify_voice_compliance(bad_copy)
    assert is_compliant_bad is False
    assert "guaranteed success" in violated_bad
    assert "cheapest price" in violated_bad

def test_visual_blueprint_analyzer():
    analyzer = VisualBlueprintAnalyzer()
    
    # Style reference string with coordinates and weathering
    ref_text = "style: split-screen, aspect_ratio: 16:9, text_position: [0.15, 0.20, 0.85, 0.50], weathering: rust"
    
    specs = analyzer.extract_layout_specs(ref_text)
    
    assert specs["layout"] == "split-screen"
    assert specs["aspect_ratio"] == "16:9"
    assert specs["coordinates"] == [0.15, 0.20, 0.85, 0.50]
    assert specs["weathering"] == "rust"

    # Minimal reference
    minimal_ref = "style: grid"
    specs_min = analyzer.extract_layout_specs(minimal_ref)
    assert specs_min["layout"] == "grid"
    assert specs_min["aspect_ratio"] == "16:9" # default
    assert specs_min["coordinates"] == [0.0, 0.0, 1.0, 1.0] # default
    assert specs_min["weathering"] == "none" # default

def test_oracle_factual_alignment():
    director = CreativeDirector(model_router=None) # fallback rule-based factual check
    
    research = "Performance: 35% higher engagement on vertically oriented narratives. Spatial coordinates [0.1, 0.2, 0.8, 0.4]."
    
    # 1. Aligned copy (uses exactly 35%)
    aligned_copy = "Our campaign gets 35% higher engagement using our premium editor!"
    aligned, reason = director.verify_factual_alignment(aligned_copy, research)
    assert aligned is True
    assert reason == "ALLOWED"

    # 2. Misaligned copy (hallucinates 45% engagement claim)
    misaligned_copy = "Our campaign gets 45% higher engagement using our premium editor!"
    aligned_bad, reason_bad = director.verify_factual_alignment(misaligned_copy, research)
    assert aligned_bad is False
    assert "45%" in reason_bad

def test_oracle_draft_script():
    director = CreativeDirector(model_router=None) # rule-based compiler fallback
    
    research = """
    # Competitor Research: Acme
    Style reference: style: split-screen, aspect_ratio: 9:16, text_position: [0.1, 0.1, 0.9, 0.4]
    Claims: 35% higher engagement
    """
    
    draft = director.draft_script(research)
    
    assert "narration" in draft
    assert "storyboard" in draft
    assert len(draft["storyboard"]) == 3
    assert draft["visual_blueprint"]["layout"] == "split-screen"
    assert draft["visual_blueprint"]["aspect_ratio"] == "9:16"
    assert draft["visual_blueprint"]["coordinates"] == [0.1, 0.1, 0.9, 0.4]
