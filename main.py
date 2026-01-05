import os
from dotenv import load_dotenv
import feedparser
from datetime import datetime, timedelta
import re
from html import unescape
import time
import logging
import json
from deepseek_client import DeepSeekClient
from gemini_client import GeminiClient
from utils.api_util import ApiUtil, ApiError
from utils.logger_util import LoggerUtil
from utils.telegram_util import TelegramUtil

# .env 파일 로드
load_dotenv()

# 로거 초기화
logger = LoggerUtil().get_logger()

def initialize_ai_client():
    """AI 클라이언트 초기화

    Returns:
        AI 클라이언트 객체 (DeepSeekClient 또는 GeminiClient)

    Raises:
        ValueError: 지원하지 않는 AI Provider인 경우
    """
    ai_provider = os.getenv('AI_PROVIDER')

    if ai_provider == 'deepseek':
        return DeepSeekClient(
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            model_id=os.getenv('DEEPSEEK_MODEL')
        )
    elif ai_provider == 'gemini':
        return GeminiClient(
            api_key=os.getenv('GOOGLE_API_KEY'),
            model_id=os.getenv('GEMINI_MODEL')
        )
    else:
        raise ValueError(f"지원하지 않는 AI Provider: {ai_provider}")

def clean_html(raw_html):
    """HTML 태그 제거"""
    # HTML 태그 제거
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html)
    # HTML 엔티티 디코딩 (예: &quot; -> ", &amp; -> &)
    text = unescape(text)
    # 연속된 공백 제거
    text = ' '.join(text.split())
    return text

def clean_text(text):
    """텍스트 정제"""
    if not text:
        return ''
    # HTML 태그 및 엔티티 제거
    text = clean_html(text)
    # 특수문자 처리 (필요한 경우 추가)
    text = text.replace('\n', ' ').replace('\r', '')
    return text.strip()

def is_within_24_hours(published_time):
    """기사가 24시간 이내인지 확인"""
    if not published_time:
        return False
        
    try:
        # 현재 시간과 기사 발행 시간의 차이 계산
        current_time = datetime.now()
        article_time = datetime(*published_time[:6])  # published_parsed는 time.struct_time 형식
        time_difference = current_time - article_time
        
        return time_difference.total_seconds() <= 24 * 60 * 60  # 24시간을 초로 변환
    except Exception as e:
        logger.error(f"시간 비교 중 오류 발생: {e}")
        return False

def fetch_rss_feed(feed_url, api_util, feed_info):
    """RSS 피드 데이터 가져오기"""
    try:
        feed = feedparser.parse(feed_url)

        # entries가 있는 경우에만 처리
        if hasattr(feed, 'entries'):
            # published_parsed를 기준으로 최신순 정렬
            feed.entries.sort(
                key=lambda x: x.get('published_parsed', time.gmtime(0)),
                reverse=True
            )

            # 1단계: 24시간 이내 + 사진 기사 아닌 것만 필터링
            pre_filtered_entries = []
            for entry in feed.entries:
                # 24시간 이내 뉴스만 필터링
                if not is_within_24_hours(entry.get('published_parsed')):
                    continue

                title = entry.title
                summary = entry.get('summary', '')

                # 사진 기사 필터링 (제목에 '포토' 포함 또는 내용 없음)
                if '포토' in title or not summary.strip():
                    logger.debug(f"사진 기사 건너뜀: {title}")
                    continue

                pre_filtered_entries.append(entry)

            # 2단계: 배치로 중복 체크
            if pre_filtered_entries:
                urls = [entry.link for entry in pre_filtered_entries]
                logger.info(f"배치 중복 체크 시작: {len(urls)}개 URL")

                duplicate_results = api_util.is_news_exists_batch(urls)

                # 중복되지 않은 뉴스만 최종 필터링
                filtered_entries = []
                for entry in pre_filtered_entries:
                    if duplicate_results.get(entry.link, False):
                        logger.debug(f"중복된 뉴스 건너뜀: {entry.title}")
                        continue
                    filtered_entries.append(entry)

                logger.info(f"중복 체크 완료: {len(filtered_entries)}/{len(pre_filtered_entries)}개 뉴스가 새로운 뉴스")
            else:
                filtered_entries = []

            feed.entries = filtered_entries

        return feed
    except Exception as e:
        logger.error(f"RSS 피드 파싱 실패: {e}")
        return None

