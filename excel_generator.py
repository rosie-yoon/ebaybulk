import streamlit as st
import pandas as pd
import re
import os
from database import get_user, save_generation_history
import io
import gspread
from google.oauth2.service_account import Credentials

# Google Sheets API 설정
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


def get_google_sheets_client():
    """Google Sheets API 클라이언트 생성 - 로컬/클라우드 호환"""
    try:
        # 1) 먼저 로컬 파일이 있으면 그걸 우선 사용
        if os.path.exists("service_account.json"):
            creds = Credentials.from_service_account_file(
                "service_account.json",
                scopes=SCOPES
            )
            return gspread.authorize(creds)

        # 2) 로컬 파일이 없으면 Streamlit secrets 사용 시도
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])

            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=SCOPES
            )
            return gspread.authorize(creds)

        except Exception:
            raise Exception(
                "service_account.json 파일이 없고, Streamlit secrets의 "
                "'gcp_service_account' 설정도 없습니다."
            )

    except Exception as e:
        raise Exception(f"Google Sheets API 인증 실패: {str(e)}")


def read_bulk_and_cat_tabs(sheet_id):
    """Bulk 탭과 CAT 탭 읽기 - INDEX 컬럼 포함"""
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(sheet_id)

        # Bulk 탭 읽기
        bulk_worksheet = spreadsheet.worksheet('Bulk')
        bulk_data = bulk_worksheet.get_all_values()

        if bulk_data:
            bulk_df = pd.DataFrame(bulk_data[1:], columns=bulk_data[0])
            bulk_df.columns = bulk_df.columns.str.strip()
        else:
            bulk_df = pd.DataFrame()

        # CAT 탭 읽기
        try:
            cat_worksheet = spreadsheet.worksheet('CAT')
            cat_data = cat_worksheet.get_all_values()

            category_map = {}
            for row in cat_data:
                if len(row) >= 2 and row[1].strip():
                    category_path = row[0].strip()
                    category_id = row[1].strip()
                    condition_id = row[2].strip() if len(row) >= 3 else "1000-New"

                    category_map[category_id] = {
                        'path': category_path,
                        'condition': condition_id
                    }

        except gspread.WorksheetNotFound:
            print("[경고] CAT 탭을 찾을 수 없습니다.")
            category_map = {}

        return bulk_df, category_map

    except Exception as e:
        raise Exception(f"구글시트 읽기 실패: {str(e)}")


def generate_ebay_excel(user_id):
    """이베이 벌크 Excel 생성 - INDEX 기반 다중 이미지 지원"""
    user = get_user(user_id)
    if not user:
        raise Exception("사용자 정보를 찾을 수 없습니다.")

    print(f"[시작] 사용자: {user['name']}")

    # 1. 데이터 로드
    bulk_df, category_map = read_bulk_and_cat_tabs(user['google_sheet_id'])
    print(f"[로드] Bulk: {len(bulk_df)}개 행, CAT: {len(category_map)}개 카테고리")

    # 2. Create=TRUE 필터링
    if 'Create' in bulk_df.columns:
        bulk_df = bulk_df[bulk_df['Create'].astype(str).str.upper() == 'TRUE']
        print(f"[필터링] Create=TRUE: {len(bulk_df)}개 행")

    if len(bulk_df) == 0:
        raise Exception("Create=TRUE인 데이터가 없습니다.")

    # 3. 베리에이션 변환
    ebay_rows = convert_to_ebay_variations(bulk_df, category_map, user)
    print(f"[변환] {len(ebay_rows)}개 이베이 행 생성")

    # 4. DataFrame 생성 및 컬럼 정렬
    ebay_df = pd.DataFrame(ebay_rows)
    ebay_columns = get_ebay_column_order()
    ebay_df = ebay_df.reindex(columns=ebay_columns, fill_value='')

    # 5. Excel 파일 생성
    output = io.BytesIO()
    safe_name = re.sub(r'[^a-zA-Z0-9가-힣_-]', '_', user['name'])
    filename = f"ebay_bulk_{safe_name}.xlsx"

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ebay_df.to_excel(writer, index=False, sheet_name='eBay Bulk Upload')

        worksheet = writer.sheets['eBay Bulk Upload']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if cell.value is not None and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)

    # 6. 데이터 검증
    validation_errors = validate_ebay_data(ebay_df, category_map)

    # 7. 이력 저장
    save_generation_history(user_id, filename, len(ebay_df))

    return output, filename, validation_errors


