import os
import tempfile
import threading
import uuid
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, abort, session
from dotenv import load_dotenv

load_dotenv()

from pipeline import run_pipeline, SOURCE_REGISTRY
from analyzers.site_profiler import SiteProfiler
from analyzers.industry_presets import INDUSTRY_PRESETS
from exporters.excel_exporter import ExcelExporter
from auth import (
    login_required, request_otp, verify_email_otp, build_signup_metadata,
    set_session, update_company_url, update_telegram_chat_id,
)
import reports_store
import telegram_bot

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

# 서비스 정식 오픈 전, 로그인 없이 바로 체험할 수 있게 하는 임시 우회 버튼.
# 실제 서비스 활성화 시 이 플래그를 false로 바꾸면 버튼과 라우트가 함께 비활성화된다.
TEST_LOGIN_ENABLED = os.environ.get("TEST_LOGIN_ENABLED", "true").lower() == "true"

# 알림 메시지에 넣을 결과 링크의 기준 주소. 배포 후에는 실제 도메인으로 바꿔야 한다.
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")

JOBS = {}
JOBS_LOCK = threading.Lock()

def _on_telegram_linked(user_id: str, access_token: str, refresh_token: str, chat_id: str) -> None:
    update_telegram_chat_id(access_token, refresh_token, chat_id)


telegram_bot.set_link_callback(_on_telegram_linked)
telegram_bot.start_polling()


@app.context_processor
def inject_user():
    return {
        "current_user_email": session.get("email"),
        "current_company_name": session.get("company_name"),
        "test_login_enabled": TEST_LOGIN_ENABLED,
        "telegram_configured": telegram_bot.is_configured(),
        "telegram_connected": bool(session.get("telegram_chat_id")),
    }

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _set_job(job_id, **kwargs):
    with JOBS_LOCK:
        JOBS[job_id].update(kwargs)


def _resolve_profile(mode: str, params: dict) -> dict:
    """입력 모드(url/industry/keywords)에 따라 keywords + business_profile을 만든다."""
    if mode == "industry":
        preset = INDUSTRY_PRESETS[params["industry"]]
        return {
            "label": f"[업종] {preset['label']}",
            "keywords": preset["keywords"],
            "business_profile": {
                "company_name": preset["company_name"],
                "business_summary": preset["business_summary"],
                "exclusion_criteria": preset["exclusion_criteria"],
            },
            "profile_view": preset,
        }

    if mode == "keywords":
        kw_list = params["keywords"]
        business_profile = {
            "company_name": "직접 입력한 키워드",
            "business_summary": "- 사용자가 직접 입력한 다음 키워드와 관련된 사업을 찾는다: " + ", ".join(kw_list),
            "exclusion_criteria": "- 위 키워드와 의미상 명백히 무관한 내용",
        }
        return {
            "label": f"[키워드] {', '.join(kw_list)}",
            "keywords": kw_list,
            "business_profile": business_profile,
            "profile_view": {**business_profile, "keywords": kw_list},
        }

    # mode == "url"
    profile = SiteProfiler().analyze(params["url"])
    business_profile = {
        "company_name": profile.get("company_name", "당사"),
        "business_summary": profile.get("business_summary", ""),
        "exclusion_criteria": profile.get("exclusion_criteria", ""),
    }
    return {
        "label": params["url"],
        "keywords": profile.get("keywords") or None,
        "business_profile": business_profile,
        "profile_view": profile,
    }


def _run_job(
    job_id: str, mode: str, params: dict, days: int, min_score: int, sources: list,
    user_id: str, access_token: str, telegram_chat_id: str = "",
):
    try:
        _set_job(job_id, status="running", stage="사업 영역 파악 중", current=0, total=1)
        resolved = _resolve_profile(mode, params)
        _set_job(job_id, profile=resolved["profile_view"], label=resolved["label"])

        def progress_cb(stage, current, total):
            _set_job(job_id, stage=stage, current=current, total=total)

        results = run_pipeline(
            days=days,
            min_score=min_score,
            keywords=resolved["keywords"],
            business_profile=resolved["business_profile"],
            sources=sources,
            progress_cb=progress_cb,
        )

        _set_job(job_id, stage="리포트 생성 중")
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}.xlsx")
        ExcelExporter.export(results, output_file)

        try:
            reports_store.save_report(
                access_token=access_token,
                user_id=user_id,
                url=resolved["label"],
                days=days,
                min_score=min_score,
                business_profile=resolved["business_profile"],
                results=results,
            )
        except Exception as e:
            print(f"[Warn] Supabase 리포트 저장 실패: {e}")

        _set_job(job_id, status="done", stage="완료", results=results, output_file=output_file)

        if telegram_chat_id:
            job_url = f"{BASE_URL}/jobs/{job_id}"
            telegram_bot.send_message(
                telegram_chat_id,
                f"✅ 분석 완료: {resolved['label']}\n매칭된 공고 {len(results)}건\n결과 보기: {job_url}",
            )
    except Exception as e:
        _set_job(job_id, status="error", stage="오류", error=str(e))
        if telegram_chat_id:
            telegram_bot.send_message(telegram_chat_id, f"⚠️ 분석 중 오류가 발생했습니다: {e}")


