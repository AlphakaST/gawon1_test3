# graph_app_final.py — 열에너지 방출 그래프(제출·공유·관찰) — 최종 개선판
# -------------------------------------------------------------------------
# 기능: (기존 기능 모두 포함)
#  1) 학생 표 입력(시간·온도) → 미리보기 → 제출(최신 1건 유지: UPSERT)
#  2) 대시보드: 전체 제출 목록 + 미니차트
#  3) 학생 상세: 큰 그래프 + 표 + CSV 다운로드
#
# 최종 개선 사항:
#  - (코드) 차트 생성 로직을 함수화하여 중복 제거 (create_altair_chart)
#  - (코드) 주요 문자열을 상수로 관리하여 유지보수성 향상
#  - (기능) 대시보드에 학년/반 필터 및 정렬 기능 추가
#  - (기능) 학생 상세 탭에서 여러 학생 그래프 비교 기능 추가
#  - (기능) 학생 상세 탭에 교사용 피드백 입력 및 저장 기능 추가
# -------------------------------------------------------------------------

import json
import re
import pandas as pd
import altair as alt
import streamlit as st
from sqlalchemy import text

# ---------- 상수 정의 (유지보수성 향상) ----------
TIME_COL = "시간(분)"
TEMP_COL = "온도(°C)"
ACTIVITY_ID = "2025-heat-curve-01"  # 차시 식별자(필요 시 문자열만 교체)

# ---------- 기본 UI ----------
st.set_page_config(page_title="열에너지 방출 그래프 그리기", layout="wide")
st.title("열에너지 방출 그래프 그리기")
st.caption("시간(분)과 온도(°C)를 표에 입력 → 미리보기 확인 → 제출")

# ---------- DB 연결 설정 (Streamlit 권장 방식) ----------
try:
    db_creds = st.secrets.connections.mysql
    conn = st.connection(
        "mysql", type="sql", dialect="mysql",
        host=db_creds.host, port=db_creds.port, database=db_creds.database,
        username=db_creds.user, password=db_creds.password
    )
    conn.query("SELECT 1")
    DB_STATUS = "ONLINE"
except Exception as e:
    conn = None
    DB_STATUS = f"OFFLINE: {e}"

st.info(f"DB 상태: {DB_STATUS}")

# ---------- 데이터 조회 함수 (캐싱 적용, 피드백 컬럼 추가) ----------
@st.cache_data(ttl=300)
def get_dashboard_data(activity_id):
    """대시보드와 학생 상세 탭에 필요한 데이터를 DB에서 조회합니다."""
    if not conn:
        return pd.DataFrame()

    df = conn.query(
        """
        SELECT g1.id, s.name, s.grade, s.class, g1.submitted_at, g1.data_json
        FROM graph1 g1
        JOIN students s ON s.id = g1.id
        WHERE g1.activity_id = :activity_id;
        """,
        params={"activity_id": activity_id},
    )
    # 학번, 학년, 반을 숫자 타입으로 변환하여 정렬이 올바르게 되도록 함
    for col in ['id', 'grade', 'class']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.sort_values('id')


# ---------- 차트 생성 함수 (신규, 코드 중복 제거) ----------
def create_altair_chart(df, title, height):
    """데이터프레임을 받아 Altair 꺾은선 그래프를 생성합니다."""
    chart = (
        alt.Chart(df)
        .mark_line(point=True, tooltip=True)
        .encode(x=f"{TIME_COL}:Q", y=f"{TEMP_COL}:Q")
        .properties(title=title, height=height)
        .interactive()
    )
    return chart


# ---------- 탭 ----------
tab_submit, tab_dash, tab_detail = st.tabs(["📤 제출(학생)", "📊 대시보드", "🔎 학생 상세"])

