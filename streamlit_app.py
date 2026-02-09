import streamlit as st
import pandas as pd
from excel_generator import generate_ebay_excel
from database import get_users, get_user, add_user, update_user, delete_user
import io

# 페이지 설정
st.set_page_config(
    page_title="eBay Bulk Generator",
    layout="wide",
    page_icon="🛍️",
    initial_sidebar_state="collapsed"
)

# 커스텀 CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 1rem;
    }
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        padding: 1rem;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if 'show_settings' not in st.session_state:
    st.session_state.show_settings = False


# ===== 설정 모달 함수 =====
def show_settings_modal():
    """설정 팝업 표시"""

    st.markdown("## ⚙️ 사용자 프로필 설정")

    # 탭으로 구분
    tab1, tab2 = st.tabs(["👤 프로필 편집", "➕ 새 프로필 추가"])

    # === 탭 1: 기존 프로필 편집 ===
    with tab1:
        users = get_users()

        if not users:
            st.warning("등록된 사용자가 없습니다. '새 프로필 추가' 탭에서 추가하세요.")
        else:
            edit_user_options = {u["id"]: u["name"] for u in users}
            edit_user_id = st.selectbox(
                "편집할 사용자 선택",
                options=list(edit_user_options.keys()),
                format_func=lambda x: edit_user_options[x]
            )

            if edit_user_id:
                user = get_user(edit_user_id)

                with st.form("edit_user_form"):
                    st.markdown("#### 📝 기본 정보")
                    col1, col2 = st.columns(2)
                    with col1:
                        name = st.text_input("이름*", value=user.get('name', ''))
                    with col2:
                        google_sheet_id = st.text_input(
                            "구글시트 ID*",
                            value=user.get('google_sheet_id', ''),
                            help="구글시트 URL의 /d/[이 부분]/edit"
                        )

                    st.markdown("#### 🖼️ 이미지 설정")
                    col3, col4 = st.columns(2)
                    with col3:
                        image_domain = st.text_input(
                            "이미지 도메인*",
                            value=user.get('image_domain', ''),
                            placeholder="https://shopeept.com"
                        )
                    with col4:
                        image_url_pattern = st.text_input(
                            "이미지 URL 패턴",
                            value=user.get('image_url_pattern', '/{sku}.jpg'),
                            help="{sku}는 상품 SKU로 자동 치환됩니다"
                        )

                    st.markdown("#### ⚙️ 기본값")
                    col5, col6 = st.columns(2)
                    with col5:
                        default_quantity = st.number_input(
                            "기본 재고",
                            value=user.get('default_quantity', 999),
                            min_value=1
                        )
                    with col6:
                        default_description = st.text_area(
                            "기본 상품 설명",
                            value=user.get('default_description', ''),
                            height=100
                        )

                    st.markdown("#### 🏪 이베이 정책 프로필")
                    shipping_profile_name = st.text_input(
                        "배송 프로필*",
                        value=user.get('shipping_profile_name', ''),
                        help="예: STANDARD - (ID: 196131623026)"
                    )
                    return_profile_name = st.text_input(
                        "반품 프로필*",
                        value=user.get('return_profile_name', ''),
                        help="예: 30 Days Return - (ID: 227722653026)"
                    )
                    payment_profile_name = st.text_input(
                        "결제 프로필*",
                        value=user.get('payment_profile_name', ''),
                        help="예: eBay Managed Payments ... - (ID: 220234315026)"
                    )

                    col_btn1, col_btn2, col_btn3 = st.columns(3)

                    with col_btn1:
                        submitted = st.form_submit_button("💾 저장", use_container_width=True)

                    with col_btn2:
                        if st.form_submit_button("🗑️ 삭제", use_container_width=True):
                            try:
                                delete_user(edit_user_id)
                                st.success(f"'{user['name']}' 사용자가 삭제되었습니다.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"삭제 실패: {str(e)}")

                    with col_btn3:
                        if st.form_submit_button("❌ 취소", use_container_width=True):
                            st.session_state.show_settings = False
                            st.rerun()

                    if submitted:
                        try:
                            update_data = {
                                "name": name,
                                "google_sheet_id": google_sheet_id,
                                "image_domain": image_domain,
                                "image_url_pattern": image_url_pattern,
                                "default_quantity": default_quantity,
                                "default_description": default_description,
                                "shipping_profile_name": shipping_profile_name,
                                "return_profile_name": return_profile_name,
                                "payment_profile_name": payment_profile_name
                            }

                            update_user(edit_user_id, update_data)
                            st.success("✅ 저장되었습니다!")
                            st.session_state.show_settings = False
                            st.rerun()

                        except Exception as e:
                            st.error(f"저장 실패: {str(e)}")

    # === 탭 2: 새 프로필 추가 ===
    with tab2:
        with st.form("add_user_form"):
            st.markdown("#### 📝 기본 정보")
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("이름*", placeholder="영희")
            with col2:
                new_google_sheet_id = st.text_input(
                    "구글시트 ID*",
                    placeholder="1abc...xyz",
                    help="구글시트 URL의 /d/[이 부분]/edit"
                )

            st.markdown("#### 🖼️ 이미지 설정")
            col3, col4 = st.columns(2)
            with col3:
                new_image_domain = st.text_input(
                    "이미지 도메인*",
                    placeholder="https://unisiashop.com"
                )
            with col4:
                new_image_url_pattern = st.text_input(
                    "이미지 URL 패턴",
                    value="/{sku}.jpg",
                    help="{sku}는 상품 SKU로 자동 치환됩니다"
                )

            st.markdown("#### ⚙️ 기본값")
            col5, col6 = st.columns(2)
            with col5:
                new_default_quantity = st.number_input("기본 재고", value=999, min_value=1)
            with col6:
                new_default_description = st.text_area(
                    "기본 상품 설명",
                    value="Brand new authentic Korean product. Fast shipping worldwide.",
                    height=100
                )

            st.markdown("#### 🏪 이베이 정책 프로필")
            new_shipping_profile = st.text_input(
                "배송 프로필*",
                placeholder="STANDARD - (ID: 196131623026)"
            )
            new_return_profile = st.text_input(
                "반품 프로필*",
                placeholder="30 Days Return - (ID: 227722653026)"
            )
            new_payment_profile = st.text_input(
                "결제 프로필*",
                placeholder="eBay Managed Payments ... - (ID: 220234315026)"
            )

            col_add1, col_add2 = st.columns(2)

            with col_add1:
                add_submitted = st.form_submit_button("➕ 추가", use_container_width=True, type="primary")

            with col_add2:
                if st.form_submit_button("❌ 취소", use_container_width=True):
                    st.session_state.show_settings = False
                    st.rerun()

            if add_submitted:
                if not all([new_name, new_google_sheet_id, new_image_domain,
                            new_shipping_profile, new_return_profile, new_payment_profile]):
                    st.error("필수 항목(*)을 모두 입력해주세요.")
                else:
                    try:
                        insert_data = {
                            "name": new_name,
                            "google_sheet_id": new_google_sheet_id,
                            "image_domain": new_image_domain,
                            "image_url_pattern": new_image_url_pattern,
                            "default_quantity": new_default_quantity,
                            "default_description": new_default_description,
                            "shipping_profile_name": new_shipping_profile,
                            "return_profile_name": new_return_profile,
                            "payment_profile_name": new_payment_profile
                        }

                        add_user(insert_data)
                        st.success(f"✅ '{new_name}' 사용자가 추가되었습니다!")
                        st.session_state.show_settings = False
                        st.rerun()

                    except Exception as e:
                        st.error(f"추가 실패: {str(e)}")


# ===== 메인 화면 =====

# 헤더 - 타이틀과 설정 버튼
col_title, col_settings = st.columns([8, 1])

with col_title:
    st.title("🛍️ eBay 벌크 리스팅 생성기")
    st.caption("구글시트 → 이베이 Excel 파일 자동 변환 | v2.0")

with col_settings:
    st.write("")  # 공백으로 수직 정렬
    if st.button("⚙️", help="설정 및 사용자 관리", use_container_width=True):
        st.session_state.show_settings = True
        st.rerun()

st.markdown("---")

# 설정 모달 표시
if st.session_state.show_settings:
    show_settings_modal()
    st.stop()  # 설정 화면이 열려있으면 메인 화면 렌더링 중지

# 사용자 선택
st.subheader("1️⃣ 사용자 선택")
users = get_users()

if not users:
    st.error("🚨 등록된 사용자가 없습니다. 우측 상단 ⚙️ 버튼을 눌러 사용자를 추가하세요.")
    st.stop()

user_options = {u["id"]: f"{u['name']} ({u.get('image_domain', '도메인 미설정')[:30]}...)" for u in users}
selected_user_id = st.selectbox(
    "사용할 프로필을 선택하세요",
    options=list(user_options.keys()),
    format_func=lambda x: user_options[x],
    label_visibility="collapsed"
)

selected_user = get_user(selected_user_id)

# 선택된 사용자 정보 표시 (간략화)
with st.expander("ℹ️ 선택된 사용자 정보", expanded=False):
    st.json({
        "이름": selected_user['name'],
        "구글시트 ID": selected_user.get('google_sheet_id', '미설정')[:40] + "...",
        "이미지 도메인": selected_user.get('image_domain', '미설정')
    })

st.markdown("---")

# 메인 기능: Excel 생성 (깔끔한 버전)
st.subheader("2️⃣ 이베이 Excel 생성")

st.info("💡 **워크플로우**: 구글시트 Bulk 탭과 CAT 탭 데이터를 자동으로 읽어와서 Excel 파일을 생성합니다.")

if st.button("🚀 Excel 생성 및 다운로드", type="primary", use_container_width=True):
    try:
        with st.spinner("🔄 처리 중... (구글시트 연결 → 데이터 검증 → 베리에이션 처리 → Excel 생성)"):
            excel_data, filename, errors = generate_ebay_excel(selected_user_id)

            # 간단한 성공 메시지
            st.success(f"✅ 생성 완료: {filename}")

            # 검증 경고 표시 (필요한 경우만)
            if errors:
                with st.expander(f"⚠️ {len(errors)}개 검증 경고", expanded=len(errors) <= 3):
                    for error in errors[:10]:
                        st.warning(error)
                    if len(errors) > 10:
                        st.info(f"... 외 {len(errors) - 10}개 추가 경고")

            # 결과 통계 (핵심 정보만)
            excel_data_copy = excel_data.getvalue()
            df_result = pd.read_excel(io.BytesIO(excel_data_copy), dtype=str)

            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Total", len(df_result))
            col_r2.metric("PSKU", len(df_result[df_result.iloc[:, 0] == 'Add']))
            col_r3.metric("SKU", len(df_result[df_result.iloc[:, 0].isna() | (df_result.iloc[:, 0] == '')]))

            # 다운로드 버튼 (가장 중요!)
            st.download_button(
                label="💾 이베이 File Exchange 업로드용 Excel 다운로드",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

            # 미리보기는 선택사항으로 (접혀있음)
            with st.expander("👀 생성된 파일 미리보기 (선택사항)", expanded=False):
                st.dataframe(df_result.head(15), use_container_width=True, height=400)

                # 베리에이션 검증 표시
                variation_groups = df_result[df_result.iloc[:, 5] == 'Variation'] if len(
                    df_result.columns) > 5 else pd.DataFrame()
                if len(variation_groups) > 0:
                    st.success(f"✅ {len(variation_groups)}개 베리에이션 SKU 확인")

            # st.balloons() 제거됨 - 풍선 효과 없음

    except Exception as e:
        st.error(f"❌ 오류 발생: {str(e)}")

        # 상세 오류 정보 및 해결 방법
        with st.expander("🔧 오류 해결 가이드"):
            st.exception(e)

            error_str = str(e)
            if "401" in error_str or "Unauthorized" in error_str:
                st.markdown("""
                ### 💡 401 Unauthorized 해결 방법:
                1. Google Sheets API 활성화 확인
                2. 서비스 계정 이메일 확인: `cat service_account.json | grep client_email`
                3. 구글시트에 서비스 계정 이메일을 뷰어 권한으로 공유
                """)

            elif "403" in error_str or "Forbidden" in error_str:
                st.markdown("""
                ### 💡 403 Forbidden 해결 방법:
                - 구글시트에 서비스 계정 이메일이 공유되지 않았습니다
                - 구글시트 → 공유 → 서비스 계정 이메일 추가 (뷰어 권한)
                """)

# 하단 가이드
st.markdown("---")
st.caption("🎯 **간단 워크플로우**: 사용자 선택 → Excel 생성 → 다운로드 → 이베이 File Exchange 업로드")