def convert_to_ebay_variations(bulk_df, category_map, user):
    """Bulk 데이터를 이베이 베리에이션 형식으로 변환"""
    ebay_rows = []

    grouped = bulk_df.groupby('PSKU', sort=False)

    for psku, group in grouped:
        psku = str(psku).strip()
        if not psku:
            continue

        first_row = group.iloc[0]
        product_name = str(first_row.get('Product Name', '')).strip()
        category_id = str(first_row.get('Categoery ID', '')).strip()
        category_name = str(first_row.get('Categoery', '')).strip()
        brand = str(first_row.get('BRAND', '')).strip()
        index_value = str(first_row.get('INDEX', '0')).strip()

        cat_info = category_map.get(category_id, {})

        if not category_name and cat_info:
            category_name = cat_info.get('path', '')

        condition_id = cat_info.get('condition', '1000-New')

        all_options = []
        for _, child in group.iterrows():
            option = str(child.get('OPTION', '')).strip()
            if option:
                all_options.append(option)

        relationship_details = f"OPTIONS={';'.join(all_options)}" if all_options else ''

        parent_row = create_parent_row(
            psku=psku,
            product_name=product_name,
            category_id=category_id,
            category_name=category_name,
            brand=brand,
            condition_id=condition_id,
            relationship_details=relationship_details,
            first_price=clean_price(first_row.get('PRICE', '0')),
            index_value=index_value,
            user=user
        )
        ebay_rows.append(parent_row)

        for _, child_data in group.iterrows():
            child_row = create_child_row(child_data, user)
            ebay_rows.append(child_row)

    return ebay_rows


def create_parent_row(psku, product_name, category_id, category_name, brand, condition_id,
                      relationship_details, first_price, index_value, user):
    """부모 행 생성 - INDEX 기반 다중 이미지 URL 생성"""

    parent_image_urls = generate_parent_image_urls(psku, index_value, user)

    parent = {
        '*Action(SiteID=US|Country=KR|Currency=USD|Version=1193)': 'Add',
        'Custom label (SKU)': psku,
        'Category ID': category_id,
        'Category name': category_name,
        'Title': product_name,
        'Relationship': '',
        'Relationship details': relationship_details,
        'Schedule Time': '',
        'P:UPC': '',
        'P:EPID': '',
        'Start price': first_price,
        'Quantity': str(user.get('default_quantity', 999)),
        'Item photo URL': parent_image_urls,
        'VideoID': '',
        'Condition ID': condition_id,
        'Description': user.get('default_description', ''),
        'Format': 'FixedPrice',
        'Duration': 'GTC',
        'Buy It Now price': '',
        'Best Offer Enabled': '',
        'Best Offer Auto Accept Price': '',
        'Minimum Best Offer Price': '',
        'Immediate pay required': '',
        'Location': 'KR',
        'Shipping service 1 option': 'StandardShippingFromOutsideUS',
        'Shipping service 1 cost': '0',
        'Shipping service 1 priority': '',
        'Shipping service 2 option': '',
        'Shipping service 2 cost': '',
        'Shipping service 2 priority': '',
        'Max dispatch time': '3',
        'Returns accepted option': '',
        'Returns within option': '',
        'Refund option': '',
        'Return shipping cost paid by': '',
        'Shipping profile name': user.get('shipping_profile_name', ''),
        'Return profile name': user.get('return_profile_name', ''),
        'Payment profile name': user.get('payment_profile_name', ''),
        'ProductCompliancePolicyID': '',
        'Regional ProductCompliancePolicies': '',
        'C:Brand': brand
    }

    return parent


def create_child_row(row, user):
    """자식 행 생성 - OPTIONS 고정 형식 사용"""

    sku = str(row.get('SKU', '')).strip()
    option = str(row.get('OPTION', '')).strip()
    price = clean_price(row.get('PRICE', '0'))

    relationship_details = f"OPTIONS={option}" if option else ''

    base_image_url = generate_image_url(sku, user)
    child_image_url = f"{option}={base_image_url}" if option and base_image_url else base_image_url

    child = {
        '*Action(SiteID=US|Country=KR|Currency=USD|Version=1193)': '',
        'Custom label (SKU)': sku,
        'Category ID': '',
        'Category name': '',
        'Title': '',
        'Relationship': 'Variation',
        'Relationship details': relationship_details,
        'Schedule Time': '',
        'P:UPC': '',
        'P:EPID': '',
        'Start price': price,
        'Quantity': str(user.get('default_quantity', 999)),
        'Item photo URL': child_image_url,
        'VideoID': '',
        'Condition ID': '',
        'Description': '',
        'Format': '',
        'Duration': '',
        'Buy It Now price': '',
        'Best Offer Enabled': '',
        'Best Offer Auto Accept Price': '',
        'Minimum Best Offer Price': '',
        'Immediate pay required': '',
        'Location': '',
        'Shipping service 1 option': '',
        'Shipping service 1 cost': '',
        'Shipping service 1 priority': '',
        'Shipping service 2 option': '',
        'Shipping service 2 cost': '',
        'Shipping service 2 priority': '',
        'Max dispatch time': '',
        'Returns accepted option': '',
        'Returns within option': '',
        'Refund option': '',
        'Return shipping cost paid by': '',
        'Shipping profile name': '',
        'Return profile name': '',
        'Payment profile name': '',
        'ProductCompliancePolicyID': '',
        'Regional ProductCompliancePolicies': '',
        'C:Brand': ''
    }

    return child


