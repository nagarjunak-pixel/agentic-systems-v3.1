import os
import tempfile
import shutil
import pytest
from core.memory.engine import MemoryEngine
from brandstream.ingestion.scraper import CompetitorScraper
from brandstream.ingestion.reviewer import MLMSemanticReviewer
from brandstream.ingestion.catalog import CatalogIngestor

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def memory_engine(temp_dir):
    engine = MemoryEngine(temp_dir)
    yield engine
    engine.shutdown()

def test_competitor_scraper_offline_fallback(memory_engine):
    scraper = CompetitorScraper(memory_engine)
    # Use an unreachable URL to force fallback or offline mock behavior
    url = "http://offline-competitor-mock.example.com"
    name = "acme_corp"
    
    markdown_content = scraper.scrape(url, name)
    
    assert "Competitor Research: Acme_corp" in markdown_content
    assert "Source URL: http://offline-competitor-mock.example.com" in markdown_content
    
    # Check that file is saved in MemoryEngine
    saved_path = os.path.join(memory_engine.root_dir, f"research/{name}.md")
    assert os.path.exists(saved_path)
    with open(saved_path, "r") as f:
        saved_content = f.read()
    assert saved_content == markdown_content

def test_mlm_semantic_reviewer():
    reviewer = MLMSemanticReviewer(model_router=None) # Offline fallback
    
    # 1. Clean metadata
    metadata = {
        "title": "Aesthetic Summer Collection Ad",
        "tags": ["summer", "fashion", "aesthetic", "stuff", "t"],
        "spatial_bounds": [0.1, 0.2, 0.9, 0.5]
    }
    
    res = reviewer.review_metadata(metadata)
    assert res["cleaned_title"] == "Aesthetic Summer Collection Ad"
    assert "summer" in res["pruned_tags"]
    assert "fashion" in res["pruned_tags"]
    assert "aesthetic" in res["pruned_tags"]
    assert "stuff" not in res["pruned_tags"] # generic tag filtered out
    assert "t" not in res["pruned_tags"] # short tag filtered out
    assert res["valid_spatial_bounds"] is True
    assert res["quality_score"] > 0.5
    assert res["pruned"] is False

    # 2. Low quality metadata
    bad_metadata = {
        "title": "",
        "tags": ["stuff", "none"],
        "spatial_bounds": [1.5, 0.2, 0.9, 0.5] # out of bounds
    }
    res_bad = reviewer.review_metadata(bad_metadata)
    assert res_bad["cleaned_title"] == "Untitled Campaign"
    assert len(res_bad["pruned_tags"]) == 0
    assert res_bad["valid_spatial_bounds"] is False
    assert res_bad["pruned"] is True

def test_catalog_ingestor(temp_dir):
    ingestor = CatalogIngestor()
    
    # 1. Test CSV Parsing
    csv_path = os.path.join(temp_dir, "catalog.csv")
    with open(csv_path, "w") as f:
        f.write("Location,Population,Competitor_Count\n")
        f.write("New York,8000000,50\n")
        f.write("Austin,1000000,2\n")
        f.write("Nowhereville,5000,0\n")
        
    csv_data = ingestor.parse_csv(csv_path)
    assert len(csv_data) == 3
    assert csv_data[0]["location"] == "New York"
    assert csv_data[0]["population"] == 8000000
    assert csv_data[1]["competitor_count"] == 2

    # 2. Test PDF text-stub Parsing
    pdf_path = os.path.join(temp_dir, "catalog.pdf")
    with open(pdf_path, "w") as f:
        f.write("Location: Paris, Population: 2200000, Competitors: 10\n")
        f.write("Location: Berlin, Population: 3600000, Competitors: 1\n")
        f.write("Location: SmallTown, Population: 8000, Competitors: 0\n")
        
    pdf_data = ingestor.parse_pdf_stub(pdf_path)
    assert len(pdf_data) == 3
    assert pdf_data[0]["location"] == "Paris"
    assert pdf_data[0]["population"] == 2200000
    assert pdf_data[1]["competitor_count"] == 1

    # 3. Test Excel (TSV) Parsing
    excel_path = os.path.join(temp_dir, "catalog.tsv")
    with open(excel_path, "w") as f:
        f.write("Location\tPopulation\tCompetitors\n")
        f.write("London\t9000000\t150\n")
        f.write("Dublin\t500000\t1\n")
        
    excel_data = ingestor.parse_excel_stub(excel_path)
    assert len(excel_data) == 2
    assert excel_data[0]["location"] == "London"
    assert int(excel_data[1]["population"]) == 500000

    # 4. Test identifying underserved targets
    # Combine New York, Austin, Nowhereville, Berlin, Dublin
    combined = [
        {"location": "New York", "population": 8000000, "competitor_count": 50}, # density = 50 / 8000 = 0.00625
        {"location": "Austin", "population": 1000000, "competitor_count": 2}, # density = 2 / 1000 = 0.002
        {"location": "Nowhereville", "population": 5000, "competitor_count": 0}, # density = 0
        {"location": "Dublin", "population": 500000, "competitor_count": 10}, # density = 10 / 500 = 0.02
        {"location": "HighComp", "population": 100000, "competitor_count": 30} # density = 30 / 100 = 0.3
    ]
    
    # We want max_density = 0.01 (competitors per 1k people)
    underserved = ingestor.identify_underserved_targets(combined, max_density=0.01)
    
    # underserved should contain New York (0.00625), Austin (0.002), Nowhereville (0)
    # HighComp (0.3) and Dublin (0.02) should be excluded
    locs = [u["location"] for u in underserved]
    assert "New York" in locs
    assert "Austin" in locs
    assert "Nowhereville" in locs
    assert "HighComp" not in locs
    assert "Dublin" not in locs
