import requests
from utils.logger_util import LoggerUtil
import time

class ApiError(Exception):
    """API 호출 관련 커스텀 예외"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error (Status: {status_code}): {message}")

class ApiUtil:
    def __init__(self):
        self.base_url = "http://localhost/api"
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.logger = LoggerUtil().get_logger()

    def get_active_rss_feeds(self):
        """status가 1인 RSS 피드 목록 가져오기"""
        try:
            response = requests.get(f"{self.base_url}/news/rss", headers=self.headers)
            response.raise_for_status()
            
            response_data = response.json()
            if not response_data.get('success', False):
                error_msg = f"RSS 피드 조회 실패\n응답: {response.text}"
                self.logger.error(error_msg)
                raise ApiError(response.status_code, error_msg)
                
            self.logger.info(f"RSS 피드 조회 성공: {len(response_data.get('data', []))}개")
            return response_data.get('data', [])
            
        except requests.RequestException as err:
            error_msg = f"RSS 피드 조회 중 오류 발생: {str(err)}"
            self.logger.error(error_msg)
            raise ApiError(500, error_msg)

    def is_news_exists(self, source_url: str):
        """뉴스 URL 중복 체크"""
        try:
            response = requests.get(
                f"{self.base_url}/news/check",
                params={'url': source_url},
                headers=self.headers
            )
            response.raise_for_status()
            
            response_data = response.json()
            return response_data.get('exists', True)
            
        except requests.RequestException as err:
            error_msg = f"뉴스 중복 체크 중 오류 발생: {str(err)}"
            self.logger.error(error_msg)
            return True

    def insert_news(self, news_data: dict):
        """뉴스 데이터 저장"""
        try:
            payload = {
                'category': news_data.get('category', ''),
                'title': news_data.get('title', ''),
                'content': news_data.get('content', ''),
                'company': news_data.get('company', ''),
                'source_url': news_data.get('source_url', ''),
                'published_date': time.strftime('%Y-%m-%d %H:%M:%S', news_data['published']) if news_data.get('published') else None,
                'step1_score': int(news_data.get('step1_score', 0))
            }
            
            response = requests.post(
                f"{self.base_url}/news",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            
            response_data = response.json()
            if not response_data.get('success', False):
                error_msg = f"뉴스 저장 실패\n제목: {payload['title']}\n응답: {response.text}"
                self.logger.error(error_msg)
                raise ApiError(response.status_code, error_msg)
                
            self.logger.info(f"뉴스 저장 성공: {payload['title']}")
            return True
            
        except requests.RequestException as err:
            error_msg = f"뉴스 저장 중 오류 발생: {str(err)}"
            self.logger.error(error_msg)
            return False

if __name__ == "__main__":
    # 로거 초기화
    logger = LoggerUtil().get_logger()
    
    # API 테스트
    api = ApiUtil()
    
    # 테스트할 이미지 경로
    image_paths = [
        "img/opm_kospi_20241209.jpg",
        "img/opm_kosdaq_20241209.jpg"
    ]
    
    # 테스트 데이터
    test_data = {
        "title": "API 이미지 전송 테스트",
        "content": "이미지 전송 테스트를 위한 게시글입니다.",
        "category": "거래량",
        "writer": "테스터"
    }
    
    try:
        # API 호출 테스트
        result = api.create_post(
            title=test_data["title"],
            content=test_data["content"],
            category=test_data["category"],
            writer=test_data["writer"],
            image_paths=image_paths
        )
        logger.info(f"API 호출 결과: {result}")
        
    except ApiError as e:
        logger.error(f"API 에러 발생: {e}")
    except Exception as e:
        logger.error(f"예상치 못한 에러 발생: {e}") 