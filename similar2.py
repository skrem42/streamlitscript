import json
import requests
from notion_client import Client
import base64
from io import BytesIO

# === Configuration (hardcoded) ===
JSON_FILE = 'dataset.json'
NOTION_TOKEN = 'ntn_B28202664456o3Kv5C0LKoOUZgMRFKp1z0yjoXGmBgP8yk'
NOTION_DATABASE_ID = '2220a819d9cd80709221c4b260703785'
VISION_API_KEY = 'AIzaSyB4SXgdV4p6T-wzFjLRjYHRCQ20WT0g89I'

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)

# Vision API endpoint
ENDPOINT_URL = f'https://vision.googleapis.com/v1/images:annotate?key={VISION_API_KEY}'

# Load pre‐fetched reel dataset from JSON
with open(JSON_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Prepare list of (image_url, reel_url, account) tuples
urls = [
    (
        item.get('displayUrl', ''),      # image URL for OCR
        item.get('url', ''),             # actual reel URL for Notion
        item.get('ownerUsername', 'Unknown')
    )
    for item in data
]

def ocr_google_vision(image_url: str) -> str:
    """Run Google Vision OCR on the given image URL."""
    try:
        resp_img = requests.get(image_url, timeout=30)
        resp_img.raise_for_status()
        image_bytes = resp_img.content
        if not image_bytes:
            return ''
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {
            "requests": [
                {
                    "image": {"content": image_base64},
                    "features": [{"type": "TEXT_DETECTION"}]
                }
            ]
        }
        resp = requests.post(ENDPOINT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if 'responses' not in result:
            print(f"❌ No OCR response for {image_url}: {result}")
            return ''
        annotations = result['responses'][0].get('textAnnotations', [])
        return annotations[0]['description'].strip() if annotations else ''
    except Exception as e:
        print(f"❌ OCR failed for {image_url}: {e}")
        return ''

# Process each entry and upload to Notion
for image_url, reel_url, account in urls:
    print(f"Processing reel: {reel_url}")
    caption = ocr_google_vision(image_url)
    if not caption:
        print("  – no text found, skipping")
        continue

    # Create a new page in Notion:
    # • Account → Title
    # • Caption → Rich text (supports \n)
    # • URL → URL field
    notion.pages.create(
        parent={ "database_id": NOTION_DATABASE_ID },
        properties={
            "Account": {
                "title": [
                    { "text": { "content": account } }
                ]
            },
            "Caption": {
                "rich_text": [
                    { "text": { "content": caption } }
                ]
            },
            "URL": {
                "url": reel_url
            }
        }
    )
    print(f"  ✅ Uploaded: {reel_url}")