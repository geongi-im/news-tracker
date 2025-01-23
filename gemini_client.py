from pathlib import Path
import json
import logging
from google import genai
import time
from typing import Optional

class GeminiClient:
    def __init__(self, api_key, max_retries=3, retry_delay=5):
        """Gemini API 클라이언트 초기화
        Args:
            api_key (str): Gemini API 키
            max_retries (int): 최대 재시도 횟수
            retry_delay (int): 재시도 대기 시간(초)
        """
        self.logger = logging.getLogger(__name__)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Gemini API 클라이언트 초기화
        self.client = genai.Client(api_key=api_key)
        
        # 프롬프트 디렉토리 설정
        self.prompt_dir = Path('prompt')

    def _call_api_with_retry(self, model: str, contents: str) -> Optional[str]:
        """재시도 로직이 포함된 API 호출
        Args:
            model (str): 모델 ID
            contents (str): 프롬프트 내용
        Returns:
            Optional[str]: API 응답 또는 None
        """
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents
                )
                return response.text
            except Exception as e:
                error_message = str(e)
                if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
                    wait_time = self.retry_delay * (attempt + 1)  # 지수 백오프
                    self.logger.warning(f"API 할당량 초과. {wait_time}초 후 재시도... (시도 {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"API 호출 중 예상치 못한 오류 발생: {error_message}")
                    return None
                
        self.logger.error(f"최대 재시도 횟수({self.max_retries})를 초과했습니다.")
        return None

    def read_prompt_template(self, prompt_path):
        """프롬프트 파일 읽기"""
        try:
            prompt_file = self.prompt_dir / prompt_path
            if not prompt_file.exists():
                self.logger.error(f"프롬프트 파일을 찾을 수 없음: {prompt_file}")
                return None
                
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"프롬프트 파일 읽기 실패: {e}")
            return None
            
    def get_response(self, input_data, prompt_path, model_id):
        """Gemini API 호출 및 응답 처리
        Args:
            input_data (dict|str|list): 프롬프트에 추가할 입력 데이터
            prompt_path (str): 프롬프트 템플릿 파일 경로
            model_id (str): 사용할 Gemini 모델 ID
        Returns:
            dict: 파싱된 응답 또는 None
        """
        try:
            if not prompt_path:
                self.logger.error("프롬프트 경로가 지정되지 않음")
                return None
                
            if not model_id:
                self.logger.error("모델 ID가 지정되지 않음")
                return None
                
            # 프롬프트 템플릿 읽기
            template = self.read_prompt_template(prompt_path)
            if not template:
                return None
                
            # 입력 데이터 처리
            if isinstance(input_data, dict):
                input_text = "\n".join([f"{k}: {v}" for k, v in input_data.items()])
            elif isinstance(input_data, list):
                input_text = "\n".join(map(str, input_data))
            else:
                input_text = str(input_data)
            
            # 프롬프트와 입력 데이터 결합
            prompt = f"{template}\n\n{input_text}"
            
            # API 호출 (재시도 로직 포함)
            response_text = self._call_api_with_retry(model_id, prompt)
            
            if not response_text:
                return None
                
            # 응답 파싱
            return self._parse_response(response_text)
            
        except Exception as e:
            self.logger.error(f"요청 처리 실패: {str(e)}")
            self.logger.debug(f"상세 에러: {e}", exc_info=True)
            return None
            
    def _parse_response(self, response_text):
        """응답 텍스트 파싱
        Args:
            response_text (str): Gemini API 응답 텍스트
        Returns:
            dict: 파싱된 응답 또는 원본 텍스트
        """
        try:
            # 코드 블록 추출 (```로 시작하고 ```로 끝나는 부분)
            if '```' in response_text:
                # 첫 번째 코드 블록 찾기
                start_idx = response_text.find('```') + 3
                end_idx = response_text.find('```', start_idx)
                
                # 코드 블록 내용 추출
                code_block = response_text[start_idx:end_idx].strip()
                
                # json 접두사 제거
                if code_block.startswith('json\n'):
                    code_block = code_block[5:]
                
                # JSON 파싱
                return json.loads(code_block)
            
            # 코드 블록이 없는 경우 기존 로직 수행
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                return json.loads(cleaned_text)
            
            return {"raw_response": cleaned_text}
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 실패: {str(e)}")
            self.logger.debug(f"파싱 실패한 텍스트: {response_text}")
            return {"raw_response": response_text} 