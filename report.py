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

# 2. 목적별 맞춤형 논문 수집 (저전압선별 / 차세대배터리 / 일반리튬)
def fetch_specific_arxiv(query, label):
    url = f'https://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=1'
    try:
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            link = entry.find('atom:id', ns).text.strip()
            return f"[{label}]\n- 제목: {title}\n- 링크: {link}\n- 초록 원문: {summary[:500]}..."
    except Exception as e:
        pass
    return f"[{label}] 논문 수집 결과 없음"

# 3. 구글 뉴스 RSS 수집
def fetch_google_news(keyword, max_count=4):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        news_items = []
        for item in root.findall('./channel/item')[:max_count]:
            title = item.find('title').text
            link = item.find('link').text
            news_items.append(f"- {title} (URL: {link})")
        return "\n".join(news_items) if news_items else "뉴스 결과 없음"
    except Exception as e:
        return f"뉴스 수집 에러: {e}"

# 4. Gemini 3.6 Flash에게 지정된 포맷으로 요약 요청하기
def summarize_with_ai(raw_text):
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
당신은 배터리 공정 및 AI 산업 전문 수석 애널리스트입니다.
아래 수집된 원문 데이터를 바탕으로 텔레그램 데일리 리포트({today})를 아래 **엄격한 작성 규칙과 포맷**에 맞춰 한국어로 작성해주세요.

[작성 규칙 및 포맷]
1. 가독성 좋게 이모지와 불릿포인트를 사용하세요.

2. 🔋 **연구 문헌 (총 3건, 중복 없음)**
   - 각 논문은 반드시 **목적**과 **결과**를 각각 **3줄 이내**로 압축해서 요약하세요.
   - [1] 저전압 선별/결함 관련 논문
   - [2] 차세대 배터리 연구 관련 논문
   - [3] 일반 리튬이온 배터리 관련 논문

3. 📈 **리튬 배터리 산업 및 시장 동향**
   - 동향 요약: 핵심 내용을 **3줄**로 작성하세요.
   - 인사이트 및 향후 전망: 핵심 시사점과 전망을 **1줄**로 요약하세요.

4. 🤖 **글로벌 AI 시장 및 테크 동향**
   - 동향 요약: 핵심 내용을 **3줄**로 작성하세요.
   - 인사이트 및 향후 전망: 핵심 시사점과 전망을 **1줄**로 요약하세요.

[수집 데이터]
{raw_text}
"""
    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text

# 5. 텔레그램 전송
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
    paper_low_voltage = fetch_specific_arxiv('all:"low-voltage" OR all:"self-discharge" OR all:"defect detection" battery', '1. 저전압 선별 관련 논문')
    paper_next_gen = fetch_specific_arxiv('all:"solid-state battery" OR all:"silicon anode" OR all:"lithium metal"', '2. 차세대 배터리 연구 논문')
    paper_general = fetch_specific_arxiv('all:"lithium-ion battery" OR all:"cycling stability" OR all:"capacity fade"', '3. 일반 리튬이온 배터리 논문')

    battery_news = fetch_google_news("리튬이온 배터리 시장 동향 OR 배터리 공급망")
    ai_news = fetch_google_news("글로벌 AI 시장 동향 OR 인공지능 빅테크")

    all_data = f"""
=== 1. 저전압 선별 관련 논문 ===
{paper_low_voltage}

=== 2. 차세대 배터리 연구 논문 ===
{paper_next_gen}

=== 3. 일반 리튬이온 배터리 논문 ===
{paper_general}

=== 배터리 시장 뉴스 ===
{battery_news}

=== AI 시장 뉴스 ===
{ai_news}
"""
    
    print("2. AI 요약 리포트 작성 중...")
    briefing = summarize_with_ai(all_data)
    
    print("3. 텔레그램 발송 중...")
    send_telegram(briefing)