def main():
    logger.info("RSS 뉴스 수집 프로그램 시작")

    # 필수 환경변수 체크
    required_env_vars = [
        "AI_PROVIDER",
        "BASE_URL",
        "TELEGRAM_CHAT_TEST_ID",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_BOT_TOKEN"
    ]

    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        error_message = f"🛑 필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}"
        logger.error(error_message)
        raise ValueError(error_message)
    else:
        ai_provider = os.getenv('AI_PROVIDER')
        telegram_util = TelegramUtil()
        api_util = ApiUtil()

    # 선택 환경변수 체크
    if ai_provider not in ['deepseek', 'gemini']:
        error_message = f"AI_PROVIDER 값이 올바르지 않습니다: {ai_provider} (deepseek 또는 gemini만 가능)"
        logger.error(error_message)
        raise ValueError(error_message)
    
    # AI Provider별 필수 환경변수 검증
    if ai_provider == 'deepseek':
        DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
        DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL')
        if not DEEPSEEK_API_KEY:
            error_message = "DEEPSEEK_API_KEY가 설정되지 않았습니다."
            logger.error(error_message)
            raise ValueError(error_message)
        if not DEEPSEEK_MODEL:
            error_message = "DEEPSEEK_MODEL이 설정되지 않았습니다. (예: deepseek-chat)"
            logger.error(error_message)
            raise ValueError(error_message)
    elif ai_provider == 'gemini':
        GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        GEMINI_MODEL = os.getenv('GEMINI_MODEL')
        if not GOOGLE_API_KEY:
            error_message = "GOOGLE_API_KEY가 설정되지 않았습니다."
            logger.error(error_message)
            raise ValueError(error_message)
        if not GEMINI_MODEL:
            error_message = "GEMINI_MODEL이 설정되지 않았습니다. (예: gemini-flash-lite-latest)"
            logger.error(error_message)
            raise ValueError(error_message)


    # AI 클라이언트 초기화
    try:
        ai_client = initialize_ai_client()
        logger.info(f"AI 클라이언트 초기화 완료: {ai_provider}")
    except Exception as e:
        logger.error(f"AI 클라이언트 초기화 실패: {e}")
        telegram_util.send_test_message(f"[news-tracker] 🚨 AI 클라이언트 초기화 실패: {str(e)}")
        return

    # RSS 피드 데이터 가져오기
    try:
        # 활성화된 RSS 피드 목록 가져오기
        active_feeds = api_util.get_active_rss_feeds()
        logger.info(f"활성화된 RSS 피드 수: {len(active_feeds)}")
        
        # 각 RSS 피드 처리
        for feed_info in active_feeds:
            logger.info(f"Processing feed: {feed_info['mq_company']} - {feed_info['mq_category']}")

            rss_data = fetch_rss_feed(feed_info['mq_rss'], api_util, feed_info)
            
            if rss_data and hasattr(rss_data, 'entries'):
                logger.info(f"Found {len(rss_data.entries)} valid entries from {feed_info['mq_company']}")
                
                # 각 뉴스 항목 처리
                for entry in rss_data.entries:
                    title = entry.title
                    published_date = time.localtime(time.mktime(entry.get('published_parsed', time.gmtime(0))) + 9 * 3600)
                    summary = entry.get('summary', '')
                    summary = clean_html(summary)  # HTML 태그 및 엔티티 제거

                    # AI 모델로 뉴스 분석
                    analysis_result = ai_client.get_response(
                        input_data={
                            'category': feed_info['mq_category'],
                            'title': title,
                            'summary': summary
                        },
                        prompt_path='step1_prompt.md'
                    )
                    
                    if analysis_result and analysis_result.parsed_data:
                        logger.info(f"제목: {title[:30]}... | 분석 결과: {analysis_result.parsed_data}")

                        if int(analysis_result.parsed_data['total_score']) >= 8:
                            api_util.insert_news({
                                'category': feed_info['mq_category'],
                                'title': title,
                                'content': summary,
                                'company': feed_info['mq_company'],
                                'source_url': entry.link,
                                'published': published_date,
                                'step1_score': analysis_result.parsed_data['total_score']
                            })
            else:
                logger.error(f"Failed to fetch RSS feed: {feed_info['mq_rss']}")

    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {e}", exc_info=True)
        telegram_util.send_test_message(f"[news-tracker] 🚨 예상치 못한 오류: {str(e)}")

    logger.info("RSS 뉴스 수집 프로그램 종료")

if __name__ == "__main__":
    main()
