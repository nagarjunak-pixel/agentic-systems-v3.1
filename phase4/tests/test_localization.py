import pytest
from brandstream.creative.oracle import DynamicLocalization

def test_dynamic_localization_mock():
    loc = DynamicLocalization(model_router=None) # fallback mock mode
    
    copy = "hello welcome overview competitor research"
    locales = ["FR", "DE", "ES", "IT"]
    
    translations = loc.translate_copy(copy, locales)
    
    assert "FR" in translations
    assert "DE" in translations
    assert "ES" in translations
    assert "IT" in translations
    
    # FR translations should translate 'hello' -> 'bonjour', 'welcome' -> 'bienvenue' etc.
    assert "bonjour" in translations["FR"]
    assert "bienvenue" in translations["FR"]
    
    # ES translations should translate 'hello' -> 'hola', 'welcome' -> 'bienvenido'
    assert "hola" in translations["ES"]
    assert "bienvenido" in translations["ES"]
    
    # IT should use fallback prefix mock format because it is not in the default dictionary
    assert "[IT] hello welcome overview competitor research" in translations["IT"]
