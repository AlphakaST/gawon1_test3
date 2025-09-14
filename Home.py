# Home.py — 멀티페이지 진입
import streamlit as st

st.set_page_config(page_title="수업 포털", page_icon="📚", layout="wide")

# 실제 파일 경로(여기만 여러분 레포 구조에 맞게 수정)
GRAPH_PAGE = "pages/1_graph.py"   # ex) pages/1_📈열에너지_그래프.py
ASSESS_PAGE = "pages/2_app.py"    # ex) pages/2_🧪서술형_평가.py

st.title("📚 수업 포털")
st.caption("열에너지 그래프 작성과 서술형 평가 채점을 한 곳에서 제공합니다.")

# 메인 카드 레이아웃
c1, c2 = st.columns(2)

with c1:
    st.markdown("### 📈 열에너지 방출 그래프")
    st.write("시간–온도 데이터를 표로 입력하면 그래프 생성 → 제출 → 대시보드 공유까지 진행됩니다.")
    # ✔ 버튼만 남기고 page_link는 제거
    if st.button("바로 이동", type="primary", use_container_width=True, key="go_graph"):
        try:
            st.switch_page(GRAPH_PAGE)
        except Exception:
            st.warning("좌측 사이드바에서 ‘열에너지 그래프’ 페이지를 선택하세요.")

with c2:
    st.markdown("### 🧪 서술형 평가 채점")
    st.write("3문항(2-1, 2-2 포함)을 입력하면 성취수준(A–D)과 간결 피드백을 생성하고 DB에 저장합니다.")
    if st.button("바로 이동", type="primary", use_container_width=True, key="go_assessment"):
        try:
            st.switch_page(ASSESS_PAGE)
        except Exception:
            st.warning("좌측 사이드바에서 ‘서술형 평가’ 페이지를 선택하세요.")
