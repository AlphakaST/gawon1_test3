# Home.py (수정 포인트만)
import streamlit as st

st.set_page_config(page_title="수업 포털", page_icon="📚", layout="wide")
st.title("📚 수업 포털")
st.caption("이 앱은 열에너지 그래프와 서술형 평가 채점을 한곳에서 제공합니다.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 열에너지 방출 그래프")
    st.write("시간–온도 데이터를 표로 입력하면, 그래프 생성 → 제출 → 대시보드 공유까지 진행됩니다.")
    # 정확한 경로 지정
    st.page_link("pages/1_graph.py", label="→ 열기", icon="📈")
    if st.button("바로 이동", key="go_graph"):
        try:
            st.switch_page("pages/1_graph.py")
        except Exception:
            st.warning("좌측 사이드바에서 ‘열에너지…’ 페이지를 선택하세요.")

with col2:
    st.subheader("🧪 서술형 평가 채점")
    st.write("3문항(2-1, 2-2 포함)을 입력하면 성취수준(A–D)과 간결 피드백을 생성하고 DB에 저장합니다.")
    # 파일명이 2_app.py 임
    st.page_link("pages/2_app.py", label="→ 열기", icon="🧪")
    if st.button("바로 이동", key="go_assessment"):
        try:
            st.switch_page("pages/2_app.py")
        except Exception:
            st.warning("좌측 사이드바에서 ‘서술형…’ 페이지를 선택하세요.")

st.divider()
st.markdown("#### 배포 체크")
st.markdown("- 좌측 사이드바에 **1_graph / 2_app**가 보이면 멀티페이지가 정상입니다.")
st.markdown("- 파일명/대소문자/경로가 실제 리포지토리와 일치해야 합니다.")
