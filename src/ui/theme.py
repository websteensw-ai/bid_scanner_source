"""디자인 시스템: 색·글꼴·간격·모서리·그림자 토큰과 전역 CSS.

모든 화면은 app.py 에서 apply_theme() 를 한 번 호출해 같은 스타일을 공유합니다.
색을 바꾸려면 TOKENS 만 수정하세요 (.streamlit/config.toml 의 primaryColor 등도 함께).
"""
import streamlit as st

TOKENS = {
    # 브랜드 (신뢰감 있는 네이비 → 블루)
    "navy-900": "#0F1C3F",
    "navy-800": "#14254F",
    "primary": "#2B50D6",
    "primary-hover": "#2343B8",
    "primary-50": "#EEF2FE",
    "primary-100": "#DCE4FD",
    # 표면 (눈이 편한 저채도 쿨그레이)
    "bg": "#F6F7FB",
    "surface": "#FFFFFF",
    "surface-muted": "#F9FAFC",
    "border": "#E3E7F0",
    "border-strong": "#CDD3E1",
    # 텍스트
    "text": "#1B2233",
    "text-secondary": "#4A5468",
    "text-muted": "#7A8499",
    # 상태
    "success": "#0F9D74",
    "success-50": "#E7F6F1",
    "warning": "#C98112",
    "warning-50": "#FDF4E3",
    "danger": "#D64545",
    "danger-50": "#FCECEC",
    # 모양
    "radius-sm": "8px",
    "radius": "12px",
    "radius-lg": "18px",
    "shadow-sm": "0 1px 2px rgba(16,28,63,.04), 0 1px 3px rgba(16,28,63,.06)",
    "shadow": "0 2px 4px rgba(16,28,63,.04), 0 8px 24px rgba(16,28,63,.06)",
    "shadow-lg": "0 12px 40px rgba(16,28,63,.10)",
}

# Pretendard(SIL OFL)를 static/fonts 에 자체 호스팅 → 외부 CDN 차단 환경에서도 동일한 글꼴
_FONT_URL = "app/static/fonts/PretendardVariable.woff2"

_VARS = "\n".join(f"  --{k}: {v};" for k, v in TOKENS.items())

