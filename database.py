import json
import os
from datetime import datetime

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def ensure_data_files():
    """data 폴더와 json 파일이 없으면 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def load_json(file_path):
    """JSON 파일 읽기"""
    ensure_data_files()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json(file_path, data):
    """JSON 파일 저장"""
    ensure_data_files()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_users():
    """모든 사용자 조회"""
    users = load_json(USERS_FILE)
    users.sort(key=lambda x: x.get("id", 0))
    return users


def get_user(user_id):
    """특정 사용자 조회"""
    users = load_json(USERS_FILE)
    for user in users:
        if str(user.get("id")) == str(user_id):
            return user
    return None


def add_user(user_data):
    """새 사용자 추가"""
    users = load_json(USERS_FILE)

    next_id = max([u.get("id", 0) for u in users], default=0) + 1

    new_user = {
        "id": next_id,
        "name": user_data.get("name", ""),
        "google_sheet_id": user_data.get("google_sheet_id", ""),
        "image_domain": user_data.get("image_domain", ""),
        "image_url_pattern": user_data.get("image_url_pattern", "/{sku}.jpg"),
        "shop_code": user_data.get("shop_code", ""),
        "default_quantity": int(user_data.get("default_quantity", 999)),
        "default_description": user_data.get("default_description", ""),
        "shipping_profile_name": user_data.get("shipping_profile_name", ""),
        "return_profile_name": user_data.get("return_profile_name", ""),
        "payment_profile_name": user_data.get("payment_profile_name", "")
    }

    users.append(new_user)
    save_json(USERS_FILE, users)
    return new_user


def update_user(user_id, user_data):
    """사용자 정보 수정"""
    users = load_json(USERS_FILE)

    for i, user in enumerate(users):
        if str(user.get("id")) == str(user_id):
            updated_user = users[i].copy()
            updated_user.update(user_data)

            if "default_quantity" in updated_user:
                try:
                    updated_user["default_quantity"] = int(updated_user["default_quantity"])
                except Exception:
                    updated_user["default_quantity"] = 999

            users[i] = updated_user
            save_json(USERS_FILE, users)
            return users[i]

    return None


def delete_user(user_id):
    """사용자 삭제"""
    users = load_json(USERS_FILE)
    new_users = [user for user in users if str(user.get("id")) != str(user_id)]
    save_json(USERS_FILE, new_users)
    return True


def save_generation_history(user_id, filename, product_count):
    """생성 이력 저장"""
    history = load_json(HISTORY_FILE)

    next_id = max([h.get("id", 0) for h in history], default=0) + 1

    history.append({
        "id": next_id,
        "user_id": user_id,
        "file_name": filename,
        "product_count": int(product_count),
        "created_at": datetime.now().isoformat()
    })

    save_json(HISTORY_FILE, history)
    return True