@app.route("/")
def index():
    if session.get("user_id"):
        return render_template(
            "index.html",
            company_url=session.get("company_url", ""),
            welcome=request.args.get("welcome") == "1",
            industries=INDUSTRY_PRESETS,
            sources=SOURCE_REGISTRY,
        )
    return render_template("landing.html")


@app.route("/test-login")
def test_login():
    """로그인 없이 분석 화면으로 바로 이동하는 임시 체험용 라우트. TEST_LOGIN_ENABLED=false로 비활성화 가능."""
    if not TEST_LOGIN_ENABLED:
        abort(404)
    session["user_id"] = "test-user"
    session["access_token"] = "test-token"
    session["refresh_token"] = "test-token"
    session["email"] = "test@example.com"
    session["company_name"] = "테스트 계정"
    session.setdefault("company_url", "")
    return redirect(url_for("index"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", form={})

    form = request.form
    email = form.get("email", "").strip()
    company_url = form.get("company_url", "").strip()
    company_name = form.get("company_name", "").strip()
    contact_name = form.get("contact_name", "").strip()
    contact_phone = form.get("contact_phone", "").strip()
    agree_service = form.get("agree_service") == "on"
    agree_privacy = form.get("agree_privacy") == "on"
    agree_marketing = form.get("agree_marketing") == "on"

    if not all([email, company_url, company_name, contact_name, contact_phone]):
        return render_template("signup.html", form=form, error="필수 항목을 모두 입력해주세요.")
    if not (agree_service and agree_privacy):
        return render_template(
            "signup.html", form=form,
            error="AI 서비스 이용약관과 개인정보 수집·이용 동의는 필수입니다.",
        )

    metadata = build_signup_metadata(
        company_url=company_url,
        company_name=company_name,
        contact_name=contact_name,
        contact_phone=contact_phone,
        agree_service=agree_service,
        agree_privacy=agree_privacy,
        agree_marketing=agree_marketing,
    )

    try:
        request_otp(email, signup_metadata=metadata)
    except Exception as e:
        return render_template("signup.html", form=form, error=f"인증코드 발송 실패: {e}")

    session["otp_pending_email"] = email
    session["otp_mode"] = "signup"
    session["otp_signup_metadata"] = metadata
    return redirect(url_for("verify_otp_page"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    if not email:
        return render_template("login.html", error="이메일을 입력해주세요.")

    try:
        request_otp(email, signup_metadata=None)
    except Exception as e:
        return render_template("login.html", error=f"인증코드 발송 실패: {e}")

    session["otp_pending_email"] = email
    session["otp_mode"] = "login"
    session["otp_next"] = request.args.get("next") or ""
    return redirect(url_for("verify_otp_page"))


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_page():
    email = session.get("otp_pending_email")
    if not email:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("verify_otp.html", email=email)

    code = request.form.get("code", "").strip()
    try:
        res = verify_email_otp(email, code)
    except Exception:
        return render_template("verify_otp.html", email=email, error="인증코드가 올바르지 않거나 만료되었습니다.")

    set_session(res.session, res.user)
    mode = session.pop("otp_mode", "login")
    next_url = session.pop("otp_next", "") or None
    session.pop("otp_pending_email", None)
    session.pop("otp_signup_metadata", None)

    if next_url:
        return redirect(next_url)
    return redirect(url_for("index", welcome="1" if mode == "signup" else "0"))


@app.route("/otp/resend", methods=["POST"])
def resend_otp():
    email = session.get("otp_pending_email")
    if not email:
        return redirect(url_for("login"))
    try:
        request_otp(email, signup_metadata=session.get("otp_signup_metadata"))
        return render_template("verify_otp.html", email=email, info="인증코드를 다시 보냈습니다.")
    except Exception as e:
        return render_template("verify_otp.html", email=email, error=f"재발송 실패: {e}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/telegram/connect")
@login_required
def telegram_connect():
    if not telegram_bot.is_configured():
        abort(404)
    if session.get("telegram_chat_id"):
        return redirect(url_for("index"))

    code = telegram_bot.create_link_code(session["user_id"], session["access_token"], session["refresh_token"])
    return render_template("telegram_connect.html", connect_url=telegram_bot.get_connect_url(code))


@app.route("/telegram/disconnect", methods=["POST"])
@login_required
def telegram_disconnect():
    try:
        update_telegram_chat_id(session["access_token"], session["refresh_token"], "")
    except Exception as e:
        print(f"[Warn] 텔레그램 연결 해제 실패: {e}")
    session["telegram_chat_id"] = ""
    return redirect(url_for("index"))


@app.route("/api/telegram/status")
@login_required
def telegram_status():
    chat_id = telegram_bot.check_and_consume_link(session["user_id"])
    if chat_id:
        session["telegram_chat_id"] = chat_id
    return jsonify({"connected": bool(session.get("telegram_chat_id"))})


@app.route("/reports")
@login_required
def my_reports():
    try:
        rows = reports_store.list_reports(session["access_token"])
    except Exception as e:
        return render_template("reports.html", rows=[], error=f"리포트 목록 조회 실패: {e}")
    return render_template("reports.html", rows=rows)


@app.route("/reports/<report_id>/download")
@login_required
def download_report(report_id):
    row = reports_store.get_report(session["access_token"], report_id)
    if not row:
        abort(404)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    ExcelExporter.export(row.get("results") or [], tmp_path)
    return send_file(tmp_path, as_attachment=True, download_name=f"Bid_Report_{report_id}.xlsx")


def _render_index_error(error: str):
    return render_template(
        "index.html",
        company_url=session.get("company_url", ""),
        industries=INDUSTRY_PRESETS,
        sources=SOURCE_REGISTRY,
        error=error,
    )


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    mode = request.form.get("mode", "url")
    days = int(request.form.get("days") or 7)
    min_score = int(request.form.get("min_score") or 70)
    selected_sources = [key for key in request.form.getlist("sources") if key in SOURCE_REGISTRY]

    if mode == "industry":
        industry_key = request.form.get("industry", "").strip()
        if industry_key not in INDUSTRY_PRESETS:
            return _render_index_error("업종을 선택해주세요.")
        params = {"industry": industry_key}

    elif mode == "keywords":
        raw = request.form.get("keywords", "").strip()
        kw_list = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        if not kw_list:
            return _render_index_error("키워드를 1개 이상 입력해주세요.")
        params = {"keywords": kw_list}

    else:
        mode = "url"
        url = request.form.get("url", "").strip()
        if not url:
            return _render_index_error("사이트 주소를 입력해주세요.")
        params = {"url": url}

        if url != session.get("company_url"):
            session["company_url"] = url
            try:
                update_company_url(session["access_token"], session["refresh_token"], url)
            except Exception as e:
                print(f"[Warn] 기본 홈페이지 주소 저장 실패: {e}")

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "stage": "대기 중",
            "current": 0,
            "total": 0,
            "label": params.get("url") or "",
            "days": days,
            "min_score": min_score,
            "created_at": datetime.now().isoformat(),
        }

    threading.Thread(
        target=_run_job,
        args=(
            job_id, mode, params, days, min_score, selected_sources,
            session["user_id"], session["access_token"], session.get("telegram_chat_id", ""),
        ),
        daemon=True,
    ).start()
    return redirect(url_for("job_page", job_id=job_id))


@app.route("/jobs/<job_id>")
@login_required
def job_page(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    return render_template("job.html", job_id=job_id, job=job)


@app.route("/api/jobs/<job_id>")
@login_required
def job_status(job_id):
    with JOBS_LOCK:
        job = dict(JOBS.get(job_id) or {})
    if not job:
        return jsonify({"error": "not found"}), 404

    payload = {
        "status": job.get("status"),
        "stage": job.get("stage"),
        "current": job.get("current", 0),
        "total": job.get("total", 0),
        "label": job.get("label"),
    }
    if job.get("status") == "done":
        payload["results"] = job.get("results", [])
        payload["profile"] = job.get("profile", {})
    if job.get("status") == "error":
        payload["error"] = job.get("error")
    return jsonify(payload)


@app.route("/jobs/<job_id>/download")
@login_required
def job_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job.get("status") != "done" or not os.path.exists(job.get("output_file", "")):
        abort(404)
    return send_file(job["output_file"], as_attachment=True, download_name=f"Bid_Report_{job_id}.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