_CSS = """
<style>
@font-face {
  font-family: 'Pretendard Variable';
  font-weight: 45 920;
  font-style: normal;
  font-display: swap;
  src: url("__FONT__") format("woff2-variations"), url("__FONT__") format("woff2");
}
:root {
__VARS__
  --font: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont,
          'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
  --font-reading: 'Pretendard Variable', Pretendard, 'Noto Serif KR', serif;
}

/* ---------- 기본 타이포그래피 ---------- */
html, body, .stApp, .stMarkdown, button, input, textarea, select {
  font-family: var(--font) !important;
  -webkit-font-smoothing: antialiased;
  letter-spacing: -0.01em;
}
.stApp { background: var(--bg); color: var(--text); }
.stMarkdown p, .stMarkdown li { line-height: 1.7; color: var(--text-secondary); }
h1, h2, h3, h4 { color: var(--navy-900) !important; letter-spacing: -0.025em; }

/* 본문 폭 제한 + 여백 (읽기 편한 너비) */
.stMainBlockContainer, [data-testid="stMainBlockContainer"] {
  max-width: 1120px;
  padding: 2.5rem 2rem 5rem;
}
header[data-testid="stHeader"] { background: transparent; }

/* ---------- 사이드바 ---------- */
section[data-testid="stSidebar"] {
  border-right: 1px solid var(--border);
}
[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavLink"] {
  border-radius: var(--radius-sm);
  margin: 2px 0;
  padding: .45rem .7rem;
  transition: background .15s ease;
}
[data-testid="stSidebarNavLink"] span { font-weight: 500; color: var(--text-secondary); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--primary-50); }
[data-testid="stSidebarNavLink"][aria-current="page"] span {
  color: var(--primary); font-weight: 700;
}
[data-testid="stSidebarNavSeparator"] { border-color: var(--border); }
[data-testid="stLogo"] { height: 2.1rem; max-width: 100%; }

/* ---------- 버튼 ---------- */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
  border-radius: 10px;
  font-weight: 600;
  min-height: 2.75rem;
  padding: .55rem 1.15rem;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-sm);
  transition: transform .12s ease, box-shadow .15s ease, background .15s ease,
              border-color .15s ease;
}
.stButton button:hover, .stFormSubmitButton button:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow);
  transform: translateY(-1px);
  color: var(--text);
}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(180deg, #3159E4 0%, var(--primary) 100%);
  border: 1px solid var(--primary-hover);
  color: #fff !important;
  box-shadow: 0 1px 2px rgba(43,80,214,.25), 0 4px 12px rgba(43,80,214,.22);
}
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--primary-hover);
  box-shadow: 0 2px 4px rgba(43,80,214,.25), 0 8px 20px rgba(43,80,214,.28);
}
.stButton button:focus-visible, .stFormSubmitButton button:focus-visible {
  outline: 3px solid var(--primary-100); outline-offset: 2px;
}

/* ---------- 입력창 ---------- */
[data-testid="stSelectbox"] div:has(> [role="combobox"]) {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  min-height: 2.9rem;
  box-shadow: var(--shadow-sm);
}
[data-testid="stSelectbox"] div:has(> [role="combobox"]):focus-within {
  border-color: var(--primary) !important; box-shadow: 0 0 0 4px var(--primary-50) !important;
}
[data-testid="stSelectbox"] [role="combobox"] { font-weight: 600; color: var(--text); }
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="select"] > div {
  border-radius: 10px !important;
  background: var(--surface) !important;
}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  border-radius: 10px !important;
  border-color: var(--border) !important;
  background: var(--surface) !important;
  transition: border-color .15s ease, box-shadow .15s ease;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 4px var(--primary-50) !important;
}
.stTextInput label p, .stTextArea label p, .stSelectbox label p, .stNumberInput label p {
  font-weight: 600; color: var(--text); font-size: .92rem;
}

/* 답안 에디터: 원고지처럼 읽기 편한 본문 스타일 */
.st-key-editor textarea {
  font-family: var(--font-reading) !important;
  font-size: 1.06rem !important;
  line-height: 1.95 !important;
  color: var(--text) !important;
  padding: 1.25rem 1.4rem !important;
  min-height: 460px;
}

/* ---------- 카드 (components.card) ---------- */
div[class*="st-key-card"] {
  background: var(--surface);
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-sm);
}
div[class*="st-key-card"] { padding: 1.4rem 1.5rem; }
div[class*="st-key-card"]:hover { box-shadow: var(--shadow); }

/* ---------- 탭 (react-aria 기반: role=tablist / data-testid=stTab) ---------- */
.stTabs [role="tablist"] {
  gap: .25rem; background: var(--surface-muted); padding: .3rem;
  border-radius: 12px; border: 1px solid var(--border); width: fit-content;
  box-shadow: none !important;
}
.stTabs [role="tablist"]::after, .stTabs [role="tablist"]::before { display: none !important; }
.stTabs .react-aria-SelectionIndicator { display: none !important; }
.stTabs [data-testid="stTab"] {
  height: 2.35rem; padding: 0 1.05rem; border-radius: 9px !important; font-weight: 600;
  color: var(--text-muted); border: 0 !important; box-shadow: none !important;
  display: flex; align-items: center; justify-content: center; transition: background .15s ease;
}
.stTabs [data-testid="stTab"] p { font-weight: 600; font-size: .93rem; }
.stTabs [data-testid="stTab"][aria-selected="true"] {
  background: var(--surface); color: var(--primary); box-shadow: var(--shadow-sm) !important;
}
.stTabs [data-testid="stTab"][aria-selected="true"] p { color: var(--primary); }

/* ---------- Expander / Alert / Metric ---------- */
[data-testid="stExpander"] details {
  background: var(--surface); border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important; box-shadow: var(--shadow-sm);
}
[data-testid="stExpander"] summary { padding: .9rem 1.1rem; font-weight: 600; }
[data-testid="stAlert"] { border-radius: var(--radius); }
[data-testid="stMetric"] {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1rem 1.1rem; box-shadow: var(--shadow-sm);
}

/* =========================================================
   커스텀 컴포넌트 (src/ui/components.py)
   ========================================================= */
.nx-eyebrow {
  display: inline-flex; align-items: center; gap: .4rem;
  font-size: .78rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  color: var(--primary); background: var(--primary-50);
  padding: .3rem .65rem; border-radius: 999px; margin-bottom: .8rem;
}
.nx-title { font-size: 2rem; font-weight: 800; color: var(--navy-900);
  letter-spacing: -0.03em; line-height: 1.25; margin: 0; }
.nx-subtitle { color: var(--text-muted); font-size: 1.02rem; margin: .5rem 0 0; line-height: 1.6; }
.nx-header { margin-bottom: 1.75rem; }

.nx-hero {
  background: radial-gradient(1200px 300px at 0% 0%, #2F57E0 0%, transparent 60%),
              linear-gradient(135deg, var(--navy-800) 0%, var(--navy-900) 100%);
  color: #fff; border-radius: var(--radius-lg); padding: 2rem 2.2rem;
  box-shadow: var(--shadow-lg); margin-bottom: 1.5rem; position: relative; overflow: hidden;
}
.nx-hero::after {
  content: ""; position: absolute; right: -60px; top: -60px; width: 240px; height: 240px;
  border-radius: 50%; background: rgba(126,162,255,.12);
}
.nx-hero h2 { color: #fff !important; font-size: 1.65rem; margin: .2rem 0 .4rem; }
.nx-hero p { color: rgba(255,255,255,.78); margin: 0; line-height: 1.6; }
.nx-hero .nx-eyebrow { background: rgba(255,255,255,.12); color: #C9D6FF; }

.nx-stats { display: grid; grid-template-columns: repeat(var(--n, 4), minmax(0, 1fr)); gap: .75rem; }
.nx-stat { background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.1rem 1.2rem; box-shadow: var(--shadow-sm); height: 100%; }
.nx-stat .label { font-size: .85rem; color: var(--text-muted); font-weight: 600; }
.nx-stat .value { font-size: 1.75rem; font-weight: 800; color: var(--navy-900);
  letter-spacing: -0.03em; margin-top: .25rem; }
.nx-stat .value small { font-size: .95rem; color: var(--text-muted); font-weight: 600; }
.nx-stat .icon { width: 36px; height: 36px; border-radius: 10px; display: grid;
  place-items: center; background: var(--primary-50); font-size: 1.1rem; margin-bottom: .6rem; }

.nx-chip { display: inline-flex; align-items: center; gap: .35rem; font-size: .78rem;
  font-weight: 700; padding: .22rem .6rem; border-radius: 999px; white-space: nowrap; }
.nx-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.nx-chip.draft { background: #F1F3F8; color: var(--text-muted); }
.nx-chip.submitted { background: var(--warning-50); color: var(--warning); }
.nx-chip.reviewed { background: var(--success-50); color: var(--success); }
.nx-chip.demo { background: var(--primary-50); color: var(--primary); }

.nx-card-title { font-size: 1.08rem; font-weight: 700; color: var(--navy-900); margin: 0 0 .35rem; }
.nx-card-meta { font-size: .86rem; color: var(--text-muted); display: flex; gap: .6rem;
  align-items: center; flex-wrap: wrap; }
.nx-prompt { font-size: 1.02rem; line-height: 1.8; color: var(--text); margin: .2rem 0 0; }
.nx-label { font-size: .78rem; font-weight: 700; color: var(--text-muted);
  letter-spacing: .04em; text-transform: uppercase; margin-bottom: .45rem; }

/* 글자 수 진행바 */
.nx-progress { margin: .2rem 0 .4rem; }
.nx-progress .row { display: flex; justify-content: space-between; font-size: .86rem;
  color: var(--text-muted); margin-bottom: .4rem; font-weight: 600; }
.nx-progress .row b { color: var(--text); }
.nx-progress .track { height: 8px; background: #E9EDF5; border-radius: 999px; position: relative; overflow: hidden; }
.nx-progress .fill { height: 100%; border-radius: 999px; transition: width .3s ease; }
.nx-progress .zone { position: absolute; top: 0; bottom: 0; background: rgba(15,157,116,.13); }

/* 점수 링 + 항목 막대 */
.nx-score { display: flex; gap: 1.6rem; align-items: center; flex-wrap: wrap; }
.nx-ring { --p: 0; --c: var(--primary); width: 132px; height: 132px; border-radius: 50%;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), #E9EDF5 0);
  display: grid; place-items: center; flex-shrink: 0; }
.nx-ring > div { width: 104px; height: 104px; border-radius: 50%; background: var(--surface);
  display: grid; place-items: center; text-align: center; }
.nx-ring b { font-size: 2.1rem; font-weight: 800; color: var(--navy-900); line-height: 1; }
.nx-ring span { font-size: .78rem; color: var(--text-muted); font-weight: 600; }
.nx-score .summary { flex: 1; min-width: 220px; }
.nx-score .grade { font-size: 1.15rem; font-weight: 800; color: var(--navy-900); margin-bottom: .3rem; }
.nx-score .summary p { margin: 0; color: var(--text-secondary); line-height: 1.7; }

.nx-crit { margin: .2rem 0 1rem; }
.nx-crit .head { display: flex; justify-content: space-between; align-items: baseline; }
.nx-crit .name { font-weight: 700; color: var(--text); font-size: .95rem; }
.nx-crit .pt { font-weight: 800; color: var(--navy-900); }
.nx-crit .pt small { color: var(--text-muted); font-weight: 600; }
.nx-crit .bar { height: 8px; background: #E9EDF5; border-radius: 999px; margin: .45rem 0 .4rem; overflow: hidden; }
.nx-crit .bar div { height: 100%; border-radius: 999px; background: var(--primary); }
.nx-crit .cmt { font-size: .88rem; color: var(--text-muted); line-height: 1.6; }

.nx-list { list-style: none; padding: 0; margin: 0; }
.nx-list li { display: flex; gap: .6rem; padding: .55rem 0; color: var(--text-secondary);
  line-height: 1.6; border-bottom: 1px dashed var(--border); }
.nx-list li:last-child { border-bottom: 0; }
.nx-list li::before { content: attr(data-i); flex-shrink: 0; width: 22px; height: 22px;
  border-radius: 7px; display: grid; place-items: center; font-size: .75rem; font-weight: 800; }
.nx-list.good li::before { background: var(--success-50); color: var(--success); }
.nx-list.todo li::before { background: var(--warning-50); color: var(--warning); }

.nx-fix { border: 1px solid var(--border); border-radius: var(--radius); padding: .9rem 1rem;
  margin-bottom: .6rem; background: var(--surface-muted); }
.nx-fix .before { color: var(--danger); text-decoration: line-through;
  text-decoration-color: rgba(214,69,69,.5); background: var(--danger-50); padding: .05rem .3rem; border-radius: 4px; }
.nx-fix .after { color: var(--success); font-weight: 700; background: var(--success-50);
  padding: .05rem .3rem; border-radius: 4px; }
.nx-fix .why { font-size: .86rem; color: var(--text-muted); margin-top: .4rem; }

.nx-tip { display: flex; gap: .7rem; padding: .6rem 0; font-size: .92rem;
  color: var(--text-secondary); line-height: 1.6; }
.nx-tip .n { flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%;
  background: var(--primary-50); color: var(--primary); font-weight: 800; font-size: .78rem;
  display: grid; place-items: center; }

.nx-empty { text-align: center; padding: 3rem 1rem; background: var(--surface);
  border: 1px dashed var(--border-strong); border-radius: var(--radius-lg); }
.nx-empty .ico { font-size: 2.2rem; margin-bottom: .5rem; }
.nx-empty h4 { margin: 0 0 .3rem; }
.nx-empty p { color: var(--text-muted); margin: 0; }

.nx-user { display: flex; gap: .7rem; align-items: center; padding: .75rem;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-muted); }
.nx-avatar { width: 38px; height: 38px; border-radius: 50%; background: var(--navy-800);
  color: #fff; display: grid; place-items: center; font-weight: 700; flex-shrink: 0; }
.nx-user .nm { font-weight: 700; color: var(--text); font-size: .92rem; }
.nx-user .rl { font-size: .78rem; color: var(--text-muted); }

/* 로그인 화면 브랜드 패널 */
.nx-brand { background: linear-gradient(160deg, var(--navy-800) 0%, var(--navy-900) 100%);
  border-radius: var(--radius-lg); padding: 2.4rem 2.2rem; color: #fff; height: 100%;
  box-shadow: var(--shadow-lg); position: relative; overflow: hidden; min-height: 460px; }
.nx-brand::before { content: ""; position: absolute; width: 380px; height: 380px; right: -140px;
  bottom: -160px; border-radius: 50%; background: radial-gradient(circle, rgba(126,162,255,.35), transparent 70%); }
.nx-brand h1 { color: #fff !important; font-size: 2.1rem; line-height: 1.3; margin: 1rem 0 .8rem; }
.nx-brand p { color: rgba(255,255,255,.75); line-height: 1.7; margin: 0 0 1.6rem; }
.nx-feature { display: flex; gap: .8rem; align-items: flex-start; margin-bottom: 1rem; position: relative; }
.nx-feature .i { width: 36px; height: 36px; border-radius: 10px; background: rgba(255,255,255,.1);
  display: grid; place-items: center; flex-shrink: 0; }
.nx-feature b { display: block; color: #fff; font-size: .98rem; }
.nx-feature span { color: rgba(255,255,255,.65); font-size: .88rem; }
.nx-demo { border: 1px dashed #B9C8FA; background: var(--primary-50); border-radius: var(--radius);
  padding: .85rem 1rem; font-size: .9rem; color: var(--text-secondary); margin-bottom: 1rem; line-height: 1.6; }
.nx-demo code { background: #fff; color: var(--primary); font-weight: 700; padding: .1rem .4rem;
  border-radius: 6px; border: 1px solid var(--primary-100); }

/* ---------- 학습 화면 ---------- */
.nx-passage { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 1.3rem 1.5rem; box-shadow: var(--shadow-sm); margin-bottom: .8rem; }
.nx-passage .lbl { font-weight: 800; color: var(--navy-900); margin-bottom: .5rem; font-size: 1.05rem; }
.nx-passage p { font-size: 1.02rem; line-height: 1.95; color: var(--text); margin: 0 0 .75rem; text-indent: .6em; }
.nx-passage p:last-child { margin-bottom: 0; }
.nx-mark { display: inline-block; font-size: .74rem; font-weight: 700; color: var(--warning);
  background: var(--warning-50); border-radius: 6px; padding: .1rem .45rem; margin-bottom: .3rem; }
.nx-interp { border: 1px dashed var(--border-strong); background: var(--surface-muted);
  border-radius: var(--radius); padding: .9rem 1.1rem; margin: .6rem 0 1rem; }
.nx-interp .tag { font-size: .74rem; font-weight: 700; color: var(--text-muted); letter-spacing: .02em; }
.nx-interp p { margin: .35rem 0 0; font-weight: 600; color: var(--text); line-height: 1.7; }
.nx-task { margin-bottom: .6rem; }
.nx-chat { display: flex; flex-direction: column; gap: .55rem; margin: .4rem 0 1rem; }
.nx-msg { max-width: 92%; padding: .75rem 1rem; border-radius: 14px; line-height: 1.7; font-size: .95rem;
  white-space: pre-wrap; }
.nx-msg .tag { font-size: .72rem; font-weight: 800; letter-spacing: .02em; margin-bottom: .2rem; opacity: .8; }
.nx-msg.me { align-self: flex-end; background: var(--primary-50); color: var(--navy-900);
  border-bottom-right-radius: 4px; }
.nx-msg.tutor { align-self: flex-start; background: var(--surface); border: 1px solid var(--border);
  color: var(--text); border-bottom-left-radius: 4px; box-shadow: var(--shadow-sm); }
.nx-msg.tutor.direction .tag, .nx-msg.tutor.confirm .tag { color: var(--primary); }
.nx-msg.tutor.explanation, .nx-msg.tutor.demo { background: #FBF8F1; border-color: #EFE3C8; }
.nx-msg.tutor.explanation .tag, .nx-msg.tutor.demo .tag { color: var(--warning); }
.nx-msg.tutor.done, .nx-msg.tutor.ack { background: var(--success-50); border-color: #CBEBDF; }
.nx-msg.tutor.done .tag, .nx-msg.tutor.ack .tag { color: var(--success); }
.nx-dots { display: flex; gap: .35rem; margin: .3rem 0 1rem; flex-wrap: wrap; }
.nx-dots span { width: 28px; height: 6px; border-radius: 999px; background: #E3E7F0; }
.nx-dots .done { background: var(--success); }
.nx-dots .skipped { background: #B9E3D4; }
.nx-dots .current { background: var(--primary); }
.nx-topic { display: flex; gap: .9rem; align-items: flex-start; }
.nx-topic .num { width: 40px; height: 40px; border-radius: 12px; background: var(--primary-50);
  color: var(--primary); font-weight: 800; display: grid; place-items: center; flex-shrink: 0; }
.nx-topic.done .num { background: var(--success-50); color: var(--success); }
.nx-chip.todo { background: #F1F3F8; color: var(--text-muted); }
.nx-chip.active { background: var(--primary-50); color: var(--primary); }
.nx-chip.paused { background: var(--warning-50); color: var(--warning); }
.nx-chip.done { background: var(--success-50); color: var(--success); }
.nx-level { display: inline-block; font-size: .78rem; font-weight: 700; border-radius: 999px; padding: .15rem .55rem; }
.nx-level.l3 { background: var(--success-50); color: var(--success); }
.nx-level.l2 { background: var(--primary-50); color: var(--primary); }
.nx-level.l1 { background: var(--warning-50); color: var(--warning); }
.nx-level.l0 { background: var(--danger-50); color: var(--danger); }
.nx-level.ln { background: #F1F3F8; color: var(--text-muted); }

/* ---------- 반응형 ---------- */
@media (max-width: 900px) {
  .stMainBlockContainer, [data-testid="stMainBlockContainer"] { padding: 1.5rem 1.1rem 4rem; }
  .nx-title { font-size: 1.6rem; }
  .nx-hero { padding: 1.5rem 1.4rem; }
  .nx-hero h2 { font-size: 1.35rem; }
  .nx-brand { min-height: auto; padding: 1.8rem 1.5rem; }
  .nx-brand h1 { font-size: 1.6rem; }
}
@media (max-width: 640px) {
  /* 상단 고정 헤더(로고·메뉴 버튼)와 겹치지 않도록 위쪽 여백 확보 */
  .stMainBlockContainer, [data-testid="stMainBlockContainer"] { padding: 4rem 1rem 4rem; }
  .nx-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; }
  .nx-stat { padding: .9rem 1rem; }
  .nx-stat .value { font-size: 1.45rem; }
  .nx-stat .icon { width: 30px; height: 30px; font-size: .95rem; margin-bottom: .45rem; }
  .nx-title { font-size: 1.4rem; }
  .nx-subtitle { font-size: .95rem; }
  .nx-ring { width: 108px; height: 108px; }
  .nx-ring > div { width: 84px; height: 84px; }
  .nx-ring b { font-size: 1.7rem; }
  .st-key-editor textarea { font-size: 1rem !important; padding: 1rem !important; min-height: 360px; }
  div[class*="st-key-card"] { padding: 1.1rem; }
  .nx-brand .nx-feature:nth-of-type(n+3) { display: none; }
  .stTabs [data-baseweb="tab-list"] { width: 100%; }
  .stTabs [data-baseweb="tab"] { flex: 1; }
}
</style>
"""


def apply_theme() -> None:
    st.html(_CSS.replace("__FONT__", _FONT_URL).replace("__VARS__", _VARS))
