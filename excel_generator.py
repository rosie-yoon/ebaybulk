import pandas as pd
import re
from database import get_user, save_generation_history
import io
import gspread
from google.oauth2.service_account import Credentials

# Google Sheets API 설정
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


def get_google_sheets_client():
    """Google Sheets API 클라이언트 생성"""
    try:
        creds = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except FileNotFoundError:
        raise Exception("service_account.json 파일이 없습니다.")
    except Exception as e:
        raise Exception(f"Google Sheets API 인증 실패: {str(e)}")


def read_bulk_and_cat_tabs(sheet_id):
    """Bulk 탭과 CAT 탭 읽기 - INDEX 컬럼 포함"""
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(sheet_id)

        # Bulk 탭 읽기 (INDEX 컬럼 포함)
        bulk_worksheet = spreadsheet.worksheet('Bulk')
        bulk_data = bulk_worksheet.get_all_values()

        if bulk_data:
            bulk_df = pd.DataFrame(bulk_data[1:], columns=bulk_data[0])
            bulk_df.columns = bulk_df.columns.str.strip()
        else:
            bulk_df = pd.DataFrame()

        # CAT 탭 읽기 (3컬럼: 경로, ID, Condition ID)
        try:
            cat_worksheet = spreadsheet.worksheet('CAT')
            cat_data = cat_worksheet.get_all_values()

            category_map = {}
            for row in cat_data:
                if len(row) >= 2 and row[1].strip():
                    category_path = row[0].strip()
                    category_id = row[1].strip()
                    # C열이 있으면 사용, 없으면 기본값
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

    # 4. DataFrame 생성 및 컬럼 정렬 (AO열까지만)
    ebay_df = pd.DataFrame(ebay_rows)
    ebay_columns = get_ebay_column_order()
    ebay_df = ebay_df.reindex(columns=ebay_columns, fill_value='')

    # 5. Excel 파일 생성
    output = io.BytesIO()
    filename = f"ebay_bulk_{user['name']}.xlsx"

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ebay_df.to_excel(writer, index=False, sheet_name='eBay Bulk Upload')

        # 컬럼 너비 자동 조정
        worksheet = writer.sheets['eBay Bulk Upload']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
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

    # PSKU로 그룹핑
    grouped = bulk_df.groupby('PSKU', sort=False)

    for psku, group in grouped:
        psku = str(psku).strip()
        if not psku:
            continue

        # 그룹 내 첫 번째 행에서 공통 정보 추출
        first_row = group.iloc[0]
        product_name = str(first_row.get('Product Name', '')).strip()
        category_id = str(first_row.get('Categoery ID', '')).strip()
        category_name = str(first_row.get('Categoery', '')).strip()
        brand = str(first_row.get('BRAND', '')).strip()
        item_type = str(first_row.get('ITEM', '')).strip()
        index_value = str(first_row.get('INDEX', '0')).strip()  # INDEX 컬럼 추가

        # CAT 탭에서 카테고리 정보 조회
        cat_info = category_map.get(category_id, {})

        # Category Name 백업 (Bulk에 없으면 CAT에서)
        if not category_name and cat_info:
            category_name = cat_info.get('path', '')

        # Condition ID 매핑 (CAT 탭 C열 값 사용)
        condition_id = cat_info.get('condition', '1000-New')

        # 모든 자식의 OPTION 값 수집 (세미콜론으로 병합)
        all_options = []
        for _, child in group.iterrows():
            option = str(child.get('OPTION', '')).strip()
            if option:
                all_options.append(option)

        # Relationship details: "Size=옵션1;옵션2;옵션3" 형식
        relationship_details = f"{item_type}={';'.join(all_options)}" if item_type and all_options else ''

        # 1. 부모 행 생성 (Add) - INDEX 기반 다중 이미지
        parent_row = create_parent_row(
            psku=psku,
            product_name=product_name,
            category_id=category_id,
            category_name=category_name,
            brand=brand,
            condition_id=condition_id,
            relationship_details=relationship_details,
            first_price=clean_price(first_row.get('PRICE', '0')),
            index_value=index_value,  # INDEX 전달
            user=user
        )
        ebay_rows.append(parent_row)

        # 2. 자식 행들 생성 (Variation)
        for _, child_data in group.iterrows():
            child_row = create_child_row(child_data, user)
            ebay_rows.append(child_row)

    return ebay_rows


