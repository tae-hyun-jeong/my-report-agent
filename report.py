import os
import sys
import requests
import xml.etree.ElementTree as ET
from google import genai
from datetime import datetime

# 1. 시크릿 값 불러오기
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([TELEGRAM_TOKEN, CHAT_ID, GEMINI_API_KEY]):
    print("[오류] 시크릿 키 설정이 누락되었습니다.")
    sys.exit(1)

# 최신 Google GenAI 클라이언트 생성
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 2. arXiv 최신 배터리 논문 가져오기
def fetch_arxiv_papers():
    url = 'https://export.arxiv.org/api/query?search_query=all:"lithium-ion battery" OR all:"solid-state battery"&sortBy=submittedDate&sortOrder=descending&max_results=3'
    try:
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        papers = []
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            link = entry.find('atom:id', ns).text.strip()
            papers.append(f"- 제목: {title}\n- 링크: {link}\n- 요약: {summary[:400]}...")
        return "\n\n".join(papers) if papers else "논문 결과 없음"
    except Exception as e:
        return f"논문 수집 에러: {e}"

# 3. 구글 뉴스 RSS에서 최신 뉴스 가져오기
def fetch_google_news(keyword):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        news_items = []
        for item in root.findall('./channel/item')[:3]:
            title = item.find('title').text
            link = item.find('link').text
            news_items.append(f"- {title}\n  링크: {link}")
        return "\n".join(news_items) if news_items else "뉴스 결과 없음"
    except Exception as e:
        return f"뉴스 수집 에러: {e}"

# 4. Gemini 2.5 Flash에게 한국어 브리핑 작성 요청하기
def summarize_with_ai(raw_text):
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
당신은 배터리 및 AI 분야 전문 애널리스트입니다.
아래 수집된 원문 데이터를 바탕으로 텔레그램 데일리 리포트({today})를 작성해주세요.

[작성 규칙]
1. 가독성 좋게 이모지와 불릿포인트를 사용하세요.
2. 아래 3가지 섹션으로 나누어 작성하세요:
🔋 [1] 리튬이온/차세대 배터리 주요 논문 요약 (핵심 인사이트 1~2줄 + 논문 링크)
📈 [2] 리튬 배터리 산업 및 시장 동향 (핵심 시사점)
🤖 [3] 글로벌 AI 시장 및 테크 동향 (핵심 시사점)
3. 텔레그램 화면에서 읽기 편하게 1,500자 이내로 핵심만 간결하게 작성하세요.

[수집 데이터]
{raw_text}
"""
    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text

# 5. 텔레그램으로 메시지 보내기
def send_telegram(message):
    target_ids = [cid.strip() for cid in CHAT_ID.split(",") if cid.strip()]
    for cid in target_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": message,
            "disable_web_page_preview": True
        }
        res = requests.post(url, json=payload, timeout=15)
        if res.ok:
            print(f"텔레그램 전송 성공! (Chat ID: {cid})")
        else:
            print(f"전송 실패 (Chat ID: {cid}):", res.text)

if __name__ == "__main__":
    print("1. 논문 및 뉴스 수집 중...")
    papers = fetch_arxiv_papers()
    battery_news = fetch_google_news("리튬이온 배터리 시장 OR 배터리 산업")
    ai_news = fetch_google_news("AI 시장 동향 OR 인공지능 산업")

    all_data = f"=== 배터리 논문 ===\n{papers}\n\n=== 배터리 뉴스 ===\n{battery_news}\n\n=== AI 뉴스 ===\n{ai_news}"
    
    print("2. AI 요약 리포트 작성 중...")
    briefing = summarize_with_ai(all_data)
    
    print("3. 텔레그램 발송 중...")
    send_telegram(briefing)
