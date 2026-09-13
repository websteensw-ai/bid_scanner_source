import os
import json
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

# main.py를 URL 없이 실행할 때 사용되는 기본 사업 프로필 (AX)
DEFAULT_BUSINESS_PROFILE = {
    "company_name": "AX",
    "business_summary": (
        "- AI 전환(AX) 컨설팅 및 교육: 기업의 AI 도입 진단, 조직 역량 강화 교육, AI 전환 전략 수립\n"
        "- AI 에이전트/AI 직원 플랫폼 구축: 생성형 AI·LLM/sLLM 기반 업무 자동화 에이전트, RAG, 사내 시스템 연동(커넥터), 온프레미스 AI 인프라\n"
        "- 산업 도메인 AX 실행: 제조·건설·반도체·공공 부문의 AI 도입/전환 실행 지원, 스마트공장·스마트제조 관련 AI·데이터 시스템 구축"
    ),
    "exclusion_criteria": (
        "- AI 응용 없이 순수 하드웨어/로봇 부품 설계·제작·성능시험 등 제조 R&D (당사는 로봇 하드웨어 제조사가 아님)\n"
        "- 단순 PC/서버/장비 구매, 상용 SW 라이선스 구매, 일반 홍보·디자인 용역\n"
        "- AI와 무관한 창업 지원, 입주 공간 모집, 전시회 참가 지원 등"
    ),
}


REPORT_FIELDS = [
    "competent_authority", "local_government", "application_period",
    "project_overview", "budget", "application_method", "contact", "bid_strategy",
]

NA = "확인필요"


class LLMEvaluator:
    """공고문 및 과업지시서 기반 심층 연관도 평가기"""

    def __init__(self, business_profile: Optional[Dict[str, str]] = None):
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"
        self.business_profile = business_profile or DEFAULT_BUSINESS_PROFILE

    def quick_filter(self, notices: List[Dict[str, Any]]) -> List[bool]:
        """제목/요약만으로 사업영역 무관 공고를 저비용으로 1차 컷. 첨부문서를 읽지 않아 빠르고 토큰이 적게 든다.
        모호하거나 오류 발생 시에는 통과(True)시켜 후보를 놓치지 않는다.
        """
        if not notices:
            return []
        business_summary = self.business_profile.get("business_summary", "")
        exclusion_criteria = self.business_profile.get("exclusion_criteria", "")

        items = "\n".join(
            f"{i}. {n.get('title', '')} - {(n.get('summary_raw') or '')[:120]}"
            for i, n in enumerate(notices)
        )
        prompt = f"""[사업 영역]
{business_summary}

[명백히 무관하여 제외할 대상]
{exclusion_criteria}

아래 공고 목록 중 [제외 대상]에 명백히 해당하거나 사업 영역과 전혀 무관한 것만 false로 표시하세요.
조금이라도 관련 가능성이 있으면 true로 두세요 (모호하면 true).

[공고 목록]
{items}

JSON으로만 응답: {{"r": [true/false, ...]}} (공고 목록과 같은 순서, 총 {len(notices)}개)
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                )
            )
            data = json.loads(response.text)
            flags = data.get("r", [])
            if len(flags) != len(notices):
                return [True] * len(notices)
            return [bool(f) for f in flags]
        except Exception as e:
            print(f"[Warn] 1차 스크리닝 실패, 전체 통과 처리: {e}")
            return [True] * len(notices)

    def evaluate(self, notice: Dict[str, Any], doc_content: str = "") -> Dict[str, Any]:
        company_name = self.business_profile.get("company_name", "당사")
        business_summary = self.business_profile.get("business_summary", "")
        exclusion_criteria = self.business_profile.get("exclusion_criteria", "")

        prompt = f"""공공기관/정부부처/지자체/산학협력단의 사업 공고입니다.
아래 [당사({company_name}) 사업 영역]을 기준으로 실제 수행·수주 가능한 과업인지 분석하세요.
단순 AI 키워드 언급만으로 관련도를 높게 주지 마세요.

[당사({company_name}) 사업 영역]
{business_summary}

[제외 대상 (관련도 낮음)]
{exclusion_criteria}

[공고 정보]
- 공고명: {notice.get('title')}
- 공고 요약: {notice.get('summary_raw')}
- 공고문/과업지시서 본문:
{doc_content[:4000] if doc_content else "세부 문서 없음"}

다음 JSON 형식으로만 응답하세요. 원문에 정보가 없으면 반드시 "{NA}"로 표기하세요:
{{
  "is_relevant": true/false (당사 사업 영역과 직접 관련 있어 실제 수주 검토 가치가 있으면 true),
  "relevance_score": 0~100 정수 (제외 대상/키워드만 언급은 30 이하, 사업 영역 직접 부합은 80 이상),
  "competent_authority": "소관부처 (중앙부처·공공기관·산학협력단명)",
  "local_government": "지자체 (해당 시/도/시군구, 없으면 {NA})",
  "application_period": "신청(접수)기간",
  "project_overview": "사업개요 1~2문장",
  "budget": "사업비 규모",
  "application_method": "신청방법 (예: 온라인 접수, 이메일 제출 등)",
  "contact": "문의처 (부서/전화/이메일)",
  "bid_strategy": "당사 강점과 연계한 수주전략 1~2문장"
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            data = json.loads(response.text)
            for field in REPORT_FIELDS:
                if not str(data.get(field) or "").strip():
                    data[field] = NA
            return data
        except Exception as e:
            print(f"[Error] LLM 평가 실패 ({notice.get('title')}): {e}")
            result = {"is_relevant": False, "relevance_score": 0}
            for field in REPORT_FIELDS:
                result[field] = NA
            return result
