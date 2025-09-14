# app.py — 서술형 평가(3문항: 2-1/2-2 포함) · 성취수준 채점(A–D) · pr.DAT3 저장
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, re, json, textwrap
from typing import Dict, Any, List, Tuple, Optional

import streamlit as st
import mysql.connector
from mysql.connector import Error as MySQLError
from openai import OpenAI

# ───────────────────────── 페이지/모델 ─────────────────────────
st.set_page_config(page_title="서술형 평가 — 상태 변화와 열에너지", page_icon="🧪", layout="wide")
st.title("🧪 서술형 평가 — 상태 변화와 열에너지")

OPENAI_MODEL = st.secrets.get("OPENAI_MODEL", "gpt-5")
if "OPENAI_API_KEY" in st.secrets and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

def _compile_id_regex() -> re.Pattern:
    pattern = st.secrets.get("ID_REGEX", r"^\d{5,10}$")
    try: return re.compile(pattern)
    except re.error: return re.compile(r"^\d{5,10}$")
ID_RE = _compile_id_regex()

# ───────────────────────── MySQL 연결 ─────────────────────────
@st.cache_resource(show_spinner=False)
def get_mysql_conn():
    cfg = st.secrets.get("connections", {}).get("mysql", {})
    return mysql.connector.connect(
        host=cfg.get("host"),
        port=cfg.get("port", 3306),
        database=cfg.get("database", "pr"),
        user=cfg.get("user"),
        password=cfg.get("password"),
        autocommit=True,
    )

def live_conn():
    conn = get_mysql_conn()
    if not conn.is_connected():
        conn.reconnect(attempts=3, delay=1)
    return conn

def assert_table_exists():
    try:
        conn = live_conn()
        cur = conn.cursor(buffered=True)
        cur.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
        """, (conn.database or "pr", "DAT3"))
        if cur.fetchone()[0] == 0:
            st.error("DAT3 테이블이 존재하지 않습니다. 워크벤치에서 pr.DAT3를 생성해 주세요.")
            st.stop()
        cur.close()
    except MySQLError as e:
        st.error(f"[DB 점검 실패] {e}")
        st.stop()

assert_table_exists()

def insert_row(row: Dict[str, Any]) -> bool:
    try:
        conn = live_conn()
        cur = conn.cursor(buffered=True)
        cur.execute("""
            INSERT INTO DAT3
            (id, answer1, feedback1, answer2, feedback2, answer3, feedback3, answer4, feedback4, opinion1)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            row.get("id"),
            row.get("answer1"), row.get("feedback1"),
            row.get("answer2"), row.get("feedback2"),
            row.get("answer3"), row.get("feedback3"),
            row.get("answer4"), row.get("feedback4"),
            row.get("opinion1", ""),
        ))
        cur.close()
        return True
    except MySQLError as e:
        st.error(f"[DB] 저장 실패: {e}")
        return False

