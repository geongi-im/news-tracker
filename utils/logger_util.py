import logging
from pathlib import Path
from datetime import datetime

class LoggerUtil:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerUtil, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not LoggerUtil._initialized:
            # 로그 디렉토리 생성
            log_dir = Path('log')
            log_dir.mkdir(exist_ok=True)

            # 로그 파일 설정
            log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}_log.log"

            # 로거 생성
            self.logger = logging.getLogger('MQLogger')
            self.logger.setLevel(logging.INFO)

            # 이미 핸들러가 있다면 제거
            if self.logger.handlers:
                self.logger.handlers.clear()

            # 파일 핸들러
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)

            # 콘솔 핸들러
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            # 포맷터 설정
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)

            # 핸들러 추가
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

            LoggerUtil._initialized = True

    def get_logger(self):
        return self.logger 