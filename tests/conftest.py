# 앱 진입점(web.main)을 먼저 불러 둔다. web.mvp·web.accounts 는 web.main 의 헬퍼를 쓰고,
# web.main 이 끝에서 두 라우터를 등록하므로 진입점부터 불러야 순환 참조가 풀린다.
import web.main  # noqa: F401
