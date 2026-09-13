import os
import re
import tempfile
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collectors.keywords import DEFAULT_KEYWORDS


class KStartupCollector:
    """K-Startup(창업지원포털) 사업공고 수집기 (인증키 불필요)"""

    BASE_URL = "https://www.k-startup.go.kr"
    LIST_URL = f"{BASE_URL}/web/contents/bizpbanc-ongoing.do"
    ATTACHMENT_EXTS = (".hwp", ".hwpx", ".pdf")

    # 1차 스크리닝 키워드
    DEFAULT_KEYWORDS = DEFAULT_KEYWORDS

    def __init__(self, download_dir: str = None, keywords: List[str] = None):
        download_dir = download_dir or os.path.join(tempfile.gettempdir(), "bid_scanner_attachments")
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.keywords = keywords or self.DEFAULT_KEYWORDS
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def fetch_recent_notices(self, days: int = 7, max_pages: int = 30) -> List[Dict[str, Any]]:
        """K-Startup 사업공고(모집중) 목록을 페이지별로 스크레이핑하여 최근 N일치 공고 수집"""
        results = []
        cutoff_date = datetime.now() - timedelta(days=days)

        for page in range(1, max_pages + 1):
            try:
                resp = self.session.get(self.LIST_URL, params={"schM": "list", "page": page}, timeout=15)
                resp.encoding = "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("#bizPbancList li.notice")
            except Exception as e:
                print(f"[Error] K-Startup 목록 조회 실패 (page {page}): {e}")
                break

            if not items:
                break

            reached_cutoff = False
            for li in items:
                link_el = li.select_one(".middle a")
                href = link_el.get("href", "") if link_el else ""
                match = re.search(r"go_view\((\d+)\)", href)
                pbanc_sn = match.group(1) if match else None
                if not pbanc_sn:
                    continue

                tit_el = li.select_one(".middle .tit_wrap .tit")
                if tit_el:
                    new_flag = tit_el.select_one(".new")
                    if new_flag:
                        new_flag.extract()
                    title = tit_el.get_text(strip=True)
                else:
                    title = ""

                bottom_text = li.select_one(".bottom").get_text("|", strip=True) if li.select_one(".bottom") else ""
                bottom_parts = [p for p in bottom_text.split("|") if p]
                organization = bottom_parts[1] if len(bottom_parts) > 1 else ""

                reg_match = re.search(r"등록일자\s*(\d{4}-\d{2}-\d{2})", bottom_text)
                pub_date_str = reg_match.group(1) if reg_match else ""
                start_match = re.search(r"시작일자\s*(\d{4}-\d{2}-\d{2})", bottom_text)
                end_match = re.search(r"마감일자\s*(\d{4}-\d{2}-\d{2})", bottom_text)
                submission_period = f"{start_match.group(1) if start_match else ''} ~ {end_match.group(1) if end_match else ''}"

                try:
                    pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
                except ValueError:
                    pub_date = None

                if pub_date and pub_date < cutoff_date:
                    reached_cutoff = True
                    break

                matched_keywords = [kw for kw in self.keywords if kw.lower() in title.lower()]
                if not matched_keywords:
                    continue

                detail = self._fetch_detail(pbanc_sn)

                results.append({
                    "source": "K-Startup",
                    "organization": organization,
                    "title": title,
                    "url": f"{self.LIST_URL}?schM=view&pbancSn={pbanc_sn}",
                    "pub_date": pub_date_str,
                    "summary_raw": detail.get("summary") or submission_period,
                    "matched_keywords": matched_keywords,
                    "attachment_paths": detail.get("attachment_paths", []),
                })

            if reached_cutoff:
                break

        return results

    def _fetch_detail(self, pbanc_sn: str) -> Dict[str, Any]:
        """상세 페이지에서 사업개요, 신청대상과 첨부파일을 추출"""
        result = {"summary": "", "attachment_paths": []}
        try:
            time.sleep(0.2)
            resp = self.session.get(self.LIST_URL, params={"schM": "view", "pbancSn": pbanc_sn}, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            summary_parts = []
            overview_el = soup.select_one(".box .box_inner .txt")
            if overview_el:
                summary_parts.append(overview_el.get_text(" ", strip=True))
            for txt_el in soup.select(".information_list-wrap .dot_list .txt"):
                summary_parts.append(txt_el.get_text(" ", strip=True))
            result["summary"] = " ".join(summary_parts)[:2000]

            for li_file in soup.select(".board_file li.clear"):
                file_bg = li_file.select_one("a.file_bg")
                download_a = li_file.select_one("a.btn_down[href]")
                if not file_bg or not download_a:
                    continue

                file_name = file_bg.get("title") or file_bg.get_text(strip=True)
                ext = os.path.splitext(file_name)[-1].lower()
                if ext not in self.ATTACHMENT_EXTS:
                    continue

                file_url = self.BASE_URL + download_a["href"]
                saved_path = self._download_attachment(file_url, pbanc_sn, len(result["attachment_paths"]), ext)
                if saved_path:
                    result["attachment_paths"].append(saved_path)
        except Exception as e:
            print(f"[Error] K-Startup 상세페이지 조회 실패 ({pbanc_sn}): {e}")

        return result

    def _download_attachment(self, url: str, pbanc_sn: str, idx: int, ext: str) -> str:
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            file_path = os.path.join(self.download_dir, f"KSTARTUP_{pbanc_sn}_{idx}{ext}")
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path
        except Exception as e:
            print(f"[Error] K-Startup 첨부파일 다운로드 실패 ({url}): {e}")
            return ""
