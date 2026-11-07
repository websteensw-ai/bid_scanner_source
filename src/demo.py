"""테스트 모드용 저장된 분석 결과 불러오기 (토큰·외부 호출 없음)."""
import json
import pathlib

DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "demo_result.json"


def load_demo() -> dict:
    with open(DEMO_PATH, encoding="utf-8") as f:
        return json.load(f)
