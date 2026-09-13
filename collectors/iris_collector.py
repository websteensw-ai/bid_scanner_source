import os
import re
import tempfile
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collectors.keywords import DEFAULT_KEYWORDS


class IrisCollector:
    """범부처통합연구지원시스템(IRIS) 사업공고 수집기 (인증키 불필요)"""

    BASE_URL = "https://www.iris.go.kr"
    LIST_VIEW_URL = f"{BASE_URL}/contents/retrieveBsnsAncmBtinSituListView.do"
    LIST_API_URL = f"{BASE_URL}/contents/retrieveBsnsAncmBtinSituList.do"
    DETAIL_URL = f"{BASE_URL}/contents/retrieveBsnsAncmView.do"
    FILE_DOWNLOAD_URL = f"{BASE_URL}/comm/file/fileDownload.do"
    ATTACHMENT_EXTS = (".hwp", ".hwpx", ".pdf")
    ONCLICK_PATTERN = re.compile(
        r"f_bsnsAncm_downloadAtchFile\('([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\)"
    )

    # 1차 스크리닝 키워드
    DEFAULT_KEYWORDS = DEFAULT_KEYWORDS

    # 공고 진행상태: 접수예정 + 접수중 (등록일 기준으로 최근 공고를 찾기 위해 둘 다 조회)
    ANCM_PRG_TYPES = ("ancmPre", "ancmIng")

    def __init__(self, download_dir: str = None, keywords: List[str] = None):
        download_dir = download_dir or os.path.join(tempfile.gettempdir(), "bid_scanner_attachments")
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.keywords = keywords or self.DEFAULT_KEYWORDS
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def fetch_recent_notices(self, days: int = 7, max_pages: int = 30) -> List[Dict[str, Any]]:
        """IRIS 사업공고 목록을 상태별로 조회하여 최근 N일치 공고 수집"""
        results = []
        seen_ids = set()
        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            self.session.get(self.LIST_VIEW_URL, timeout=15)
        except Exception as e:
            print(f"[Warn] IRIS 세션 초기화 실패: {e}")

        for ancm_prg in self.ANCM_PRG_TYPES:
            page = 1
            while page <= max_pages:
                try:
                    resp = self.session.post(
                        self.LIST_API_URL,
                        data={"pageIndex": page, "pageUnit": 20, "bsnsTl": "", "ancmPrg": ancm_prg},
                        headers={"X-Requested-With": "XMLHttpRequest"},
                        timeout=20,
                    )
                    data = resp.json()
                    items = data.get("listBsnsAncmBtinSitu", [])
                except Exception as e:
                    print(f"[Error] IRIS 목록 조회 실패 ({ancm_prg}, page {page}): {e}")
                    break

                if not items:
                    break

                reached_cutoff = False
                for item in items:
                    ancm_id = item.get("ancmId")
                    ancm_de = item.get("ancmDe")

                    try:
                        pub_date = datetime.strptime(ancm_de, "%Y-%m-%d")
                    except (TypeError, ValueError):
                        pub_date = None

                    if pub_date and pub_date < cutoff_date:
                        reached_cutoff = True
                        break

                    if not ancm_id or ancm_id in seen_ids:
                        continue

                    title = item.get("ancmTl", "")
                    matched_keywords = [kw for kw in self.keywords if kw.lower() in title.lower()]
                    if not matched_keywords:
                        continue

                    seen_ids.add(ancm_id)
                    detail = self._fetch_detail(ancm_id, ancm_prg)

                    results.append({
                        "source": "IRIS",
                        "organization": item.get("blngGovdSeNm") or item.get("sorgnNm"),
                        "title": title,
                        "url": f"{self.DETAIL_URL}?ancmId={ancm_id}&ancmPrg={ancm_prg}",
                        "pub_date": ancm_de,
                        "summary_raw": detail.get("summary") or f"접수기간 {item.get('rcveStrDe', '')} ~ {item.get('rcveEndDe', '')}",
                        "matched_keywords": matched_keywords,
                        "attachment_paths": detail.get("attachment_paths", []),
                    })

                if reached_cutoff:
                    break

                total_pages = data.get("paginationInfo", {}).get("totalPageCount", page)
                if page >= total_pages:
                    break
                page += 1

        return results

    def _fetch_detail(self, ancm_id: str, ancm_prg: str) -> Dict[str, Any]:
        """상세 페이지에서 공고 본문과 첨부파일을 추출"""
        result = {"summary": "", "attachment_paths": []}
        try:
            time.sleep(0.2)
            resp = self.session.get(self.DETAIL_URL, params={"ancmId": ancm_id, "ancmPrg": ancm_prg}, timeout=10)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            content_el = soup.select_one(".tb_contents .se-contents")
            if content_el:
                result["summary"] = content_el.get_text(" ", strip=True)[:2000]

            for a in soup.select(".add_file_list a.file_down"):
                match = self.ONCLICK_PATTERN.search(a.get("href", ""))
                if not match:
                    continue
                atch_doc_id, atch_file_id, file_name, _file_size = match.groups()

                ext = os.path.splitext(file_name)[-1].lower()
                if ext not in self.ATTACHMENT_EXTS:
                    continue

                saved_path = self._download_attachment(atch_doc_id, atch_file_id, ancm_id, len(result["attachment_paths"]), ext)
                if saved_path:
                    result["attachment_paths"].append(saved_path)
        except Exception as e:
            print(f"[Error] IRIS 상세페이지 조회 실패 ({ancm_id}): {e}")

        return result

    def _download_attachment(self, atch_doc_id: str, atch_file_id: str, ancm_id: str, idx: int, ext: str) -> str:
        try:
            resp = self.session.get(
                self.FILE_DOWNLOAD_URL,
                params={"atchDocId": atch_doc_id, "atchFileId": atch_file_id},
                timeout=20,
            )
            resp.raise_for_status()
            file_path = os.path.join(self.download_dir, f"IRIS_{ancm_id}_{idx}{ext}")
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path
        except Exception as e:
            print(f"[Error] IRIS 첨부파일 다운로드 실패 ({ancm_id}): {e}")
            return ""