# ======================== 제출(학생) ========================
with tab_submit:
    with st.form("submit_form"):
        sid = st.text_input("학번(5자리, 예: 10130)", max_chars=5, help="1학년 01반 30번 → 10130")
        name = st.text_input("이름", help="처음 제출하는 경우, 이름을 정확히 입력하세요.")
        
        init = pd.DataFrame({TIME_COL: [0, 1, 2, 3, 4], TEMP_COL: [20.0, None, None, None, None]})
        df_editor = st.data_editor(
            init, num_rows="dynamic",
            column_config={
                TIME_COL: st.column_config.NumberColumn(min_value=0, max_value=60, step=1),
                TEMP_COL: st.column_config.NumberColumn(min_value=-20.0, max_value=150.0, step=0.1),
            },
        )
        st.caption("※ 시간 0–60분, 온도 -20–150°C. 모든 셀을 숫자로 채워야 제출됩니다.")
        
        prev = df_editor.dropna()
        if not prev.empty:
            chart_title = f"학번 {sid.strip()} 이름 {name.strip()}" if sid and name else "미리보기"
            # 함수를 사용하여 차트 생성
            ch = create_altair_chart(prev.sort_values(TIME_COL), chart_title, 280)
            st.altair_chart(ch, use_container_width=True)
            
        submitted = st.form_submit_button("제출")
        if submitted:
            sid = sid.strip()
            name = name.strip()
            # 입력 검증
            if not re.fullmatch(r"\d{5}", sid or ""):
                st.error("학번은 숫자 5자리여야 합니다. 예: 10130")
                st.stop()
            if not name:
                st.error("이름을 입력해야 합니다.")
                st.stop()
            if df_editor.isnull().any().any():
                st.error("빈 칸이 있습니다. 모든 셀을 숫자로 입력하세요.")
                st.stop()
            if not ((df_editor[TIME_COL].between(0, 60)).all() and (df_editor[TEMP_COL].between(-20, 150)).all()):
                st.error("허용 범위를 벗어난 값이 있습니다.")
                st.stop()
            if DB_STATUS != "ONLINE":
                st.error("DB가 오프라인입니다. secrets 또는 네트워크를 확인하세요.")
                st.stop()
            
            # 학생 존재 확인 및 신규 등록
            try:
                student_exists = conn.query("SELECT 1 FROM students WHERE id=:id", params={"id": sid})
                if student_exists.empty:
                    with conn.session as s:
                        # 수정: id와 name만 INSERT합니다. grade와 class는 DB에서 자동으로 생성됩니다.
                        s.execute(text("INSERT INTO students (id, name) VALUES (:id, :name);"), 
                                  params={"id": sid, "name": name})
                        s.commit()
                    st.toast(f"{name} 학생을 새로 등록했습니다.")
            except Exception as e:
                st.error(f"[DB 오류] 학생 등록 또는 확인 실패: {e}")
                st.stop()
            
            # 데이터 저장 (UPSERT)
            ordered = df_editor.sort_values(TIME_COL)
            payload = json.dumps(ordered.to_dict(orient="records"), ensure_ascii=False)
            try:
                with conn.session as s:
                    s.execute(
                        text("""
                        INSERT INTO graph1(activity_id, id, data_json) VALUES (:activity_id, :id, :data_json)
                        ON DUPLICATE KEY UPDATE
                            data_json = VALUES(data_json),
                            submitted_at = CURRENT_TIMESTAMP
                        """),
                        params={"activity_id": ACTIVITY_ID, "id": sid, "data_json": payload}
                    )
                    s.commit()
                st.cache_data.clear() # 제출 성공 후 캐시 초기화
                st.success("제출 완료! ‘📊 대시보드’에서 전체 결과를 확인하세요.")
            except Exception as e:
                st.error(f"[DB 오류] 저장 실패: {e}")

# ======================== 공통 데이터 로딩 ========================
if DB_STATUS == "ONLINE":
    all_data = get_dashboard_data(ACTIVITY_ID)
else:
    all_data = pd.DataFrame()