def generate_parent_image_urls(psku, index_value, user):
    """INDEX 기반 부모 상품 다중 이미지 URL 생성 - 샵코드 적용"""

    if not psku or not user.get('image_domain'):
        return ""

    shop_code = str(user.get('shop_code', '')).strip()

    try:
        only_digits = re.sub(r'[^\d]', '', str(index_value)) if index_value else ''
        index_num = int(only_digits) if only_digits else 0
    except ValueError:
        index_num = 0

    image_urls = []

    # 첫 번째 이미지
    if shop_code:
        first_image_sku = f"{psku}_C_{shop_code}"
        first_image_url = generate_image_url(first_image_sku, user)
        if first_image_url:
            image_urls.append(first_image_url)
    else:
        base_url = generate_image_url(psku, user)
        if base_url:
            image_urls.append(base_url)

    # 추가 이미지
    for i in range(1, index_num + 1):
        sub_sku = f"{psku}_D{i}"
        sub_url = generate_image_url(sub_sku, user)
        if sub_url:
            image_urls.append(sub_url)

    return '|'.join(image_urls)


def generate_image_url(sku, user):
    """SKU 기반 이미지 URL 생성"""
    if not sku or not user.get('image_domain'):
        return ""

    domain = user['image_domain'].rstrip('/')
    pattern = user.get('image_url_pattern', '/{sku}.jpg')

    return domain + pattern.format(sku=sku)


def clean_price(price_value):
    """가격에서 숫자만 추출"""
    if not price_value:
        return ""

    cleaned = re.sub(r'[^\d.]', '', str(price_value))
    try:
        return f"{float(cleaned):.2f}" if cleaned else ""
    except ValueError:
        return ""


def validate_ebay_data(ebay_df, category_map):
    """이베이 데이터 검증"""
    errors = []

    if len(ebay_df) == 0:
        return ["데이터가 없습니다."]

    add_rows = ebay_df[ebay_df['*Action(SiteID=US|Country=KR|Currency=USD|Version=1193)'] == 'Add']

    required_fields = ['Custom label (SKU)', 'Category ID', 'Category name', 'Title', 'Start price', 'Condition ID']

    for idx, row in add_rows.iterrows():
        for field in required_fields:
            if not str(row.get(field, '')).strip():
                errors.append(f"PSKU 행 {idx + 2}: {field} 누락")

    if category_map:
        invalid_cats = add_rows[
            ~add_rows['Category ID'].isin(category_map.keys()) & (add_rows['Category ID'] != '')
        ]
        if len(invalid_cats) > 0:
            unique_invalid = invalid_cats['Category ID'].unique()[:5]
            errors.append(f"⚠️ CAT 탭에 없는 카테고리 ID: {', '.join(map(str, unique_invalid))}")

    var_rows = ebay_df[ebay_df['Relationship'] == 'Variation']
    for idx, row in var_rows.iterrows():
        if not str(row.get('Custom label (SKU)', '')).strip():
            errors.append(f"SKU 행 {idx + 2}: SKU 누락")
        if not str(row.get('Start price', '')).strip():
            errors.append(f"SKU 행 {idx + 2}: 가격 누락")

    return errors


def get_ebay_column_order():
    """이베이 표준 컬럼 순서"""
    return [
        '*Action(SiteID=US|Country=KR|Currency=USD|Version=1193)',
        'Custom label (SKU)',
        'Category ID',
        'Category name',
        'Title',
        'Relationship',
        'Relationship details',
        'Schedule Time',
        'P:UPC',
        'P:EPID',
        'Start price',
        'Quantity',
        'Item photo URL',
        'VideoID',
        'Condition ID',
        'Description',
        'Format',
        'Duration',
        'Buy It Now price',
        'Best Offer Enabled',
        'Best Offer Auto Accept Price',
        'Minimum Best Offer Price',
        'Immediate pay required',
        'Location',
        'Shipping service 1 option',
        'Shipping service 1 cost',
        'Shipping service 1 priority',
        'Shipping service 2 option',
        'Shipping service 2 cost',
        'Shipping service 2 priority',
        'Max dispatch time',
        'Returns accepted option',
        'Returns within option',
        'Refund option',
        'Return shipping cost paid by',
        'Shipping profile name',
        'Return profile name',
        'Payment profile name',
        'ProductCompliancePolicyID',
        'Regional ProductCompliancePolicies',
        'C:Brand'
    ]
