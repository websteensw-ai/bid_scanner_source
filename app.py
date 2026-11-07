"""테이커스 비전 기호 분석시스템 - 유튜브 주소 입력 화면.

- 테스트 모드(기본): 저장된 분석 결과를 보여준다. 토큰과 유튜브 호출이 없다.
- 실제 분석: 유튜브 자막과 채팅을 내려받아 같은 형식으로 분석한다.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import networkx as nx
import pandas as pd
import streamlit as st
from kiwipiepy import Kiwi

from src.demo import load_demo
from src.pipeline import (analyze, anonymize, chat_quotes_check, parse_chat_jsonl,
                          parse_vtt)
from src.view import result_to_view
from src.youtube import YouTubeError, fetch_captions_and_chat, parse_video_id

st.set_page_config(page_title="테이커스 비전 기호 분석시스템", layout="wide")

# 한글 라벨용 글꼴 (packages.txt의 fonts-noto-cjk 설치 시 사용 가능)
for _name in ("Noto Sans CJK JP", "Noto Sans CJK KR", "Noto Sans CJK SC"):
    if any(f.name == _name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _name
        break
plt.rcParams["axes.unicode_minus"] = False

LOADING_STAGES = ["자막 확인 중", "채팅 정리 중", "명사 추출 중", "네트워크 계산 중", "결과 그리는 중"]
MIN_LOADING_SEC = 5.0


LOADING_EMOJIS = ["🍩", "🍰", "☕", "🍷", "🧁", "🍪", "🥐", "🍕"]


def loading_loop(future, start: float, emoji_slot, bar_slot):
    """최소 5초 동안 이모지를 돌리고, 분석이 끝날 때까지 진행 막대를 보여준다."""
    i = 0
    while True:
        elapsed = time.time() - start
        frac = min(1.0, elapsed / MIN_LOADING_SEC)
        if not future.done():
            frac = min(frac, 0.95)
        idx = min(len(LOADING_STAGES) - 1, int(frac * len(LOADING_STAGES)))
        emoji_slot.markdown(
            f"<div style='text-align:center;font-size:72px;line-height:1.2'>"
            f"{LOADING_EMOJIS[i % len(LOADING_EMOJIS)]}</div>"
            f"<div style='text-align:center'>{LOADING_STAGES[idx]}...</div>",
            unsafe_allow_html=True)
        bar_slot.progress(frac)
        i += 1
        if future.done() and elapsed >= MIN_LOADING_SEC:
            break
        time.sleep(0.8)


QUOTES = ["부채살 좋아", "빨리 먹고 싶", "고기 많이 드세요", "별도로 구매", "완판 기원",
          "얘기많이", "얼릉 고기", "완판 가즈아", "양지원 가수님 응원"]


@st.cache_resource
def get_kiwi():
    return Kiwi()


def run_real(url: str) -> dict:
    vid = parse_video_id(url)
    got = fetch_captions_and_chat(vid)
    if not got["vtt"]:
        raise YouTubeError("자동 자막을 찾지 못했습니다. 자막이 없는 영상일 수 있습니다.")
    segs = parse_vtt(got["vtt"].read_text(encoding="utf-8"))
    chat = parse_chat_jsonl(got["chat"].read_text(encoding="utf-8")) if got["chat"] else []
    anonymize(chat)
    res = analyze(segs, chat, get_kiwi())
    quotes = chat_quotes_check(chat, QUOTES)
    return result_to_view(res, got["title"], got["duration_min"], quotes)


def network_figure(nodes, edges):
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], freq=n["freq"], comm=n["community"])
    for e in edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])
    if not G.number_of_nodes():
        return None
    pos = nx.spring_layout(G, k=0.9, seed=7, weight="weight")
    palette = ["#1d6a64", "#b5652b", "#7d5ba6", "#5b7fa6", "#8a8a3a"]
    fig, ax = plt.subplots(figsize=(9, 7), dpi=110)
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#999999", alpha=0.5,
                           width=[0.4 + G[u][v]["weight"] / 5 for u, v in G.edges])
    nx.draw_networkx_nodes(G, pos, ax=ax, alpha=0.92,
                           node_color=[palette[G.nodes[n]["comm"] % 5] if G.nodes[n]["comm"] >= 0 else "#888" for n in G.nodes],
                           node_size=[60 + G.nodes[n]["freq"] * 14 for n in G.nodes])
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=9)
    ax.axis("off")
    return fig


def render(view: dict):
    chat = view["chat"]
    total = chat["n_msgs"]
    cats = dict(chat["cats"])
    st.subheader(view["video_title"] or "분석 결과")
    if view.get("note"):
        st.caption(view["note"])

    fan = cats.get("팬덤 응원", 0)
    buy = cats.get("구매 언급", 0) + cats.get("상품 선호", 0)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("방송 길이", f"{view['duration_min']} 분")
    k2.metric("채팅 메시지", f"{total:,}")
    k3.metric("채팅 참여자", f"{chat['n_authors']:,}")
    k4.metric("팬덤 응원 비중", f"{(fan / total * 100 if total else 0):.1f}%")
    k5.metric("구매·상품 언급 비중", f"{(buy / total * 100 if total else 0):.1f}%")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**채팅 참여 유형**")
        if chat["cats"]:
            df = pd.DataFrame(sorted(chat["cats"], key=lambda x: x[1]),
                              columns=["유형", "건수"]).set_index("유형")
            st.bar_chart(df, horizontal=True)
        st.caption("키워드 규칙으로 분류했습니다.")
    with c2:
        st.markdown("**분 단위 채팅량 (유형별)**")
        if chat["per_min_cat"]:
            rows = []
            for minute, c in sorted(chat["per_min_cat"].items(), key=lambda x: int(x[0])):
                row = {"분": int(minute)}
                row.update(c)
                rows.append(row)
            tdf = pd.DataFrame(rows).fillna(0).set_index("분")
            st.bar_chart(tdf)

    st.markdown("**판매 발화와 판매 반응의 시간 흐름**")
    if chat["sale_talk_min"] or chat["per_min_cat"]:
        sale_talk = dict((int(k), v) for k, v in chat["sale_talk_min"])
        mins = sorted(set(sale_talk) | {int(m) for m in chat["per_min_cat"]})
        sale_chat = {int(m): c.get("구매 언급", 0) + c.get("판매 응원(완판)", 0)
                     for m, c in chat["per_min_cat"].items()}
        sdf = pd.DataFrame({"방송 판매 발화 구간": [sale_talk.get(m, 0) for m in mins],
                            "채팅 구매·완판 반응": [sale_chat.get(m, 0) for m in mins]},
                           index=mins)
        st.line_chart(sdf)
        if view["correlation"] is not None:
            st.caption(f"상관계수 r = {view['correlation']:.2f} (분 단위, 약한 양의 관계는 인과를 뜻하지 않습니다)")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**방송 핵심어 (명사 빈도)**")
        if view["terms"]:
            tdf = pd.DataFrame(sorted([(t["term"], t["freq"]) for t in view["terms"][:25]],
                                      key=lambda x: x[1]),
                               columns=["명사", "빈도"]).set_index("명사")
            st.bar_chart(tdf, horizontal=True)
    with c4:
        st.markdown("**채팅 핵심어**")
        if chat["chat_nouns"]:
            cdf = pd.DataFrame(sorted(chat["chat_nouns"][:20], key=lambda x: x[1]),
                               columns=["명사", "빈도"]).set_index("명사")
            st.bar_chart(cdf, horizontal=True)
        else:
            st.caption("이 결과에는 채팅 핵심어가 없습니다.")

    st.markdown("**핵심어 공출현 네트워크**")
    fig = network_figure(view["network"]["nodes"], view["network"]["edges"])
    if fig:
        st.pyplot(fig)
        comms = view["network"]["communities"]
        if comms:
            st.caption("주제군: " + " / ".join(", ".join(c[:6]) for c in comms))
    else:
        st.caption("네트워크 데이터가 없습니다.")

    if view["quotes"]:
        st.markdown("**논문 인용 채팅 검증**")
        qdf = pd.DataFrame(view["quotes"])
        st.dataframe(qdf, hide_index=True)

    if view["sections"]:
        st.markdown("**방송 구간별 비교**")
        st.json(view["sections"], expanded=False)


st.title("테이커스 비전 기호 분석시스템")
st.caption("유튜브 주소를 입력하면 자막과 채팅을 가져와 분석합니다.")

mode = st.radio("모드", ["샘플 결과", "실제 분석"], horizontal=True)
url = st.text_input("유튜브 주소", placeholder="https://www.youtube.com/watch?v=77nP8lcSuzY")
go = st.button("분석하기", type="primary")

if go:
    start = time.time()
    emoji_slot = st.empty()
    bar_slot = st.empty()
    get_kiwi()  # 스레드 시작 전에 메인 스레드에서 로드

    def work():
        if mode.startswith("샘플"):
            parse_video_id(url or "77nP8lcSuzY")
            return load_demo()
        return run_real(url)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(work)
    loading_loop(future, start, emoji_slot, bar_slot)
    emoji_slot.empty()
    bar_slot.empty()
    executor.shutdown(wait=False)
    try:
        st.session_state["view"] = future.result()
    except YouTubeError as exc:
        st.error(str(exc))

if "view" in st.session_state:
    st.divider()
    render(st.session_state["view"])
else:
    st.info("주소를 입력하고 분석하기를 누르세요. 샘플 결과는 바로 보입니다.")
