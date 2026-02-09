from supabase import create_client
import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

# 환경변수 가져오기 (Streamlit Secrets 우선, 없으면 환경변수)
def get_env_var(key):
    """환경변수를 Secrets 또는 .env에서 가져오기"""
    try:
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
        else:
            return os.getenv(key)
    except:
        return os.getenv(key)

SUPABASE_URL = get_env_var("SUPABASE_URL")
SUPABASE_KEY = get_env_var("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL 또는 SUPABASE_KEY가 설정되지 않았습니다.\n\n"
        "로컬 환경: .env 파일에 값 추가\n"
        "Streamlit Cloud: Manage app → Settings → Secrets에 다음 형식으로 추가:\n"
        'SUPABASE_URL = "your-url"\n'
        'SUPABASE_KEY = "your-key"'
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_users():
    """모든 사용자 조회"""
    response = supabase.table("users").select("*").order('id').execute()
    return response.data

def get_user(user_id):
    """특정 사용자 조회"""
    response = supabase.table("users").select("*").eq("id", user_id).execute()
    return response.data[0] if response.data else None

def add_user(user_data):
    """새 사용자 추가"""
    response = supabase.table("users").insert(user_data).execute()
    return response.data[0] if response.data else None

def update_user(user_id, user_data):
    """사용자 정보 수정"""
    response = supabase.table("users").update(user_data).eq("id", user_id).execute()
    return response.data[0] if response.data else None

def delete_user(user_id):
    """사용자 삭제"""
    response = supabase.table("users").delete().eq("id", user_id).execute()
    return response.data

def save_generation_history(user_id, filename, product_count):
    """생성 이력 저장"""
    supabase.table("bulk_generations").insert({
        "user_id": user_id,
        "file_name": filename,
        "product_count": product_count
    }).execute()
