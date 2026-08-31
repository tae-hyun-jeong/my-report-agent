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

# 2. 배터리 논문 전용 정밀 검색 (제목/초록 기반 필터링으로 LLM/컴퓨터공학 논문 완전 차단)
def fetch_specific_arxiv(query, label):
    url = f'https://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=3'
    try:
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        entries = root.findall('atom:entry', ns)
        for entry in entries:
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            link = entry.find('atom:id', ns).text.strip()
            
            # 본문에 battery / lithium 관련 단어가 확실히 포함된 것만 선정
            text_check = (title + summary).lower()
            if "battery" in text_check or "batteries" in text_check or "lithium" in text_check:
                return f"[{label}]\n- 제목: {title}\n- 링크: {link}\n- 초록 원문: {summary[:500]}..."
    except Exception as e:
        pass
    return f"[{label}] 최근 3년 내 수집된 관련 배터리 논문 없음"

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
당신은 리튬이온 배터리 공정/소재 및 AI 산업 전문 수석 애널리스트입니다.
아래 수집된 원문 데이터를 바탕으로 텔레그램 데일리 리포트({today})를 아래 **엄격한 작성 규칙과 포맷**에 맞춰 한국어로 작성해주세요.

[중요 지침]
- **연구 문헌은 반드시 순수 화학/소재 '배터리' 관련 연구만 다루어야 합니다.** (LLM, NLP, 소프트웨어 AI 모델 논문은 배터리 논문 섹션에 절대 포함하지 마세요.)
- 배터리 논문 3건은 최근 3년 내 발표된 최신 연구 기준으로 요약합니다.

[작성 규칙 및 포맷]
1. 가독성 좋게 이모지와 불릿포인트를 사용하세요.

2. 🔋 **연구 문헌 (총 3건, 배터리 연구)**
   - 각 논문은 반드시 **목적:**과 **결과:**를 각각 **3줄 이내**로 압축해서 요약하세요. (원문 링크 포함)
   - [1] Formation(화성/활성화 및 SEI 형성) 공정 관련 논문
   - [2] 차세대 배터리(전고체/실리콘음극/리튬메탈 등) 연구 관련 논문
   - [3] 일반 리튬이온 배터리(수명/열화/안전성 등) 관련 논문

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
    
    # 1) Formation/SEI 공정 배터리 논문 (제목/초록 타겟팅)
    query_formation = '(ti:formation OR abs:formation OR ti:SEI OR abs:SEI) AND (ti:battery OR abs:battery OR ti:lithium OR abs:lithium)'
    paper_formation = fetch_specific_arxiv(query_formation, '1. Formation(화성/활성화) 공정 관련 논문')

    # 2) 차세대 배터리 논문 (전고체, 실리콘, 리튬메탈)
    query_next_gen = '(ti:"solid-state" OR abs:"solid-state" OR ti:"silicon anode" OR abs:"silicon anode" OR ti:"lithium metal" OR abs:"lithium metal") AND (ti:battery OR abs:battery)'
    paper_next_gen = fetch_specific_arxiv(query_next_gen, '2. 차세대 배터리 연구 논문')

    # 3) 일반 리튬이온 배터리 논문 (수명, 열화, 전해액 등)
    query_general = '(ti:"lithium-ion battery" OR abs:"lithium-ion battery" OR ti:"capacity fade" OR abs:"capacity fade" OR ti:"electrolyte" OR abs:"electrolyte") AND (ti:battery OR abs:battery)'
    paper_general = fetch_specific_arxiv(query_general, '3. 일반 리튬이온 배터리 논문')

    battery_news = fetch_google_news("리튬이온 배터리 시장 OR 배터리 공급망 OR K배터리")
    ai_news = fetch_google_news("글로벌 AI 시장 동향 OR 인공지능 빅테크")

    all_data = f"""
=== 1. Formation 공정 관련 논문 ===
{paper_formation}

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
