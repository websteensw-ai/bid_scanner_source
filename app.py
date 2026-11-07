"""테이커스 비전 기호 분석시스템 - Streamlit 앱.

실행: streamlit run app.py
"""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st
from kiwipiepy import Kiwi

from src.pipeline import (
    CHAT_CATEGORIES, CHAT_OTHER, analyze, anonymize, parse_chat_jsonl, parse_vtt,
)

st.set_page_config(page_title="테이커스 비전 기호 분석시스템", layout="wide")


@st.cache_resource
def get_kiwi():
    return Kiwi()


@st.cache_data(show_spinner=False)
def run_pipeline(vtt_text, chat_text, window, top_n, min_edge):
    segments = parse_vtt(vtt_text) if vtt_text else []
    chat = parse_chat_jsonl(chat_text) if chat_text else []
    anonymize(chat)
    return analyze(segments, chat, get_kiwi(), window_sec=window,
                   top_n=top_n, min_edge=min_edge)


def network_figure(nodes, edges):
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], freq=n["freq"], comm=n["community"])
    for e in edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])
    pos = nx.spring_layout(G, k=0.9, seed=7, weight="weight")
    palette = ["#1d6a64", "#b5652b", "#7d5ba6", "#5b7fa6", "#8a8a3a"]
    fig, ax = plt.subplots(figsize=(9, 7), dpi=110)
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#999999", alpha=0.5,
                           width=[0.4 + G[u][v]["weight"] / 5 for u, v in G.edges])
    nx.draw_networkx_nodes(G, pos, ax=ax, alpha=0.92,
                           node_color=[palette[G.nodes[n]["comm"] % 5] for n in G.nodes],
                           node_size=[60 + G.nodes[n]["freq"] * 14 for n in G.nodes])
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=9)
    ax.axis("off")
    return fig


st.title("테이커스 비전 기호 분석시스템")
st.caption("유튜브 방송의 자막과 채팅을 핵심어, 네트워크, 참여 유형, 시간 흐름으로 분석합니다.")

with st.sidebar:
    st.header("입력")
    vtt_file = st.file_uploader("자동자막 (.vtt)", type=["vtt"])
    chat_file = st.file_uploader("채팅 리플레이 (.json / .jsonl)", type=["json", "jsonl"])
    st.header("설정")
    window = st.slider("공출현 창 (초)", 30, 180, 60, 10)
    top_n = st.slider("네트워크 노드 수", 10, 80, 45, 5)
    min_edge = st.slider("최소 공출현 횟수", 1, 10, 3)

if not vtt_file and not chat_file:
    st.info("왼쪽에서 자막 파일 또는 채팅 파일을 올려 주세요. 채팅 작성자는 익명 ID로 바뀝니다.")
    st.stop()

vtt_text = vtt_file.getvalue().decode("utf-8") if vtt_file else ""
chat_text = chat_file.getvalue().decode("utf-8") if chat_file else ""

with st.spinner("분석 중..."):
    res = run_pipeline(vtt_text, chat_text, window, top_n, min_edge)

total = sum(c for _, c in res.category_counts)
k1, k2, k3, k4 = st.columns(4)
k1.metric("자막 구간", f"{len(res.segments):,}")
k2.metric("채팅 메시지", f"{total:,}")
k3.metric("네트워크 노드 / 간선", f"{len(res.graph_nodes)} / {len(res.graph_edges)}")
k4.metric("판매 발화 ↔ 판매 반응 r", "-" if res.correlation is None else f"{res.correlation:.2f}")

tab1, tab2, tab3, tab4 = st.tabs(["핵심어", "네트워크", "채팅 참여", "시간 흐름"])

with tab1:
    if res.term_freq:
        df = pd.DataFrame(res.term_freq, columns=["명사", "빈도"]).set_index("명사")
        st.bar_chart(df, horizontal=True)
    else:
        st.write("자막이 없어 핵심어를 계산하지 않았습니다.")

with tab2:
    if res.graph_nodes:
        st.pyplot(network_figure(res.graph_nodes, res.graph_edges))
        st.subheader("주제군")
        for i, c in enumerate(res.communities, 1):
            st.write(f"**{i}.** " + ", ".join(c))
        bet = sorted(res.graph_nodes, key=lambda n: -n["betweenness"])[:8]
        st.subheader("매개 중심성 상위")
        st.dataframe(pd.DataFrame(bet)[["id", "freq", "betweenness"]], hide_index=True)
    else:
        st.write("공출현 간선이 없습니다. 최소 공출현 횟수를 낮춰 보세요.")

with tab3:
    if res.category_counts:
        cdf = pd.DataFrame(res.category_counts, columns=["유형", "건수"])
        cdf["비율(%)"] = (cdf["건수"] / total * 100).round(1)
        st.dataframe(cdf, hide_index=True)
        st.bar_chart(cdf.set_index("유형")["건수"], horizontal=True)
        st.caption(f"키워드 규칙으로 분류했습니다. '{CHAT_OTHER}'는 규칙에 맞지 않은 메시지입니다.")
    else:
        st.write("채팅 파일이 없습니다.")

with tab4:
    if res.per_minute:
        rows = []
        for minute, cats in res.per_minute.items():
            row = {"분": minute}
            row.update(cats)
            rows.append(row)
        tdf = pd.DataFrame(rows).fillna(0).set_index("분")
        st.area_chart(tdf)
        st.caption("분 단위 채팅량을 유형별로 나눈 그래프입니다.")
    else:
        st.write("채팅 파일이 없습니다.")

st.divider()
export = {"autocaption_segments": [s.__dict__ for s in res.segments],
          "term_freq": res.term_freq, "communities": res.communities,
          "category_counts": res.category_counts, "correlation": res.correlation}
import json
st.download_button("분석 결과 JSON 내려받기", json.dumps(export, ensure_ascii=False, indent=2),
                   file_name="takers_vision_result.json", mime="application/json")