def _has_time_column(conn) -> bool:
    cur = conn.cursor(buffered=True)
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s AND column_name='time'
    """, (conn.database or "pr", "DAT3"))
    has = cur.fetchone()[0] > 0
    cur.close()
    return has

def update_latest_opinion(student_id: str, opinion: str) -> bool:
    """해당 id의 최신 1건을 우선, 불가 시 1건 업데이트로 폴백"""
    try:
        conn = live_conn()
        cur = conn.cursor(buffered=True)
        if _has_time_column(conn):
            sql = "UPDATE DAT3 SET opinion1=%s WHERE id=%s ORDER BY time DESC LIMIT 1"
            params = (opinion, student_id)
        else:
            sql = "UPDATE DAT3 SET opinion1=%s WHERE id=%s LIMIT 1"
            params = (opinion, student_id)
        cur.execute(sql, params)
        cur.close()
        return True
    except MySQLError as e:
        st.error(f"[DB] 의견 저장 실패: {e}")
        return False

# ───────────────────────── 유틸/이미지 ─────────────────────────
def text_area_with_counter(label: str, key: str, max_chars: int, height: int = 160, placeholder: str = "") -> str:
    left, right = st.columns([5, 1])
    with left: st.markdown(f"**{label}**")
    val = st.text_area("", key=key, height=height, placeholder=placeholder,
                       max_chars=max_chars, label_visibility="collapsed")
    with right: st.caption(f"{len(val)}/{max_chars}")
    return val

def validate_answer(ans: str, max_chars: int, max_newlines: int = 3) -> Tuple[bool, Optional[str]]:
    if len(ans.strip()) == 0: return False, "답안을 입력해 주세요."
    if len(ans) > max_chars:  return False, f"글자 수 제한 초과({len(ans)}/{max_chars}자)."
    if ans.count("\n") > max_newlines: return False, f"줄바꿈은 최대 {max_newlines}회까지만 허용됩니다."
    return True, None

def windows25(s: str) -> set:
    s = re.sub(r"\s+", " ", s.strip()); out=set()
    if len(s) < 25: return out
    for i in range(len(s)-24): out.add(s[i:i+25])
    return out

def find_cross_paste(wins: Dict[str, set]) -> List[Tuple[str, str]]:
    hits=[]; keys=list(wins.keys())
    for i in range(len(keys)):
        for j in range(i+1, len(keys)):
            a,b=keys[i],keys[j]
            if wins[a] & wins[b]: hits.append((a,b))
    return hits

def _img_candidates(name: str) -> List[str]:
    # 3번 문항은 image3.png만 사용(보조 후보 비활성화)
    if name == "image3.png":
        return ["image3.png", "image/image3.png", "./image/image3.png"]
    # 일반 규칙: 루트 또는 image/ 폴더 탐색
    return [name, f"image/{name}", f"./image/{name}"]

def show_img_safe(name: str, caption: str):
    shown=False
    for p in _img_candidates(name):
        try:
            st.image(p, caption=caption, use_container_width=True); shown=True; break
        except Exception: continue
    if not shown: st.info(f"{name} 이미지를 찾을 수 없습니다.")

# ───────────────────────── 문제 안내/제한 ─────────────────────────
GUIDE_Q1   = "3–4문장, 150–350자(최대 350자). 두 가지로 분류 + 분류 기준을 명확히."
GUIDE_Q2_1 = "2–4문장, 100–300자(최대 300자). 상태/입자(종류·개수·거리·배열) 반영."
GUIDE_Q2_2 = "2–4문장, 100–300자(최대 300자). 액체→고체(응고) + 열에너지 ‘방출’."
GUIDE_Q3   = "3–5문장, 150–350자(최대 350자). 캠프장에서 음료수 캔을 시원하게 하는 아이디어 2(각 항목에 상태 전/후·열 출입·주위 온도 포함)."
LIMITS     = {"q1": 350, "q2a": 300, "q2b": 300, "q3": 350}

# ───────────────────────── GPT 채점 ─────────────────────────
@st.cache_resource(show_spinner=False)
def get_openai_client(): return OpenAI()

def build_messages(payload: Dict[str,str]) -> Tuple[str,str]:
    system = (
        "당신은 중학교 과학 서술형 평가 ‘채점 보조교사’입니다. "
        "학생 답안을 성취수준(A/B/C/D)으로만 평가하고 간결한 피드백을 제공합니다. "
        "출력은 반드시 JSON 한 개로만 작성하세요."
    )
    # Q3의 요구를 '캠프장에서 음료수를 시원하게 하는 아이디어 2가지'로 단순화(각 항목 3요소 필수)
    rubric = textwrap.dedent("""
    [채점 운영 원칙]
    - 등급만 사용(A/B/C/D), 점수 없음. 예시 답안/채점기준을 우선 적용.
    - 과학 용어는 교과 수준(‘열에너지 흡수/방출’). ‘잠열’ 등은 필수 아님(있어도 판정은 흡수/방출 정확성 기준).
    - 중복 아이디어는 1건으로만 인정. 상충 진술(예: 액→고면서 흡수)은 감점.
    - 출력은 반드시 JSON 하나.

    [문항별 체크리스트와 등급 매핑]
    ■ Q1 (분류와 기준 진술)
      체크(3):
        1) 분류쌍 정확: {(가,다)=흡수}, {(나,라)=방출} (순서 자유, 쌍 구성 정확)
        2) 열에너지 출입 명시: ‘흡수/방출’ 용어로 두 쌍의 열 출입을 명확히 진술
        3) 기준문장: “열에너지의 출입에 따라 분류”와 같은 분류 기준 문장 존재(인과 일치)
      등급:
        - A: 1,2,3 모두 충족(오류·모순 없음)
        - B: 1 충족 + (2 또는 3 중 1개만 충족) / 표현이 다소 모호하나 방향성은 정확
        - C: 1만 충족(2,3 부실) 또는 1이 부분만 정확(한 쌍만 맞음)
        - D: 분류 틀림(방향 반대·쌍 오류) 또는 열 출입 진술이 모순

    ■ Q2-1 (액→고, 입자 관점 5요소)
      체크(5):
        a) 상태: 액체→고체(응고 과정)
        b) 입자 종류: 불변
        c) 입자 개수: 불변
        d) 입자 사이 거리: 감소
        e) 입자 배열: 규칙적(더 질서정연)
      등급:
        - A: 5/5
        - B: 3–4/5
        - C: 1–2/5
        - D: 0/5 또는 반대 진술(예: 고→액, 거리 증가 등)

    ■ Q2-2 (응고 + 방출)
      체크(2):
        a) 상태 변화: 액체→고체(‘응고’ 포함 가능)
        b) 열에너지: 주위로 ‘방출’
      등급:
        - A: 2/2
        - B: a만 정확하고 b가 모호/불완전
        - C: 일부 오류 또는 불완전(방출 대신 감소 등 애매)
        - D: 방향 반대(흡수) 또는 상태 변화 오기

    ■ Q3 (캠프장에서 음료수 캔을 시원하게 하는 아이디어 2)
      요구: 아이디어 2가지 제시.
      각 아이디어의 필수 3요소: (i) 상태 전/후, (ii) 열에너지 출입(흡수/방출), (iii) 주위 온도 변화
      카운트:
        - camp_ok: 3요소를 모두 갖춘 캠프 아이디어 수(0–2)
      등급:
        - A: camp_ok=2, 과학적 오류 없음, 글 흐름 양호
        - B: camp_ok=1(정확) 또는 2이나 경미한 누락/모호 표현
        - C: camp_ok=0이지만 부분 요소는 일부 언급(불완전) 또는 오개념 일부
        - D: camp_ok=0이며 과학적 오류/요구 불충족 심함

    [출력 JSON 스키마]
    {
      "q1":   {"level":"A|B|C|D","feedback":"...", "detected":{"grouping_correct":bool,"mentions_inout":bool,"criterion_sentence":bool}},
      "q2_1": {"level":"A|B|C|D","feedback":"...", "detected":{"state_liq_to_sol":bool,"type_const":bool,"count_const":bool,"distance_decrease":bool,"arrangement_regular":bool}},
      "q2_2": {"level":"A|B|C|D","feedback":"...", "detected":{"state_liq_to_sol":bool,"heat_release":bool}},
      "q3":   {"level":"A|B|C|D","feedback":"...", "detected":{"camp_ok":0-2}}
    }

    [피드백 작성]
    - 각 문항 2–3문장, 간결한 한국어. 요구 조건 중 부족한 요소를 직접 지적하고 보완 방향 제시.
    """).strip()

    user = {
        "q1_answer":   payload.get("q1",""),
        "q2_1_answer": payload.get("q2_1",""),
        "q2_2_answer": payload.get("q2_2",""),
        "q3_answer":   payload.get("q3",""),
    }
    return system, rubric + "\n\n" + json.dumps(user, ensure_ascii=False)

def _parse_json_strict(txt: str) -> Dict[str, Any]:
    try: return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}\s*$", txt, flags=re.S)
        if m: return json.loads(m.group(0))
        raise

def grade_all(q1: str, q2_1: str, q2_2: str, q3: str) -> Dict[str, Any]:
    client = get_openai_client()
    system, user_msg = build_messages({"q1": q1, "q2_1": q2_1, "q2_2": q2_2, "q3": q3})
    # 1) Responses API
    try:
        if getattr(client, "responses", None) is not None:
            resp = client.responses.create(
                model=OPENAI_MODEL,
                input=[{"role":"system","content":system},
                       {"role":"user","content":user_msg}],
                response_format={"type":"json_object"},
                max_output_tokens=600,
            )
            txt = getattr(resp, "output_text", None)
            if not txt and hasattr(resp, "output") and resp.output:
                parts=[]
                for o in resp.output:
                    if hasattr(o,"content"):
                        for c in o.content:
                            if getattr(c,"type","")=="output_text" and getattr(c,"text",""):
                                parts.append(c.text)
                txt="".join(parts) if parts else ""
            if not txt: raise RuntimeError("빈 응답")
        else:
            raise AttributeError("Responses API not available")
    except Exception:
        # 2) Chat Completions (토큰 파라미터 없이)
        try:
            chat = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user_msg}],
                response_format={"type":"json_object"},
            )
            txt = chat.choices[0].message.content
        except Exception:
            chat = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user_msg}],
            )
            txt = chat.choices[0].message.content

    try:
        data = _parse_json_strict(txt)
        for key in ("q1","q2_1","q2_2","q3"):
            item = data.get(key, {}) if isinstance(data, dict) else {}
            lv = str(item.get("level","D")).upper()
            if lv not in ("A","B","C","D"): lv="D"
            item["level"]=lv; item.setdefault("feedback",""); item.setdefault("detected",{})
            data[key]=item
        return data
    except Exception as e:
        st.error(f"[채점] 응답 파싱 실패: {e}")
        return {k:{"level":"D","feedback":"시스템 오류로 간단 채점.","detected":{}} for k in ("q1","q2_1","q2_2","q3")}

# ───────────────────────── 입력 폼 ─────────────────────────
st.subheader("① 기본 정보")
col_id, _ = st.columns([1.2, 2])
with col_id:
    student_id = st.text_input("학번 (예: 10130)", max_chars=10, placeholder="예: 10130")

st.divider()
st.subheader("② 문항")

# 문항 1
c1, c2 = st.columns([1,1])
with c1:
    st.markdown("**[1번 문항]**\n\n "
    "(가)~(라)의 상태 변화를 열에너지와 관련된 분류 기준을 세워 **두 가지로 분류**하고, 그 **분류 기준**을 제시하시오.")
    st.caption(GUIDE_Q1)
with c2:
    show_img_safe("image1.png", "[1번] 상태 변화 예시")
ans1 = text_area_with_counter("답안 — [1번]", "ans1", LIMITS["q1"], height=160,
                              placeholder="예) 분류: (가)(다), (나)(라) / 분류 기준: …")

# 문항 2
st.markdown("---")
c21, c22 = st.columns([1,1])
with c21:
    st.markdown("**[2번 문항]**\n\n"
    " 다음은 2001년 유네스코 세계기록유산으로 등재된 직지심체요철을 만드는 방법을 나타낸 것이다.\n\n"
    " 금속 활자 제작: 1) 밀랍 활자 → 2) 거푸집 → 3) 청동 쇳물 붓기 → 4) 깨고 다듬기")
with c22:
    show_img_safe("image2.png", "[2번] 금속 활자 제작")
st.markdown("**[2-1]**\n\n" 
" 3단계 쇳물의 상태 변화 과정을 <조건>에 맞게 서술하시오.\n\n"
"<조건>\n\n"
"- 상태 변화와 입자 관점(종류/개수/거리/배열) 포함\n"
)
st.caption(GUIDE_Q2_1)
ans2a = text_area_with_counter("답안 — [2-1번]", "ans2a", LIMITS["q2a"], height=150,
                               placeholder="예) 액체→고체, 입자 종류/개수 불변, 거리↓, 배열 규칙적 …")
st.markdown("**[2-2]** 4단계에서 쇳물이 굳을 때, 상태 변화와 열에너지 출입을 연관지어 설명하시오.")
st.caption(GUIDE_Q2_2)
ans2b = text_area_with_counter("답안 — [2-2번]", "ans2b", LIMITS["q2b"], height=140,
                               placeholder="예) 액체→고체(응고), 열에너지를 주위로 방출 …")

# 문항 3
st.markdown("---")
c31, c32 = st.columns([1,1])
with c31:
    st.markdown("**[3번 문항]**\n\n" 
    "상태 변화에서 출입하는 열에너지가 **일상생활에 이용되는 사례**를 <조건>에 맞게 쓰시오.\n\n"
    "<조건>\n\n"
    "- 캠프장에서 음료수 캔을 시원하게 하는 아이디어 2가지\n\n"
    "- 이때, 각 항목에 **상태 전후 / 열에너지 출입 / 주위 온도 변화** 포함\n\n"
    )
    st.caption(GUIDE_Q3)
with c32:
    # 3번 문항은 image3.png 하나만 표시
    show_img_safe("image3.png", "[3번] 예시 그림")
ans3 = text_area_with_counter("답안 — [3번]", "ans3", LIMITS["q3"], height=220,
                              placeholder="예) 물에 적신 수건으로 감싸 부채질: 액→기, 열 흡수, 주위 온도↓ / 항아리식 젖은 모래 증발 등")

# ───────────────────────── 검증 ─────────────────────────
def validate_all() -> bool:
    if not ID_RE.fullmatch((student_id or "").strip()):
        st.error("학번 형식이 올바르지 않습니다. 예: 10130"); return False
    ok, msg = validate_answer(ans1, LIMITS["q1"])
    if not ok: st.error(f"[1번] {msg}"); return False
    for label, ans, lim in (("[2-1]",ans2a,LIMITS["q2a"]), ("[2-2]",ans2b,LIMITS["q2b"]), ("[3번]",ans3,LIMITS["q3"])):
        ok, msg = validate_answer(ans, lim)
        if not ok: st.error(f"{label} {msg}"); return False
    wins={"1번":windows25(ans1),"2-1":windows25(ans2a),"2-2":windows25(ans2b),"3번":windows25(ans3)}
    dup=find_cross_paste(wins)
    if dup:
        st.error("복사/붙여넣기 의심: " + ", ".join([f"{a}↔{b}" for a,b in dup]) +
                 " 에서 25자 이상 동일 구간이 발견되었습니다. 각 문항을 독립적으로 서술하세요.")
        return False
    return True

# ───────────────────────── 제출/채점 ─────────────────────────
st.markdown("---")
col_btn1, col_btn2 = st.columns([1.2, 3])
with col_btn1:
    submit = st.button("채점 받기", type="primary", key="btn_submit")
with col_btn2:
    st.caption("제출 시 한 번의 GPT 호출로 4칸(1, 2-1, 2-2, 3)을 동시 채점합니다.")

# 세션 플래그 초기화
if "ready_for_opinion" not in st.session_state:
    st.session_state["ready_for_opinion"] = False
if "opinion_target_id" not in st.session_state:
    st.session_state["opinion_target_id"] = ""

if submit:
    if not validate_all():
        st.stop()
    with st.spinner("채점 중…"):
        result = grade_all(ans1, ans2a, ans2b, ans3)

    st.success("채점이 완료되었습니다. 아래 성취수준과 피드백을 확인하세요.")
    tab1, tab2, tab3, tab4 = st.tabs(["문항 1", "문항 2-1", "문항 2-2", "문항 3"])
    mapping = {
        "문항 1":  result.get("q1", {}),
        "문항 2-1":result.get("q2_1", {}),
        "문항 2-2":result.get("q2_2", {}),
        "문항 3":  result.get("q3", {}),
    }
    for t, key in zip((tab1, tab2, tab3, tab4), ("q1","q2_1","q2_2","q3")):
        with t:
            item = result.get(key, {})
            st.markdown(f"**성취수준: {item.get('level','D')}**")
            st.write(item.get("feedback",""))

    fb1=json.dumps(mapping["문항 1"],  ensure_ascii=False)
    fb2=json.dumps(mapping["문항 2-1"],ensure_ascii=False)
    fb3=json.dumps(mapping["문항 2-2"],ensure_ascii=False)
    fb4=json.dumps(mapping["문항 3"],  ensure_ascii=False)

    saved = insert_row({
        "id": (student_id or "").strip(),
        "answer1": ans1, "feedback1": fb1,
        "answer2": ans2a, "feedback2": fb2,
        "answer3": ans2b, "feedback3": fb3,
        "answer4": ans3,  "feedback4": fb4,
        "opinion1": "",
    })

    if saved:
        # ▶ 의견 UI를 rerun 후에도 계속 보이도록 세션 플래그 설정
        st.session_state["ready_for_opinion"] = True
        st.session_state["opinion_target_id"] = (student_id or "").strip()
        st.info("제출/저장이 완료되었습니다. 이어서 ‘한 가지 의견’을 작성하면 최근 제출 내역에 반영됩니다.")

# ───────────────────────── 의견 입력(항상 세션 플래그로 표시) ─────────────────────────
if st.session_state.get("ready_for_opinion"):
    st.markdown("### ③ 한 가지 의견 (필수)")
    new_opinion = st.text_area(
        "의견을 입력하세요(최대 300자)",
        key="opinion_after", max_chars=300, height=80,
        placeholder="예) GPT 피드백 내용/채점 오류/동료 피드백/기타 등 자유롭게 작성 가능합니다."
    )
    if st.button("의견 제출", type="secondary", key="btn_opinion"):
        if (new_opinion or "").strip():
            ok = update_latest_opinion(st.session_state.get("opinion_target_id",""), (new_opinion or "").strip())
            if ok:
                st.success("의견이 저장되었습니다.")
        else:
            st.warning("의견이 비어 있습니다.")
