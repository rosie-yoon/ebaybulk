from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

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
