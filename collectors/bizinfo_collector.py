import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collectors.keywords import DEFAULT_KEYWORDS


class BizInfoCollector:
    """기업마당 지원사업 공고 웹 스크레이핑 수집기 (OpenAPI 인증키 불필요)"""

    BASE_URL = "https://www.bizinfo.go.kr"
    LIST_URL = f"{BASE_URL}/sii/siia/selectSIIA200View.do"
    DETAIL_URL = f"{BASE_URL}/sii/siia/selectSIIA200Detail.do"
    ATTACHMENT_EXTS = (".hwp", ".hwpx", ".pdf")

    # 1차 스크리닝 키워드
    DEFAULT_KEYWORDS = DEFAULT_KEYWORDS

    def __init__(self, download_dir: str = "./data/attachments", keywords: List[str] = None):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.keywords = keywords or self.DEFAULT_KEYWORDS
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def fetch_recent_notices(self, days: int = 7, max_pages: int = 30) -> List[Dict[str, Any]]:
        """기업마당 지원사업 공고 목록을 페이지별로 스크레이핑하여 최근 N일치 공고 수집"""
        results = []
        cutoff_date = datetime.now() - timedelta(days=days)

        for page in range(1, max_pages + 1):
            try:
                resp = self.session.get(self.LIST_URL, params={"cpage": page}, timeout=10)
                resp.encoding = "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("table tbody tr")
            except Exception as e:
                print(f"[Error] 기업마당 목록 조회 실패 (page {page}): {e}")
                break

            if not rows:
                break

            reached_cutoff = False
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 7:
                    continue

                link = cols[2].find("a")
                title = link.get_text(strip=True) if link else cols[2].get_text(strip=True)
                href = link["href"] if link else ""
                submission_period = cols[3].get_text(" ", strip=True)
                organization = cols[4].get_text(strip=True)
                pub_date_str = cols[6].get_text(strip=True)

                try:
                    pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
                except ValueError:
                    pub_date = None

                if pub_date and pub_date < cutoff_date:
                    reached_cutoff = True
                    break

                match = re.search(r"pblancId=([^&]+)", href)
                pblanc_id = match.group(1) if match else None
                if not pblanc_id:
                    continue

                matched_keywords = [kw for kw in self.keywords if kw.lower() in title.lower()]
                if not matched_keywords:
                    continue

                detail = self._fetch_detail(pblanc_id)

                results.append({
                    "source": "기업마당",
                    "organization": organization,
                    "title": title,
                    "url": f"{self.BASE_URL}{href}",
                    "pub_date": pub_date_str,
                    "summary_raw": detail.get("summary") or submission_period,
                    "matched_keywords": matched_keywords,
                    "attachment_paths": detail.get("attachment_paths", []),
                })

            if reached_cutoff:
                break

        return results

    def _fetch_detail(self, pblanc_id: str) -> Dict[str, Any]:
        """상세 페이지에서 사업개요와 첨부파일을 추출"""
        result = {"summary": "", "attachment_paths": []}
        try:
            time.sleep(0.2)
            resp = self.session.get(self.DETAIL_URL, params={"pblancId": pblanc_id}, timeout=10)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            for li in soup.select(".support_project_detail .view_cont li"):
                title_el = li.select_one(".s_title")
                txt_el = li.select_one(".txt")
                if title_el and txt_el and "사업개요" in title_el.get_text():
                    result["summary"] = txt_el.get_text(" ", strip=True)
                    break

            for li in soup.select(".attached_file_list li"):
                file_name_el = li.select_one(".file_name")
                download_a = li.select_one("a.icon_download")
                if not file_name_el or not download_a or not download_a.get("href"):
                    continue

                ext = os.path.splitext(file_name_el.get_text(strip=True))[-1].lower()
                if ext not in self.ATTACHMENT_EXTS:
                    continue

                file_url = self.BASE_URL + download_a["href"]
                saved_path = self._download_attachment(file_url, pblanc_id, len(result["attachment_paths"]), ext)
                if saved_path:
                    result["attachment_paths"].append(saved_path)
        except Exception as e:
            print(f"[Error] 상세페이지 조회 실패 ({pblanc_id}): {e}")

        return result

    def _download_attachment(self, url: str, pblanc_id: str, idx: int, ext: str) -> str:
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            file_path = os.path.join(self.download_dir, f"{pblanc_id}_{idx}{ext}")
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path
        except Exception as e:
            print(f"[Error] 첨부파일 다운로드 실패 ({url}): {e}")
            return ""
