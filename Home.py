# Home.py — 멀티페이지 진입 페이지 (Streamlit)
# 사용법:
#   /repo
#   ├─ Home.py                 ← 메인 파일(Cloud에서 Main file로 지정)
#   └─ pages/
#      ├─ 1_graph.py           ← 그래프(= 기존 graph_app_final.py 내용)
#      └─ 2_assessment.py      ← 서술형 평가(= 기존 app.py 내용)
#   ※ 파일명은 임의 변경 가능. 아래 'page_targets'만 맞춰 주세요.

import streamlit as st

st.set_page_config(page_title="수업 포털", page_icon="📚", layout="wide")

st.title("📚 수업 포털")
st.caption("이 앱은 열에너지 그래프 작성과 서술형 평가 채점을 한곳에서 제공합니다.")

# ---- 페이지 경로(파일명)만 여러분 레포 구조에 맞게 조정하세요 ----
page_targets = {
    "graph": ["pages/1_graph.py", "pages/1_그래프.py", "1_graph", "1_그래프"],
    "assessment": ["pages/2_assessment.py", "pages/2_서술형.py", "2_assessment", "2_서술형"],
}
# ---------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 열에너지 방출 그래프")
    st.write("시간–온도 데이터를 표로 입력하면, 그래프 생성 → 제출 → 대시보드 공유까지 진행됩니다.")
    # 내비게이션: page_link(안전) + 버튼(switch_page 시도)
    st.page_link(page_targets["graph"][0], label="→ 열기", icon="📈")
    if st.button("바로 이동", key="go_graph"):
        for p in page_targets["graph"]:
            try:
                st.switch_page(p)
                break
            except Exception:
                continue
        else:
            st.warning("좌측 사이드바에서 ‘열에너지…’ 페이지를 선택하세요.")

with col2:
    st.subheader("🧪 서술형 평가 채점")
    st.write("3문항(2-1, 2-2 포함)을 입력하면 성취수준(A–D)과 간결 피드백을 생성하고 DB에 저장합니다.")
    st.page_link(page_targets["assessment"][0], label="→ 열기", icon="🧪")
    if st.button("바로 이동", key="go_assessment"):
        for p in page_targets["assessment"]:
            try:
                st.switch_page(p)
                break
            except Exception:
                continue
        else:
            st.warning("좌측 사이드바에서 ‘서술형…’ 페이지를 선택하세요.")

st.divider()
st.markdown("#### 배포 체크")
st.markdown("- 좌측 사이드바에 **Pages** 항목이 보이면 멀티페이지가 정상 구성된 것입니다.")
st.markdown("- 페이지가 보이지 않으면 레포 구조와 파일명을 다시 확인해 주세요.")
st.markdown("- 이미지가 필요한 경우 `/image/` 폴더에 `image1.png, image2.png, image3.png`가 있는지 확인하세요.")
