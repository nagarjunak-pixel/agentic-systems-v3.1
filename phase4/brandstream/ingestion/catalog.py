import csv
import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("BrandStream.Catalog")

class CatalogIngestor:
    def __init__(self):
        pass

    def parse_csv(self, filepath: str) -> List[Dict[str, Any]]:
        """Parses a CSV catalog file using stdlib csv module."""
        results = []
        if not os.path.exists(filepath):
            logger.error(f"CSV file not found: {filepath}")
            return results
            
        with open(filepath, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert keys and values to clean strings / numbers
                clean_row = {}
                for k, v in row.items():
                    if k is None:
                        continue
                    key = k.strip().lower()
                    val = v.strip() if v else ""
                    # Try converting numeric values
                    if re.match(r"^\d+$", val):
                        clean_row[key] = int(val)
                    elif re.match(r"^\d+\.\d+$", val):
                        clean_row[key] = float(val)
                    else:
                        clean_row[key] = val
                results.append(clean_row)
        return results

    def parse_pdf_stub(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses a text-based PDF/text file containing catalog data.
        Avoids heavy binary PDF dependencies by reading lines and extracting structured records.
        """
        results = []
        if not os.path.exists(filepath):
            logger.error(f"PDF file not found: {filepath}")
            return results

        try:
            with open(filepath, mode="r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Simple line/regex-based pattern extraction for catalog data
            # e.g., "Location: Paris, Population: 2200000, Competitors: 12"
            pattern = r"(?:Location|Region|City):\s*([a-zA-Z\s]+)(?:,.*?Population:\s*(\d+))?(?:,.*?Competitors:\s*(\d+))?"
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                loc = match[0].strip()
                pop = int(match[1]) if match[1] else 0
                comp = int(match[2]) if match[2] else 0
                results.append({
                    "location": loc,
                    "population": pop,
                    "competitor_count": comp
                })
                
            # If no matches, fall back to checking paragraph/line segments
            if not results:
                lines = content.splitlines()
                for line in lines:
                    if "," in line and ":" in line:
                        parts = line.split(",")
                        row_dict = {}
                        for part in parts:
                            if ":" in part:
                                k, v = part.split(":", 1)
                                key = k.strip().lower()
                                val = v.strip()
                                if val.isdigit():
                                    row_dict[key] = int(val)
                                else:
                                    row_dict[key] = val
                        if row_dict:
                            results.append(row_dict)
        except Exception as e:
            logger.error(f"Error parsing PDF stub: {e}")
            
        return results

    def parse_excel_stub(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses a TSV/CSV disguised as Excel, or falls back to reading rows from mock text format.
        Avoids heavy openpyxl/pandas dependencies.
        """
        results = []
        if not os.path.exists(filepath):
            logger.error(f"Excel file not found: {filepath}")
            return results

        try:
            # Try reading as tab-separated values or text lines
            with open(filepath, mode="r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                f.seek(0)
                if "\t" in first_line:
                    reader = csv.DictReader(f, delimiter="\t")
                    for row in reader:
                        results.append({k.strip().lower(): v.strip() for k, v in row.items() if k})
                else:
                    # Generic line parser
                    reader = csv.DictReader(f)
                    for row in reader:
                        results.append({k.strip().lower(): v.strip() for k, v in row.items() if k})
        except Exception as e:
            logger.error(f"Error parsing Excel stub: {e}")
            
        return results

    def identify_underserved_targets(self, catalog_data: List[Dict[str, Any]], max_density: float = 0.05) -> List[Dict[str, Any]]:
        """
        Identifies underserved market locations.
        A location is underserved if:
        - competitor_count is 0, or
        - competitor_count / (population / 1000) < max_density (competitors per 1k people)
        """
        underserved = []
        for entry in catalog_data:
            location = entry.get("location") or entry.get("city") or entry.get("region")
            if not location:
                continue
                
            population = entry.get("population") or entry.get("pop") or 0
            competitors = entry.get("competitor_count") or entry.get("competitors") or 0
            
            try:
                population = float(population)
                competitors = float(competitors)
            except (ValueError, TypeError):
                continue
                
            if population <= 0:
                continue
                
            # Compute density per 1000 people
            density = competitors / (population / 1000.0)
            
            if competitors == 0 or density < max_density:
                entry_copy = dict(entry)
                entry_copy["market_density"] = round(density, 4)
                entry_copy["underserved"] = True
                underserved.append(entry_copy)
                
        return underserved
