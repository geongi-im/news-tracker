# news-tracker
RSS기반에 뉴스를 수집하여 AI가 판단하여 저장하는 프로젝트

## 환경 설정

1. Python 가상환경 설정
   ```bash
   # 가상환경 생성
   python -m venv venv

   # 가상환경 활성화
   # Windows
   .\venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

2. 환경 변수 설정
   - `.env.sample` 파일을 `.env`로 복사합니다.
   ```bash
   cp .env.sample .env
   ```
   - `.env` 파일을 열어 실제 값으로 수정합니다:
     - `GOOGLE_API_KEY`: Google Gemini API 키
     - `BASE_URL`: API 저장할 서버 주소

3. 필요한 패키지 설치
   ```bash
   pip install -r requirements.txt
   ```

## 실행 방법
1. 가상환경이 활성화되어 있는지 확인
2. 다음 명령어로 프로그램 실행
   ```bash
   python main.py
   ```

#https://github.com/googleapis/python-genai