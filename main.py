import os
import pymysql
from dotenv import load_dotenv
import feedparser
from datetime import datetime, timedelta
import re
from html import unescape
import time
import logging
from pathlib import Path
import json
from gemini_client import GeminiClient

# .env 파일 로드
load_dotenv()

# AFC 메시지 필터 클래스
class AFCFilter(logging.Filter):
    def filter(self, record):
        return "AFC is enabled" not in record.getMessage()

# 로그 디렉토리 생성
log_dir = Path('log')
log_dir.mkdir(exist_ok=True)

# 로그 파일 설정
log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}_log.log"

# 기본 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # 콘솔에도 출력
    ]
)

# AFC 필터 적용
for handler in logging.root.handlers:
    handler.addFilter(AFCFilter())

# Google API 관련 로깅 설정
for logger_name in ['google', 'google.auth', 'google.auth.transport', 'google.ai.generativelanguage', 'google.generativeai']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.ERROR)
    for handler in logger.handlers + logging.root.handlers:
        handler.addFilter(AFCFilter())

logger = logging.getLogger(__name__)

# Gemini 클라이언트 초기화
gemini_client = GeminiClient(api_key=os.getenv('GOOGLE_API_KEY'))

def connect_to_database():
    """MySQL 데이터베이스 연결"""
    try:
        connection =    pymysql.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE'),
            port=int(os.getenv('MYSQL_PORT')),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        logger.info("데이터베이스 연결 성공")
        return connection
    except pymysql.Error as err:
        logger.error(f"데이터베이스 연결 실패: {err}")
        return None

def get_active_rss_feeds(connection):
    """status가 1인 RSS 피드 목록 가져오기"""
    try:
        with connection.cursor() as cursor:
            query = "SELECT * FROM mq_news_rss WHERE mq_status = 1"
            cursor.execute(query)
            feeds = cursor.fetchall()
            return feeds
    except pymysql.Error as err:
        print(f"RSS 피드 조회 실패: {err}")
        return []

def is_news_exists(connection, source_url):
    """뉴스 URL 중복 체크"""
    try:
        with connection.cursor() as cursor:
            query = "SELECT COUNT(*) as count FROM mq_news WHERE mq_source_url = %s"
            cursor.execute(query, (source_url,))
            result = cursor.fetchone()
            return result['count'] > 0
    except pymysql.Error as err:
        print(f"중복 체크 실패: {err}")
        return True

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

def insert_news(connection, news_data):
    """뉴스 데이터 저장"""
    try:
        with connection.cursor() as cursor:
            query = """
                INSERT INTO mq_news (
                    mq_category, mq_title, mq_content, 
                    mq_company, mq_source_url,
                    mq_reg_date, mq_published_date, mq_step1_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            # published_parsed를 datetime 문자열로 변환
            published_date = None
            if news_data.get('published'):
                published_date = time.strftime('%Y-%m-%d %H:%M:%S', news_data['published'])

            title = clean_text(news_data.get('title', ''))
            summary = clean_text(news_data.get('summary', ''))
            step1_score = int(news_data.get('step1_score', 0))  # mq_step1_score 값을 int로 변환
            cursor.execute(query, (
                news_data.get('category', ''),
                title,
                summary,
                news_data.get('company', ''),
                news_data.get('link', ''),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                published_date,
                step1_score
            ))
            connection.commit()
            logger.info(f"뉴스 저장 성공: {title}")
            return True
    except pymysql.Error as err:
        logger.error(f"뉴스 저장 실패: {err}")
        connection.rollback()
        return False

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

def fetch_rss_feed(feed_url, connection, feed_info):
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
                if is_news_exists(connection, entry.link):
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

def update_rss_feed_update_time(connection, feed_id):
    """RSS 피드 최종 업데이트 시간 기록"""
    try:
        with connection.cursor() as cursor:
            query = "UPDATE mq_news_rss SET mq_update_date = NOW() WHERE idx = %s"
            cursor.execute(query, (feed_id,))
            connection.commit()
            logger.info(f"RSS 피드 업데이트 시간 갱신 성공: ID {feed_id}")
    except pymysql.Error as err:
        logger.error(f"RSS 피드 업데이트 시간 갱신 실패: {err}")
        connection.rollback()

def main():
    logger.info("RSS 뉴스 수집 프로그램 시작")
    
    # 데이터베이스 연결
    connection = connect_to_database()
    if not connection:
        return

    try:
        # 활성화된 RSS 피드 목록 가져오기
        active_feeds = get_active_rss_feeds(connection)
        logger.info(f"활성화된 RSS 피드 수: {len(active_feeds)}")
        
        # 각 RSS 피드 처리
        for feed_info in active_feeds:
            logger.info(f"Processing feed: {feed_info['mq_company']} - {feed_info['mq_category']}")
            rss_data = fetch_rss_feed(feed_info['mq_rss'], connection, feed_info)
            
            if rss_data and hasattr(rss_data, 'entries'):
                logger.info(f"Found {len(rss_data.entries)} valid entries from {feed_info['mq_company']}")
                
                # 각 뉴스 항목 처리
                for entry in rss_data.entries:
                    title = entry.title
                    summary = entry.get('summary', '')

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

                        if analysis_result.parsed_data['total_score'] >= 8:
                            insert_news(connection, {
                                'category': feed_info['mq_category'],
                                'title': title,
                                'summary': summary,
                                'company': feed_info['mq_company'],
                                'link': entry.link,
                                'published': entry.published_parsed,
                                'step1_score': analysis_result.parsed_data['total_score']
                            })

                # 해당 RSS 피드의 모든 항목 처리 완료 후 업데이트
                update_rss_feed_update_time(connection, feed_info['idx'])
            else:
                logger.error(f"Failed to fetch RSS feed: {feed_info['mq_rss']}")

    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {e}", exc_info=True)
    finally:
        connection.close()
        logger.info("RSS 뉴스 수집 프로그램 종료")

if __name__ == "__main__":
    main()