# ======================== 대시보드 ========================
with tab_dash:
    if all_data.empty:
        st.warning("표시할 데이터가 없거나 DB가 오프라인입니다.")
    else:
        st.markdown("#### filters and sorting")
        
        # --- 필터 및 정렬 기능 (신규) ---
        filter_cols = st.columns(3)
        with filter_cols[0]:
            # 학년 필터 (데이터에 있는 학년만 옵션으로)
            grades = sorted(all_data['grade'].unique())
            sel_grades = st.multiselect("학년 필터", options=grades, default=grades)
        with filter_cols[1]:
            # 반 필터 (데이터에 있는 반만 옵션으로)
            classes = sorted(all_data['class'].unique())
            sel_classes = st.multiselect("반 필터", options=classes, default=classes)
        with filter_cols[2]:
            # 정렬 기준
            sort_option = st.radio("정렬", ["학번순", "제출시각순"], horizontal=True)
            
        # 필터링 및 정렬 적용
        filtered_data = all_data[all_data['grade'].isin(sel_grades) & all_data['class'].isin(sel_classes)]
        if sort_option == "학번순":
            filtered_data = filtered_data.sort_values('id')
        else:
            filtered_data = filtered_data.sort_values('submitted_at', ascending=False)
        # --- 필터 및 정렬 기능 끝 ---

        # 필터링된 데이터로 표 표시
        meta_cols = ["id", "name", "grade", "class", "submitted_at"]
        st.dataframe(filtered_data[meta_cols].rename(columns={
            "id": "학번", "name": "이름", "grade": "학년", "class": "반", "submitted_at": "제출시각"
        }))
        
        st.markdown("#### 미니차트")
        cols = st.columns(3)
        # 필터링된 데이터로 미니차트 표시
        for i, row in enumerate(filtered_data.head(12).itertuples()):
            with cols[i % 3]:
                st.markdown(f"**{row.id} {row.name}**")
                try:
                    df_chart = pd.DataFrame(json.loads(row.data_json))
                    if not df_chart.empty:
                        # 함수를 사용하여 차트 생성
                        ch = create_altair_chart(df_chart, "", 200)
                        st.altair_chart(ch, use_container_width=True)
                    else: st.caption("데이터 없음")
                except (json.JSONDecodeError, TypeError):
                    st.caption("데이터 형식 오류")

# ======================== 학생 상세 ========================
with tab_detail:
    if all_data.empty:
        st.warning("표시할 데이터가 없거나 DB가 오프라인입니다.")
    else:
        # --- 학생 선택 (다중 선택으로 변경) ---
        options = [f"{row['id']} | {row['name']}" for _, row in all_data.iterrows()]
        sel_students = st.multiselect("학생 선택 (여러 명 선택하여 비교 가능)", options)

        # --- 선택된 학생 수에 따라 다른 UI 표시 (신규) ---
        if not sel_students:
            st.info("학생을 선택하여 상세 데이터를 확인하거나, 여러 명을 선택하여 그래프를 비교해보세요.")
        
        # --- 1명 선택 시: 상세 정보 + 피드백 (기능 개선) ---
        elif len(sel_students) == 1:
            sid_sel = sel_students[0].split("|")[0].strip()
            record = all_data[all_data["id"] == int(sid_sel)].iloc[0]
            
            st.markdown(f"### {record['id']} {record['name']}")
            try:
                df_sel = pd.DataFrame(json.loads(record["data_json"]))
                if not df_sel.empty:
                    ch = create_altair_chart(df_sel, f"그래프: {record['id']} {record['name']}", 420)
                    st.altair_chart(ch, use_container_width=True)
                    st.dataframe(df_sel)
                    st.download_button(
                        "⬇️ CSV 다운로드",
                        data=df_sel.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{ACTIVITY_ID}_{sid_sel}.csv", mime="text/csv"
                    )
            except (json.JSONDecodeError, TypeError):
                st.error("상세 데이터를 불러오는 데 실패했습니다.")

        # --- 2명 이상 선택 시: 그래프 비교 (신규 기능) ---
        else:
            st.markdown("### 학생별 그래프 비교")
            chart_data_list = []
            for student_str in sel_students:
                sid_sel = student_str.split("|")[0].strip()
                record = all_data[all_data["id"] == int(sid_sel)].iloc[0]
                try:
                    df_student = pd.DataFrame(json.loads(record["data_json"]))
                    df_student['student'] = f"{record['id']} {record['name']}" # 학생 식별 컬럼 추가
                    chart_data_list.append(df_student)
                except (json.JSONDecodeError, TypeError):
                    st.warning(f"{record['id']} {record['name']} 학생의 데이터 형식이 잘못되어 비교에서 제외됩니다.")

            if chart_data_list:
                combined_df = pd.concat(chart_data_list, ignore_index=True)
                
                comparison_chart = (
                    alt.Chart(combined_df)
                    .mark_line(point=True, tooltip=True)
                    .encode(
                        x=f"{TIME_COL}:Q",
                        y=f"{TEMP_COL}:Q",
                        color='student:N',  # 학생별로 색상 구분
                        strokeDash='student:N' # 점선/실선 구분도 추가
                    )
                    .properties(height=500, title="학생별 그래프 비교")
                    .interactive()
                )
                st.altair_chart(comparison_chart, use_container_width=True)