def create_parent_row(psku, product_name, category_id, category_name, brand, condition_id,
                      relationship_details, first_price, index_value, user):
    """부모 행 생성 - INDEX 기반 다중 이미지 URL 생성"""

    # INDEX 기반 다중 이미지 URL 생성
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
        'Quantity': str(user.get('default_quantity', 999)),  # 사용자 설정값 적용
        'Item photo URL': parent_image_urls,  # 파이프(|) 구분 다중 URL
        'VideoID': '',
        'Condition ID': condition_id,  # CAT 탭 C열에서 매핑
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
        'Shipping profile name': '',
        'Return profile name': user.get('return_profile_name', ''),
        'Payment profile name': user.get('payment_profile_name', ''),
        'ProductCompliancePolicyID': '',
        'Regional ProductCompliancePolicies': '',
        'C:Brand': brand
        # AO열(C:Brand)에서 종료
    }

    return parent


def create_child_row(row, user):
    """자식 행 생성 - 기존 로직 유지"""

    sku = str(row.get('SKU', '')).strip()
    item = str(row.get('ITEM', '')).strip()
    option = str(row.get('OPTION', '')).strip()
    price = clean_price(row.get('PRICE', '0'))

    # Relationship details: "Size=Blanche&Woody 400ml" 형식
    relationship_details = f"{item}={option}" if item and option else option

    # 자식 이미지 URL: "Blanche&Woody 400ml=https://shopeept.com/LABOH0007.jpg" 형식
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
        'Quantity': str(user.get('default_quantity', 999)),  # 사용자 설정값 적용
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
    """INDEX 기반 부모 상품 다중 이미지 URL 생성"""

    if not psku or not user.get('image_domain'):
        return ""

    domain = user['image_domain'].rstrip('/')

    # INDEX 값 정제 (숫자만 추출)
    try:
        index_num = int(re.sub(r'[^\d]', '', str(index_value))) if index_value else 0
    except ValueError:
        index_num = 0

    # 이미지 URL 리스트 생성
    image_urls = []

    # 1. 기본 이미지 (항상 포함)
    base_url = generate_image_url(psku, user)
    if base_url:
        image_urls.append(base_url)

    # 2. 추가 이미지 (INDEX 개수만큼)
    for i in range(1, index_num + 1):
        # PSKU_D1, PSKU_D2 형태로 SKU 생성
        sub_sku = f"{psku}_D{i}"
        sub_url = generate_image_url(sub_sku, user)
        if sub_url:
            image_urls.append(sub_url)

    # 3. 파이프(|)로 연결 (이베이 공식 구분자)
    return '|'.join(image_urls)


def generate_image_url(sku, user):
    """SKU 기반 이미지 URL 생성 (기존 함수 유지)"""
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

    # Add 행 검증
    add_rows = ebay_df[ebay_df['*Action(SiteID=US|Country=KR|Currency=USD|Version=1193)'] == 'Add']

    # 필수 필드 체크
    required_fields = ['Custom label (SKU)', 'Category ID', 'Category name', 'Title', 'Start price', 'Condition ID']

    for idx, row in add_rows.iterrows():
        for field in required_fields:
            if not str(row.get(field, '')).strip():
                errors.append(f"부모 행 {idx + 2}: {field} 누락")

    # CAT 탭 카테고리 ID 검증
    if category_map:
        invalid_cats = add_rows[~add_rows['Category ID'].isin(category_map.keys()) & (add_rows['Category ID'] != '')]
        if len(invalid_cats) > 0:
            unique_invalid = invalid_cats['Category ID'].unique()[:5]
            errors.append(f"⚠️ CAT 탭에 없는 카테고리 ID: {', '.join(map(str, unique_invalid))}")

    # Variation 행 검증
    var_rows = ebay_df[ebay_df['Relationship'] == 'Variation']
    for idx, row in var_rows.iterrows():
        if not str(row.get('Custom label (SKU)', '')).strip():
            errors.append(f"자식 행 {idx + 2}: SKU 누락")
        if not str(row.get('Start price', '')).strip():
            errors.append(f"자식 행 {idx + 2}: 가격 누락")

    return errors


def get_ebay_column_order():
    """이베이 표준 컬럼 순서 - AO열(C:Brand)까지만"""
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
