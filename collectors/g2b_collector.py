import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
from urllib.parse import unquote
from collectors.keywords import DEFAULT_KEYWORDS


class G2BCollector:
    """나라장터(G2B) 용역 입찰공고 수집기 (data.go.kr Open API 서비스키 필요)

    공식 조달청 Open API를 사용합니다 (나라장터 자체는 WebSquare 기반 SPA라 스크레이핑 불가).
    .env의 G2B_SERVICE_KEY (data.go.kr 발급 서비스키)가 필요합니다.
    """

    LIST_API_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"
    ATTACHMENT_EXTS = (".hwp", ".hwpx", ".pdf")
    MAX_ROWS_PER_PAGE = 999

    DEFAULT_KEYWORDS = DEFAULT_KEYWORDS

    def __init__(self, download_dir: str = "./data/attachments", keywords: List[str] = None):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.keywords = keywords or self.DEFAULT_KEYWORDS
        # data.go.kr은 URL-encoding된 키(Encoding 키)를 제공하므로, 디코딩 후 requests가 다시 인코딩하게 함
        self.service_key = unquote(os.getenv("G2B_SERVICE_KEY", ""))
        self.session = requests.Session()
        # g2b.go.kr은 User-Agent 스니핑으로 비표준 클라이언트를 차단함
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        })

    def fetch_recent_notices(self, days: int = 7) -> List[Dict[str, Any]]:
        if not self.service_key or self.service_key == "your_data_go_kr_service_key_here":
            print("[Warn] G2B_SERVICE_KEY가 설정되지 않아 나라장터 수집을 건너뜁니다.")
            return []

        results = []
        end_dt = datetime.now()
        begin_dt = end_dt - timedelta(days=days)
        base_params = {
            "inqryDiv": "1",
            "type": "json",
            "inqryBgnDt": begin_dt.strftime("%Y%m%d0000"),
            "inqryEndDt": end_dt.strftime("%Y%m%d2359"),
            "numOfRows": self.MAX_ROWS_PER_PAGE,
            "ServiceKey": self.service_key,
        }

        page = 1
        while True:
            params = dict(base_params, pageNo=page)
            try:
                resp = self.session.get(self.LIST_API_URL, params=params, timeout=20)
                data = resp.json()
                body = data.get("response", {}).get("body")
                if body is None:
                    header = data.get("response", {}).get("header", {})
                    print(f"[Error] 나라장터 API 응답 오류: {header}")
                    break
                items = body.get("items") or []
            except Exception as e:
                print(f"[Error] 나라장터 목록 조회 실패 (page {page}): {e}")
                break

            if not items:
                break

            for item in items:
                title = item.get("bidNtceNm", "")
                matched_keywords = [kw for kw in self.keywords if kw.lower() in title.lower()]
                if not matched_keywords:
                    continue

                results.append({
                    "source": "나라장터",
                    "organization": item.get("ntceInsttNm") or item.get("dminsttNm"),
                    "title": title,
                    "url": item.get("bidNtceDtlUrl", ""),
                    "pub_date": (item.get("bidNtceDt") or "")[:10],
                    "summary_raw": (
                        f"입찰방식: {item.get('bidMethdNm', '')} / 계약방법: {item.get('cntrctCnclsMthdNm', '')} / "
                        f"입찰마감: {item.get('bidClseDt', '')} / 배정예산: {item.get('asignBdgtAmt', '')}원"
                    ),
                    "matched_keywords": matched_keywords,
                    "attachment_paths": self._download_attachments(item),
                })

            total_count = body.get("totalCount", 0)
            if page * self.MAX_ROWS_PER_PAGE >= total_count:
                break
            page += 1

        return results

    def _download_attachments(self, item: Dict[str, Any]) -> List[str]:
        paths = []
        bid_no = item.get("bidNtceNo", "unknown")
        for i in range(1, 11):
            doc_url = item.get(f"ntceSpecDocUrl{i}")
            file_name = item.get(f"ntceSpecFileNm{i}")
            if not doc_url or not file_name:
                continue

            ext = os.path.splitext(file_name)[-1].lower()
            if ext not in self.ATTACHMENT_EXTS:
                continue

            try:
                resp = self.session.get(doc_url, timeout=20)
                resp.raise_for_status()
                file_path = os.path.join(self.download_dir, f"G2B_{bid_no}_{i}{ext}")
                with open(file_path, "wb") as f:
                    f.write(resp.content)
                paths.append(file_path)
            except Exception as e:
                print(f"[Error] 나라장터 첨부파일 다운로드 실패 ({bid_no}): {e}")

        return paths
