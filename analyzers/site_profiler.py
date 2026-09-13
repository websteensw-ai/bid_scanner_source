import json
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
from google import genai
from google.genai import types


class SiteProfiler:
    """회사 웹사이트를 분석하여 사업 영역 요약, 제외 기준, 1차 스크리닝 키워드를 생성"""

    def __init__(self):
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        })

    def _fetch_site_text(self, url: str, max_chars: int = 8000) -> str:
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return text[:max_chars]

    def analyze(self, url: str) -> Dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        site_text = self._fetch_site_text(url)
        if not site_text:
            raise ValueError("사이트에서 텍스트를 추출하지 못했습니다.")

        prompt = f"""
다음은 한 회사의 웹사이트에서 추출한 텍스트입니다. 이 회사가 공공/정부 입찰공고 중 어떤 것을 수주 대상으로 삼아야 하는지 분석하는 데 쓸 자료를 만들어주세요.

[웹사이트 URL]
{url}

[웹사이트 텍스트]
{site_text}

[출력 요구사항]
반드시 다음 JSON 형식으로만 응답하세요:
{{
  "company_name": "회사명 (텍스트에서 추정)",
  "business_summary": "이 회사가 실제로 사업으로 삼는 영역을 3~5개의 불릿 포인트로 요약 (각 줄은 '- '로 시작, 줄바꿈으로 구분). 공공 입찰공고와 매칭할 때 '우리가 이걸 실제로 수행할 수 있는가'를 판단하는 기준이 되어야 함.",
  "exclusion_criteria": "이 회사의 사업 영역과 무관하거나 수행할 수 없는 유형을 2~4개의 불릿 포인트로 요약 (각 줄은 '- '로 시작, 줄바꿈으로 구분)",
  "keywords": ["1차 스크리닝에 쓸 한국어/영어 키워드 15~25개. 회사의 실제 사업/기술/산업 도메인과 관련된 단어. 공고 제목에 포함될 법한 구체적인 단어 위주로 선정"]
}}
"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        profile = json.loads(response.text)
        profile["source_url"] = url
        return profile
