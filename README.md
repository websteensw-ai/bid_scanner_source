# 테이커스 비전 기호 분석시스템

유튜브 방송의 자동자막(VTT)과 채팅 리플레이(live_chat JSON)를 분석합니다.

- 핵심어 빈도 (한국어 형태소 분석, Kiwi)
- 공출현 네트워크와 주제군, 매개 중심성 (NetworkX)
- 채팅 참여 유형 분류 (키워드 규칙)
- 분 단위 채팅량과 판매 발화의 상관

## 실행

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 데이터 주의

- 원본 자막·채팅 파일은 저장소에 올리지 않습니다 (`.gitignore` 참고).
- 채팅 작성자는 분석 시 익명 ID로 바뀝니다.
- 채팅 유형은 키워드 규칙으로 분류합니다. 연구에 쓰기 전에 표본을 수기 코딩해 정확도를 확인하세요.
- 저장소의 `tests/fixtures`는 가상의 예시 데이터입니다.
