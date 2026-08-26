"""
Ingestion module for BPS publications.
"""
from modules.ingestion.registry import PublicationRegistry
from modules.ingestion.bps_scraper import BPSPublicationScraper

__all__ = ["PublicationRegistry", "BPSPublicationScraper"]
