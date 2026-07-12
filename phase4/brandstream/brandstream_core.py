import os
import json
import logging
from typing import Dict, Any, List, Tuple, Optional

# Core imports
from core.wammr.router import ModelRouter
from aisg.guardrails import GuardrailChecker
from abtm.budget import BudgetManager
from wmg.gateway import WebhookMessagingGateway

# BrandStream imports
from brandstream.ingestion.scraper import CompetitorScraper
from brandstream.ingestion.reviewer import MLMSemanticReviewer
from brandstream.ingestion.catalog import CatalogIngestor
from brandstream.creative.oracle import CreativeDirector
from brandstream.audit.auditor import CopyAuditor, ChessValidator, LogicStateValidator

logger = logging.getLogger("BrandStream.CoreSystem")

class BrandStreamAI:
    def __init__(
        self,
        memory_engine: Any,
        model_router: ModelRouter,
        budget_manager: BudgetManager,
        guardrail_checker: GuardrailChecker,
        wmg_gateway: WebhookMessagingGateway,
        connection_id: str = "brandstream_publish_conn"
    ):
        self.memory_engine = memory_engine
        self.model_router = model_router
        self.budget_manager = budget_manager
        self.guardrail_checker = guardrail_checker
        self.wmg_gateway = wmg_gateway
        self.connection_id = connection_id

        # Ingestion
        self.scraper = CompetitorScraper(memory_engine, model_router, budget_manager)
        self.reviewer = MLMSemanticReviewer(model_router, budget_manager)
        self.catalog = CatalogIngestor()

        # Creative
        self.creative = CreativeDirector(model_router, budget_manager)

        # Audit
        self.copy_auditor = CopyAuditor()
        self.chess_validator = ChessValidator()
        self.logic_validator = LogicStateValidator()

    def process_competitor_campaign(self, url: str, name: str, locales: List[str]) -> Dict[str, Any]:
        """
        Full workflow:
        1. Scrape competitor site using Astros Scraper.
        2. Run MLM review on scraped metadata.
        3. Draft copy & storyboard scripts using Oracle.
        4. Validate copy for compliance (safety checking via GuardrailChecker).
        5. Run Parallel Audits on draft:
           - CopyAuditor (style check)
           - LogicStateValidator (coordinates/frames sequence check)
        6. Generate localized copy for specified locales.
        7. Publish notification/results via Webhook Messaging Gateway (WMG).
        """
        logger.info(f"Starting BrandStream workflow for campaign: {name}")

        # 1. Scrape
        scraped_markdown = self.scraper.scrape(url, name)
        
        # Parse basic metadata from scraped output
        metadata = {
            "title": f"Campaign {name}",
            "tags": ["social", "promo", name],
            "spatial_bounds": [0.1, 0.2, 0.8, 0.4]  # from style reference
        }
        
        # 2. MLM review on metadata
        cleaned_meta = self.reviewer.review_metadata(metadata)
        logger.info(f"Cleaned metadata: {cleaned_meta}")
        
        # 3. Oracle draft script
        draft_data = self.creative.draft_script(scraped_markdown)
        narration = draft_data.get("narration", "")
        storyboard = draft_data.get("storyboard", [])
        blueprint = draft_data.get("visual_blueprint", {})
        
        # 4. Guardrail safety check (Phase 1 AISG)
        # Pre-check narration input & output using GuardrailChecker
        is_allowed_in, verdict_in = self.guardrail_checker.check_input("gpt-4o", narration)
        if not is_allowed_in:
            raise ValueError(f"Guardrail safety violation on drafted copy input: {verdict_in}")
            
        is_allowed_out, verdict_out = self.guardrail_checker.check_output("gpt-4o", narration)
        if not is_allowed_out:
            raise ValueError(f"Guardrail safety violation on drafted copy output: {verdict_out}")

        # 5. Parallel Audits
        # A. CopyAuditor (style constraints)
        audit_report = self.copy_auditor.audit_copy(draft_data)
        if not audit_report["valid"]:
            logger.warning(f"Copy Auditor failed: {audit_report['errors']}")
            raise ValueError(f"Copy Auditor failed validation: {audit_report['errors']}")

        # B. LogicStateValidator (storyboard frames sequence)
        seq_valid, seq_msg = self.logic_validator.validate_storyboard_sequence(storyboard)
        if not seq_valid:
            raise ValueError(f"Storyboard sequence invalid: {seq_msg}")

        # C. LogicStateValidator (spatial bounds check)
        bp_valid, bp_msg = self.logic_validator.validate_spatial_blueprint(blueprint)
        if not bp_valid:
            raise ValueError(f"Visual blueprint coordinates invalid: {bp_msg}")
            
        # 6. Localization
        localized_variants = self.creative.localization.translate_copy(narration, locales)

        # 7. Publish Results via WMG (Phase 2 gateway)
        publish_payload = {
            "name": name,
            "original_narration": narration,
            "localized_variants": localized_variants,
            "blueprint": blueprint
        }
        
        message_text = f"Publishing BrandStream Campaign '{name}' successful! Narration: {narration[:60]}..."
        
        try:
            self.wmg_gateway.dispatch_outgoing_message(
                connection_id=self.connection_id,
                recipient="operator_channel",
                message_text=message_text
            )
            logger.info("Published campaign notifications via Webhook Messaging Gateway")
        except Exception as e:
            logger.warning(f"Failed to send publication message via WMG: {e}")

        # Save result to MemoryEngine-backed workspace
        result_file = f"campaigns/{name}_result.json"
        self.memory_engine.write_file_sync(result_file, json.dumps(publish_payload, indent=2))

        return {
            "status": "success",
            "campaign_name": name,
            "draft": draft_data,
            "localized": localized_variants,
            "audit_report": audit_report,
            "saved_result": result_file
        }
