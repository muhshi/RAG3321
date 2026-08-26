"""
BPS Publication Scraper & Ingestion Module.
Crawls BPS Demak publications, verifies against registry, downloads PDFs,
and stores them organized by year and month.
"""
import os
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

from config.settings import settings
from modules.ingestion.registry import PublicationRegistry


class BPSPublicationScraper:
    """Automates scraping, tracking, and downloading BPS publications."""

    MONTH_MAP_ID = {
        "januari": "01", "jan": "01",
        "februari": "02", "feb": "02",
        "maret": "03", "mar": "03",
        "april": "04", "apr": "04",
        "mei": "05",
        "juni": "06", "jun": "06",
        "juli": "07", "jul": "07",
        "agustus": "08", "agu": "08", "agt": "08",
        "september": "09", "sep": "09",
        "oktober": "10", "okt": "10",
        "november": "11", "nov": "11",
        "desember": "12", "des": "12",
    }

    # Browser headers to pass government WAF / bot-checks
    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        registry: Optional[PublicationRegistry] = None,
        target_dir: Optional[Path] = None
    ):
        self.base_url = base_url or settings.BPS_BASE_URL
        self.registry = registry or PublicationRegistry()
        self.target_dir = target_dir or settings.DEMAK_DATA_DIR
        self.session = httpx.Client(
            headers=self.BROWSER_HEADERS,
            timeout=settings.REQUEST_TIMEOUT,
            follow_redirects=True
        )

    def _slugify(self, text: str) -> str:
        """Converts arbitrary strings into safe filenames."""
        text = text.lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "_", text)
        return text.strip("_")[:80]

    def _parse_indonesian_date(self, date_str: str) -> str:
        """Normalizes Indonesian date strings to YYYY-MM-DD."""
        if not date_str:
            return datetime.utcnow().strftime("%Y-%m-%d")
        
        date_str_clean = date_str.strip().lower()
        
        # Match YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str_clean):
            return date_str_clean
            
        # Match DD Month YYYY
        match = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", date_str_clean)
        if match:
            day, month_str, year = match.groups()
            month = self.MONTH_MAP_ID.get(month_str, "01")
            return f"{year}-{month}-{int(day):02d}"
            
        # Match Month YYYY
        match_my = re.search(r"([a-zA-Z]+)\s+(\d{4})", date_str_clean)
        if match_my:
            month_str, year = match_my.groups()
            month = self.MONTH_MAP_ID.get(month_str, "01")
            return f"{year}-{month}-01"

        return datetime.utcnow().strftime("%Y-%m-%d")

    def fetch_publication_list(self, max_pages: int = 1, keyword: str = "Demak") -> List[Dict[str, Any]]:
        """
        Crawls the BPS publication directory pages.
        Extracts metadata for each publication card.
        """
        publications: List[Dict[str, Any]] = []
        logger.info(f"Starting BPS publication discovery for {self.base_url} (Max pages: {max_pages})")

        # Try regional URL first, fallback to central BPS if regional blocks
        urls_to_try = [
            (self.base_url, f"{self.base_url}{settings.BPS_PUBLICATION_PATH}"),
            (settings.BPS_CENTRAL_URL, f"{settings.BPS_CENTRAL_URL}/id/publication")
        ]

        for base, endpoint in urls_to_try:
            if publications:
                break

            for page in range(1, max_pages + 1):
                url = f"{endpoint}?page={page}&keyword={keyword}"
                logger.info(f"Fetching publication catalog page {page}: {url}")

                try:
                    response = self.session.get(url)
                    if response.status_code != 200:
                        logger.warning(f"Response status {response.status_code} for {url}")
                        continue

                    soup = BeautifulSoup(response.text, "lxml")
                    items = soup.select(".card, .list-publication, article, .item-publication, tr, div.publication-item")
                    
                    if not items:
                        items = soup.find_all(["div", "article"], class_=lambda c: c and ("pub" in c.lower() or "card" in c.lower()))

                    for item in items:
                        pub_data = self._parse_publication_item(item, base_url=base)
                        if pub_data:
                            publications.append(pub_data)

                    if publications:
                        logger.info(f"Found {len(publications)} publications on {base}")
                        break

                except Exception as e:
                    logger.warning(f"Error connecting to {url}: {e}")

        return publications

    def _parse_publication_item(self, item: BeautifulSoup, base_url: str) -> Optional[Dict[str, Any]]:
        """Extracts publication metadata fields from an HTML node."""
        title_tag = item.find(["h2", "h3", "h4", "h5", "a"], class_=lambda c: c and ("title" in c.lower() or "judul" in c.lower()))
        if not title_tag:
            title_tag = item.find("a", href=re.compile(r"/publication/|/publikasi/"))
        
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        detail_url = ""
        if title_tag.name == "a" and title_tag.get("href"):
            detail_url = urljoin(base_url, title_tag["href"])
        else:
            link_tag = item.find("a", href=True)
            if link_tag:
                detail_url = urljoin(base_url, link_tag["href"])

        pub_id_match = re.search(r"/publication/(\d+)|/(\d{10,})", detail_url)
        if pub_id_match:
            pub_id = pub_id_match.group(1) or pub_id_match.group(2)
        else:
            pub_id = hashlib.md5(f"{title}_{detail_url}".encode()).hexdigest()[:12]

        date_tag = item.find(string=re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})"))
        date_raw = date_tag.strip() if date_tag else ""
        release_date = self._parse_indonesian_date(date_raw)

        category_tag = item.find(class_=lambda c: c and ("badge" in c.lower() or "category" in c.lower() or "subjek" in c.lower()))
        category = category_tag.get_text(strip=True) if category_tag else "Statistik Umum"

        pdf_tag = item.find("a", href=re.compile(r"\.pdf|/download/|/get/"))
        pdf_url = urljoin(base_url, pdf_tag["href"]) if pdf_tag else detail_url

        return {
            "publication_id": pub_id,
            "title": title,
            "release_date": release_date,
            "category": category,
            "detail_url": detail_url,
            "pdf_url": pdf_url,
            "region": "Kabupaten Demak"
        }

    def resolve_pdf_download_url(self, pub_meta: Dict[str, Any]) -> Optional[str]:
        """Resolves direct PDF download endpoint."""
        pdf_url = pub_meta.get("pdf_url")
        if pdf_url and pdf_url.endswith(".pdf"):
            return pdf_url

        detail_url = pub_meta.get("detail_url") or pdf_url
        if not detail_url:
            return None

        try:
            res = self.session.get(detail_url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "lxml")
                download_btn = soup.find("a", href=re.compile(r"\.pdf|/publication/get/|/download/"))
                if download_btn and download_btn.get("href"):
                    return urljoin(self.base_url, download_btn["href"])
        except Exception as e:
            logger.warning(f"Could not resolve direct PDF link for {pub_meta['publication_id']}: {e}")

        return pdf_url

    def download_pdf(self, pub_meta: Dict[str, Any]) -> Optional[Path]:
        """Downloads the PDF if not already downloaded, organizing into /data_publikasi/demak/YYYY/MM/."""
        pub_id = pub_meta["publication_id"]
        title = pub_meta["title"]
        release_date = pub_meta["release_date"]

        if self.registry.is_already_downloaded(pub_id):
            logger.info(f"Skipping download (Already in registry): [{pub_id}] {title}")
            return None

        download_url = self.resolve_pdf_download_url(pub_meta)
        if not download_url:
            self.registry.mark_download_failed(pub_id)
            return None

        try:
            year, month, _ = release_date.split("-")
        except Exception:
            year, month = datetime.utcnow().strftime("%Y"), datetime.utcnow().strftime("%m")

        target_folder = self.target_dir / year / month
        target_folder.mkdir(parents=True, exist_ok=True)

        filename = f"{pub_id}_{self._slugify(title)}.pdf"
        target_file_path = target_folder / filename

        logger.info(f"Downloading publication [{pub_id}] -> {target_file_path.name}")

        try:
            with self.session.stream("GET", download_url) as stream_resp:
                if stream_resp.status_code != 200:
                    logger.error(f"Download HTTP error {stream_resp.status_code} for {download_url}")
                    self.registry.mark_download_failed(pub_id)
                    return None

                total_size = int(stream_resp.headers.get("content-length", 0))
                with open(target_file_path, "wb") as f, tqdm(
                    total=total_size, unit="B", unit_scale=True, desc=filename[:30]
                ) as pbar:
                    for chunk in stream_resp.iter_bytes(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            file_size = target_file_path.stat().st_size
            self.registry.register_or_update_metadata(pub_meta)
            self.registry.mark_download_success(
                publication_id=pub_id,
                file_path=str(target_file_path),
                file_size=file_size
            )
            return target_file_path

        except Exception as e:
            logger.error(f"Exception during download of {pub_id}: {e}")
            if target_file_path.exists():
                target_file_path.unlink(missing_ok=True)
            self.registry.mark_download_failed(pub_id)
            return None

    def run_ingestion_pipeline(self, max_pages: int = 1) -> List[Dict[str, Any]]:
        discovered_pubs = self.fetch_publication_list(max_pages=max_pages)
        downloaded_items: List[Dict[str, Any]] = []

        for pub in discovered_pubs:
            self.registry.register_or_update_metadata(pub)
            pdf_path = self.download_pdf(pub)
            if pdf_path:
                pub["local_file_path"] = str(pdf_path)
                downloaded_items.append(pub)

        return downloaded_items
