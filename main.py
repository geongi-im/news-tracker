import os
from dotenv import load_dotenv
import feedparser
from datetime import datetime, timedelta
import re
from html import unescape
import time
import logging
import json
from gemini_client import GeminiClient
from utils.api_util import ApiUtil, ApiError
from utils.logger_util import LoggerUtil

# .env 파일 로드
load_dotenv()

# 로거 초기화
logger = LoggerUtil().get_logger()

# Google API 관련 로깅 설정
for logger_name in ['google', 'google.auth', 'google.auth.transport', 'google.ai.generativelanguage', 'google.generativeai']:
    google_logger = logging.getLogger(logger_name)
    google_logger.setLevel(logging.ERROR)

# Gemini 클라이언트 초기화
gemini_client = GeminiClient(api_key=os.getenv('GOOGLE_API_KEY'))

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
            
            filtered_entries = []
            for entry in feed.entries:
                # 24시간 이내 뉴스만 필터링
                if not is_within_24_hours(entry.get('published_parsed')):
                    continue
                    
                title = entry.title
                summary = entry.get('summary', '')
                
                # 사진 기사 필터링
                if is_photo_only_news(title, summary):
                    logger.debug(f"사진 기사 건너뜀: {title}")
                    continue
                
                # 중복 체크
                if api_util.is_news_exists(entry.link):
                    logger.debug(f"중복된 뉴스 건너뜀: {title}")
                    continue
                    
                filtered_entries.append(entry)
            
            feed.entries = filtered_entries
            
        return feed
    except Exception as e:
        logger.error(f"RSS 피드 파싱 실패: {e}")
        return None

def is_photo_only_news(title, summary):
    """사진 기사 여부 확인"""
    # 제목에 '포토'가 포함되어 있거나 내용이 없는 경우
    return '포토' in title or not summary.strip()

def main():
    logger.info("RSS 뉴스 수집 프로그램 시작")
    
    # API 클라이언트 초기화
    api_util = ApiUtil()

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
                    summary = entry.get('summary', '')
                    summary = re.sub(r'<[^>]+>', '', summary)  # HTML 태그 제거

                    # Gemini로 뉴스 분석
                    analysis_result = gemini_client.get_response(
                        input_data={
                            'category': feed_info['mq_category'],
                            'title': title,
                            'summary': summary
                        },
                        model_id='gemini-1.5-flash-8b',
                        prompt_path='step1_prompt.md'
                    )
                    
                    if analysis_result:
                        logger.info(f"제목: {title[:30]}... | 분석 결과: {analysis_result.parsed_data}")

                        if int(analysis_result.parsed_data['total_score']) >= 8:
                            api_util.insert_news({
                                'category': feed_info['mq_category'],
                                'title': title,
                                'content': summary,
                                'company': feed_info['mq_company'],
                                'source_url': entry.link,
                                'published': entry.published_parsed,
                                'step1_score': analysis_result.parsed_data['total_score']
                            })
            else:
                logger.error(f"Failed to fetch RSS feed: {feed_info['mq_rss']}")

    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {e}", exc_info=True)

    logger.info("RSS 뉴스 수집 프로그램 종료")

if __name__ == "__main__":
    main()
