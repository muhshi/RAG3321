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

    def _fetch_url_text_curl(self, url: str) -> str:
        """Fetches page content using curl.exe to pass government security checks."""
        import subprocess
        try:
            res = subprocess.run(
                ["curl.exe", "-s", "-L", "--max-time", "30", url],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if res.returncode == 0:
                return res.stdout
        except Exception as e:
            logger.warning(f"curl.exe fetch failed for {url}: {e}")
        return ""

    def fetch_publication_list(self, max_pages: int = 2, keyword: str = "Demak") -> List[Dict[str, Any]]:
        """
        Crawls the BPS publication catalog and search engine.
        Extracts metadata for all Demak publications.
        """
        publications: List[Dict[str, Any]] = []
        seen_urls = set()
        logger.info(f"Starting BPS publication discovery for keyword '{keyword}' (Max pages: {max_pages})")

        search_targets = [
            # 1. Broad Demak & Compendiums
            ("Demak", "3321"),
            ("Demak", "all"),
            ("Kabupaten Demak", "3321"),
            ("Kecamatan", "3321"),
            ("Statistik", "3321"),
            ("Angka", "3321"),
            ("Daerah", "3321"),
            ("Sensus", "3321"),
            ("Pertanian", "3321"),
            ("PDRB", "3321"),
            ("Kesejahteraan", "3321"),
            ("Kemiskinan", "3321"),
            ("Kependudukan", "3321"),
            ("Profil", "3321"),
            ("Indikator", "3321"),
            ("Ketenagakerjaan", "3321"),
            ("Tenaga Kerja", "3321"),
            ("Perikanan", "3321"),
            ("Pelelangan Ikan", "3321"),
            ("Hortikultura", "3321"),
            ("Industri", "3321"),
            ("Kesehatan", "3321"),
            ("Pendidikan", "3321"),
            ("Potensi Desa", "3321"),
            ("Podes", "3321"),
            ("IPM", "3321"),
            # 2. All 14 Kecamatan in Demak
            ("Mranggen", "3321"),
            ("Sayung", "3321"),
            ("Karangawen", "3321"),
            ("Guntur", "3321"),
            ("Bonang", "3321"),
            ("Wedung", "3321"),
            ("Mijen", "3321"),
            ("Gajah", "3321"),
            ("Karanganyar", "3321"),
            ("Karangtengah", "3321"),
            ("Wonosalam", "3321"),
            ("Dempet", "3321"),
            ("Kebonagung", "3321"),
            ("Demak", "3321"),
            # 3. Notable Desa & Kelurahan in Demak
            ("Bintoro", "3321"),
            ("Kadilangu", "3321"),
            ("Batursari", "3321"),
            ("Morosari", "3321"),
            ("Bedono", "3321"),
            ("Betahwalang", "3321"),
            ("Morodemak", "3321"),
            ("Jragung", "3321"),
            ("Buko", "3321"),
            ("Tedunan", "3321"),
            ("Pecuk", "3321"),
            ("Undaan", "3321"),
            ("Wilalung", "3321"),
            ("Trengguli", "3321"),
            ("Tlogoweru", "3321"),
            ("Trimulyo", "3321")
        ]

        seen_pub_ids = set()

        for kw, mfd in search_targets:
            for page in range(1, max_pages + 1):
                search_url = (
                    f"http://searchengine.web.bps.go.id/search"
                    f"?q={kw.replace(' ', '+')}&content=publication&page={page}"
                    f"&title=0&mfd={mfd}&from=all&to=all&sort=relevansi"
                )
                html = self._fetch_url_text_curl(search_url)
                if not html:
                    break

                soup = BeautifulSoup(html, "lxml")
                links = soup.find_all("a", href=True)
                new_in_page = 0
                has_demak_link = False

                for a in links:
                    href = a["href"]
                    if "/publication/" in href and "demakkab.bps.go.id" in href:
                        has_demak_link = True
                        if href not in seen_urls:
                            seen_urls.add(href)
                            parent = a.find_parent(["div", "tr", "li", "article"])
                            title = ""
                            desc = ""
                            if parent:
                                lines = [l.strip() for l in parent.stripped_strings if len(l.strip()) > 3]
                                if len(lines) >= 2 and not lines[1].startswith("http"):
                                    title = lines[1]
                                elif lines:
                                    title = lines[0]
                                if len(lines) >= 3:
                                    desc = lines[2]
                            if not title:
                                title = a.get_text(strip=True)

                            pub_id_match = re.search(r"/publication/(\d{4})/(\d{2})/(\d{2})/([a-f0-9]+)/", href)
                            if pub_id_match:
                                y, m, d, h = pub_id_match.groups()
                                rel_date = f"{y}-{m}-{d}"
                            else:
                                rel_date = datetime.utcnow().strftime("%Y-%m-%d")

                            slug_title = self._slugify(title)[:60]
                            pub_id = f"{rel_date}_{slug_title}"

                            if pub_id in seen_pub_ids:
                                if pub_id_match:
                                    pub_id = f"{rel_date}_{slug_title}_{h[:6]}"
                                else:
                                    count = 2
                                    while f"{pub_id}_{count}" in seen_pub_ids:
                                        count += 1
                                    pub_id = f"{pub_id}_{count}"
                            seen_pub_ids.add(pub_id)

                            # Determine category
                            cat = "Statistik Umum"
                            tl = title.lower()
                            if "ikan" in tl or "perikanan" in tl:
                                cat = "Perikanan"
                            elif "tani" in tl or "panen" in tl or "padi" in tl:
                                cat = "Pertanian"
                            elif "hortikultura" in tl:
                                cat = "Pertanian & Hortikultura"
                            elif "sejahtera" in tl or "sosial" in tl or "miskin" in tl:
                                cat = "Kesejahteraan & Sosial"
                            elif "tenaga" in tl or "kerja" in tl:
                                cat = "Ketenagakerjaan"
                            elif "angka" in tl or "daerah" in tl:
                                cat = "Statistik Umum & Kompendium"
                            elif "industri" in tl:
                                cat = "Industri & UMKM"
                            elif "pdrb" in tl or "ekonomi" in tl:
                                cat = "Ekonomi & PDRB"
                            elif "sehat" in tl or "kesehatan" in tl:
                                cat = "Kesehatan"
                            elif "didik" in tl or "pendidikan" in tl:
                                cat = "Pendidikan"

                            pub_data = {
                                "publication_id": pub_id,
                                "title": title,
                                "release_date": rel_date,
                                "category": cat,
                                "detail_url": href,
                                "pdf_url": href,
                                "description": desc,
                                "region": "Kabupaten Demak"
                            }
                            publications.append(pub_data)
                            new_in_page += 1

                if not has_demak_link or (new_in_page == 0 and page > 2):
                    break

        logger.info(f"Discovered total of {len(publications)} BPS Demak publications across all keywords and kecamatan.")
        return publications

    def resolve_pdf_download_url(self, pub_meta: Dict[str, Any]) -> Optional[str]:
        """Resolves direct PDF download endpoint using curl."""
        detail_url = pub_meta.get("detail_url") or pub_meta.get("pdf_url")
        if not detail_url:
            return None

        html = self._fetch_url_text_curl(detail_url)
        if html:
            soup = BeautifulSoup(html, "lxml")
            download_btn = soup.find("a", href=lambda h: h and ("download.php" in h or ".pdf" in h))
            if download_btn and download_btn.get("href"):
                return download_btn["href"]

        return None

    def download_pdf(self, pub_meta: Dict[str, Any]) -> Optional[Path]:
        """Downloads the PDF using curl and validates integrity."""
        pub_id = pub_meta["publication_id"]
        title = pub_meta["title"]
        release_date = pub_meta.get("release_date", "2026-01-01")

        try:
            year, month, _ = release_date.split("-")
        except Exception:
            year, month = "2026", "01"

        target_folder = self.target_dir / year / month
        target_folder.mkdir(parents=True, exist_ok=True)

        filename = f"{pub_id}.pdf"
        target_file_path = target_folder / filename

        # If already exists and is a valid PDF (> 1000 bytes)
        if target_file_path.exists() and target_file_path.stat().st_size > 1000:
            file_size = target_file_path.stat().st_size
            self.registry.register_or_update_metadata(pub_meta)
            self.registry.mark_download_success(pub_id, str(target_file_path), file_size)
            logger.info(f"Using cached publication on disk: {target_file_path.name}")
            return target_file_path

        if self.registry.is_already_downloaded(pub_id):
            logger.info(f"Skipping download (Already in registry): [{pub_id}] {title}")
            return None

        download_url = self.resolve_pdf_download_url(pub_meta)
        if not download_url:
            logger.warning(f"Could not resolve download button for [{pub_id}] {title}")
            self.registry.mark_download_failed(pub_id)
            return None

        logger.info(f"Downloading publication [{pub_id}] -> {target_file_path.name}")

        import subprocess
        try:
            res = subprocess.run(
                ["curl.exe", "-s", "-L", "--max-time", "120", "-o", str(target_file_path), download_url],
                capture_output=True
            )
            if res.returncode == 0 and target_file_path.exists():
                file_size = target_file_path.stat().st_size
                # Verify header
                with open(target_file_path, "rb") as fp:
                    header = fp.read(10)
                if b"%PDF" in header and file_size > 1000:
                    logger.success(f"Downloaded {target_file_path.name} ({file_size:,} bytes).")
                    self.registry.register_or_update_metadata(pub_meta)
                    self.registry.mark_download_success(
                        publication_id=pub_id,
                        file_path=str(target_file_path),
                        file_size=file_size
                    )
                    return target_file_path
                else:
                    logger.warning(f"Downloaded file for {pub_id} is not a valid PDF. Removing.")
                    target_file_path.unlink(missing_ok=True)

            self.registry.mark_download_failed(pub_id)
            return None
        except Exception as e:
            logger.error(f"Download exception for {pub_id}: {e}")
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
