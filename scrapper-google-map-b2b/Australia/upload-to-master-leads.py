import argparse
import os
from pathlib import Path
import pandas as pd
from pyairtable import Api


def normalize_text(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def pick_column(df, *candidates):
    lowered = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def discover_input_files(root_dir: Path):
    files = []
    for path in root_dir.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() == '.csv':
            files.append(path)
        elif path.suffix == '' and path.parent != root_dir:
            files.append(path)
    return sorted(files)


def build_pitch_type(category: str, mapping: dict):
    return mapping.get(category.lower(), 'AI Chatbot')


def build_records_for_file(file_path: Path, root_dir: Path, pitch_mapping: dict):
    city = file_path.parent.name.replace('_', ' ').title()
    category = file_path.stem.replace('_', ' ').replace('-', ' ').title()
    pitch_type = build_pitch_type(category, pitch_mapping)

    try:
        df = pd.read_csv(file_path)
    except Exception as exc:
        print(f"❌ {file_path} 읽기 실패: {exc}")
        return []

    df = df.where(pd.notnull(df), None)
    print(f"🔄 [{city} - {category}] 데이터 읽는 중... (총 {len(df)}줄)")

    name_column = pick_column(df, 'name', 'business_name', 'company_name', 'company', 'business')
    website_column = pick_column(df, 'website', 'website_url', 'url')
    email_column = pick_column(df, 'email', 'email_address', 'extracted_email', 'contact_email')

    records = []
    for _, row in df.iterrows():
        name = normalize_text(row[name_column]) if name_column else None
        website = normalize_text(row[website_column]) if website_column else None
        email = normalize_text(row[email_column]) if email_column else None

        record = {
            'Name': name,
            'Website': website,
            'Email': email,
            'Country': 'Australia',
            'City': city,
            'Category': category,
            'Pitch Type': pitch_type,
            'Status': 'To Contact',
        }

        if name and email and email not in {'Not Found', 'Connection Error', 'No Website'}:
            records.append(record)

    return records


def main():
    parser = argparse.ArgumentParser(description='Upload scraped lead data to Airtable from the Australia folder.')
    parser.add_argument('--root-dir', default=str(Path(__file__).resolve().parent), help='Root directory to scan for CSV files')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be uploaded without sending anything')
    parser.add_argument('--api-token', default=os.getenv('AIRTABLE_API_TOKEN'), help='Airtable personal access token')
    parser.add_argument('--base-id', default=os.getenv('AIRTABLE_BASE_ID'), help='Airtable base ID')
    parser.add_argument('--table-name', default=os.getenv('AIRTABLE_TABLE_NAME', 'Master Leads'), help='Airtable table name')
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    csv_files = discover_input_files(root_dir)

    if not csv_files:
        print(f"📁 {root_dir} 안에 업로드 대상 파일이 없습니다.")
        return

    pitch_mapping = {
        'clinic': 'AI Chatbot',
        'hospital': 'AI Chatbot',
        'restaurant': 'Web Redesign',
        'restaurants': 'Web Redesign',
        'agency': 'Lead Gen Automation',
    }

    all_records = []
    for file_path in csv_files:
        rel_path = file_path.relative_to(root_dir)
        print(f"📄 발견: {rel_path}")
        all_records.extend(build_records_for_file(file_path, root_dir, pitch_mapping))

    valid_records = [r for r in all_records if r['Name'] and r['Email']]
    print(f"\n📊 유효 레코드 수: {len(valid_records)}")

    if args.dry_run:
        print('🧪 Dry run 모드: Airtable 업로드는 건너뜁니다.')
        return

    if not args.api_token or not args.base_id:
        print('⚠️ Airtable credentials not provided. Set AIRTABLE_API_TOKEN and AIRTABLE_BASE_ID or pass --api-token/--base-id.')
        return

    api = Api(args.api_token)
    table = api.table(args.base_id, args.table_name)

    if valid_records:
        print(f"\n🚀 총 {len(valid_records)}개의 레코드를 '{args.table_name}' 테이블로 전송합니다...")
        table.batch_create(valid_records)
        print('✅ 업로드 완료')
    else:
        print('\n전송할 유효한 데이터가 없습니다. 이메일이 없거나 형식이 맞지 않습니다.')


if __name__ == '__main__':
    main()
