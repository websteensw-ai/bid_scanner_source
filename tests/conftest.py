# 앱 진입점(web.main)을 먼저 불러 둔다. web.mvp·web.accounts 는 web.main 의 헬퍼를 쓰고,
# web.main 이 끝에서 두 라우터를 등록하므로 진입점부터 불러야 순환 참조가 풀린다.
import os

os.environ.setdefault("MVP_PACK", "SAMPLE-Q1")   # 엔진 테스트는 고정 샘플 (실제 문제: test_real_pack)

import web.main  # noqa: E402,F401
