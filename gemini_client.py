from pathlib import Path
import json
from google import genai
from google.genai import types
import time
from typing import Optional
from pydantic import BaseModel, Field, ValidationError
import os
from utils.logger_util import LoggerUtil

class GeminiResponse(BaseModel):
    """Gemini API 응답을 위한 Pydantic 모델"""
    raw_response: Optional[str] = Field(None, description="파싱되지 않은 원본 응답")
    parsed_data: Optional[dict] = Field(None, description="파싱된 JSON 데이터")
    error: Optional[str] = Field(None, description="에러 메시지")

class GeminiClient:
    def __init__(self, api_key, max_retries=os.getenv('MAX_RETRIES', 3), 
                 retry_delay=os.getenv('RETRY_DELAY', 5),
                 success_delay=os.getenv('SUCCESS_DELAY', 3)):
        """Gemini API 클라이언트 초기화
        Args:
            api_key (str): Gemini API 키
            max_retries (int): 최대 재시도 횟수
            retry_delay (int): 재시도 대기 시간(초)
            success_delay (int): 성공 시 대기 시간(초)
        """
        self.logger = LoggerUtil().get_logger()
        self.max_retries = int(max_retries)
        self.retry_delay = int(retry_delay)
        self.success_delay = int(success_delay)
        
        # Gemini API 클라이언트 초기화
        self.client = genai.Client(api_key=api_key)
        
        # 프롬프트 디렉토리 설정
        self.prompt_dir = Path('prompt')

        self.config = types.GenerateContentConfig(
            response_mime_type="application/json"
        )

    def _call_api_with_retry(self, model: str, contents: str):
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
                    contents=contents,
                    config=self.config
                )
                result = response.text
                # 성공 시 3초 대기 (API 서버 부하 방지)
                time.sleep(self.success_delay)
                return result
            except Exception as e:
                error_message = str(e)
                # 503(UNAVAILABLE) 및 429(RESOURCE_EXHAUSTED) 모두 처리
                if any(err in error_message for err in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                    wait_time = self.retry_delay * (2 ** attempt)  # 지수 백오프(5, 10, 20초...)
                    self.logger.warning(f"API 서버 과부하. {wait_time}초 후 재시도... (시도 {attempt + 1}/{self.max_retries})")
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
            
    def _parse_response(self, response_text: str):
        """응답 텍스트 파싱
        Args:
            response_text (str): Gemini API 응답 텍스트
        Returns:
            GeminiResponse: 파싱된 응답 모델
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
                
                # JSON 파싱 및 Pydantic 모델 변환
                parsed_data = json.loads(code_block)
                return GeminiResponse(parsed_data=parsed_data)
            
            # 코드 블록이 없는 경우
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                parsed_data = json.loads(cleaned_text)
                return GeminiResponse(parsed_data=parsed_data)
            
            return GeminiResponse(raw_response=cleaned_text)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 실패: {str(e)}")
            self.logger.debug(f"파싱 실패한 텍스트: {response_text}")
            return GeminiResponse(
                raw_response=response_text,
                error=f"JSON 파싱 실패: {str(e)}"
            )
        except ValidationError as e:
            self.logger.error(f"Pydantic 검증 실패: {str(e)}")
            return GeminiResponse(
                raw_response=response_text,
                error=f"데이터 검증 실패: {str(e)}"
            ) 