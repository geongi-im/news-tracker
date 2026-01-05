from pathlib import Path
import json
from openai import OpenAI
from typing import Optional
from pydantic import BaseModel, Field, ValidationError
import os
from utils.logger_util import LoggerUtil

class DeepSeekResponse(BaseModel):
    """DeepSeek API 응답을 위한 Pydantic 모델"""
    raw_response: Optional[str] = Field(None, description="파싱되지 않은 원본 응답")
    parsed_data: Optional[dict] = Field(None, description="파싱된 JSON 데이터")
    error: Optional[str] = Field(None, description="에러 메시지")

class DeepSeekClient:
    def __init__(self, api_key, model_id, base_url=None):
        """DeepSeek API 클라이언트 초기화
        Args:
            api_key (str): DeepSeek API 키
            model_id (str): 사용할 DeepSeek 모델 ID (예: 'deepseek-chat')
            base_url (str): API base URL (기본값: 환경변수 또는 https://api.deepseek.com)
        """
        self.logger = LoggerUtil().get_logger()

        # 모델 ID 저장
        self.model_id = model_id

        # DeepSeek API 클라이언트 초기화 (OpenAI SDK 사용)
        self.base_url = base_url or os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        self.client = OpenAI(api_key=api_key, base_url=self.base_url)

        # 프롬프트 디렉토리 설정
        self.prompt_dir = Path('prompt')

    def _call_api(self, model: str, messages: list):
        """DeepSeek API 호출
        Args:
            model (str): 모델 ID (예: 'deepseek-chat')
            messages (list): OpenAI 형식의 메시지 리스트
        Returns:
            Optional[str]: API 응답 또는 None
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"}  # JSON 강제 출력
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"API 호출 실패: {str(e)}")
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

    def get_response(self, input_data, prompt_path):
        """DeepSeek API 호출 및 응답 처리
        Args:
            input_data (dict|str|list): 프롬프트에 추가할 입력 데이터
            prompt_path (str): 프롬프트 템플릿 파일 경로
        Returns:
            DeepSeekResponse: 파싱된 응답 또는 None
        """
        try:
            if not prompt_path:
                self.logger.error("프롬프트 경로가 지정되지 않음")
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
            user_prompt = f"{template}\n\n{input_text}"

            # OpenAI 메시지 형식으로 변환
            messages = [
                {"role": "system", "content": "You are a helpful assistant that analyzes Korean news articles and returns structured JSON responses."},
                {"role": "user", "content": user_prompt}
            ]

            # API 호출
            response_text = self._call_api(self.model_id, messages)

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
            response_text (str): DeepSeek API 응답 텍스트
        Returns:
            DeepSeekResponse: 파싱된 응답 모델
        """
        try:
            # JSON 강제 출력 모드를 사용하므로 직접 파싱 시도
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                parsed_data = json.loads(cleaned_text)
                return DeepSeekResponse(parsed_data=parsed_data)

            # 백업: 코드 블록 추출 (```로 시작하고 ```로 끝나는 부분)
            if '```' in response_text:
                start_idx = response_text.find('```') + 3
                end_idx = response_text.find('```', start_idx)

                code_block = response_text[start_idx:end_idx].strip()

                # json 접두사 제거
                if code_block.startswith('json\n'):
                    code_block = code_block[5:]

                parsed_data = json.loads(code_block)
                return DeepSeekResponse(parsed_data=parsed_data)

            return DeepSeekResponse(raw_response=cleaned_text)

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 실패: {str(e)}")
            self.logger.debug(f"파싱 실패한 텍스트: {response_text}")
            return DeepSeekResponse(
                raw_response=response_text,
                error=f"JSON 파싱 실패: {str(e)}"
            )
        except ValidationError as e:
            self.logger.error(f"Pydantic 검증 실패: {str(e)}")
            return DeepSeekResponse(
                raw_response=response_text,
                error=f"데이터 검증 실패: {str(e)}"
            )
