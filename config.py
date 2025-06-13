import os
from pathlib import Path

# Базовая директория проекта
basedir = Path(__file__).parent.absolute()

class Config:
    """Базовая конфигурация"""
    
    # Безопасность
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-me-in-production'
    
    # SQLAlchemy настройки
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    
    # SSH Manager настройки
    SSH_TIMEOUT = int(os.environ.get('SSH_TIMEOUT', 10))
    SSH_MAX_WORKERS = int(os.environ.get('SSH_MAX_WORKERS', 20))
    
    # Загрузка файлов
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = basedir / 'uploads'
    
    # Создаем необходимые директории
    @staticmethod
    def init_app(app):
        # Создаем папки если их нет
        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        upload_dir.mkdir(exist_ok=True)
        
        db_dir = basedir / 'database'
        db_dir.mkdir(exist_ok=True)
        
        logs_dir = basedir / 'logs'
        logs_dir.mkdir(exist_ok=True)

class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    
    DEBUG = True
    
    # SQLite для разработки
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        f'sqlite:///{basedir}/database/ssh_servers_dev.db'
    
    # Логирование запросов SQL
    SQLALCHEMY_ECHO = False  # Установить True для отладки SQL

class TestingConfig(Config):
    """Конфигурация для тестирования"""
    
    TESTING = True
    WTF_CSRF_ENABLED = False
    
    # In-memory база для тестов
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    
    DEBUG = False
    
    # PostgreSQL для продакшена (по умолчанию)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{basedir}/database/ssh_servers.db'
    
    # SSL для PostgreSQL в продакшене
    if os.environ.get('DATABASE_URL') and 'postgresql' in os.environ.get('DATABASE_URL'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_timeout': 20,
            'pool_recycle': -1,
            'pool_pre_ping': True
        }
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Логирование в файл в продакшене
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not app.debug and not app.testing:
            if not (basedir / 'logs').exists():
                (basedir / 'logs').mkdir()
            
            file_handler = RotatingFileHandler(
                basedir / 'logs' / 'ssh_manager.log',
                maxBytes=10240000,
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s '
                '[in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('SSH Manager startup')

class DockerConfig(ProductionConfig):
    """Конфигурация для Docker контейнера"""
    
    @classmethod
    def init_app(cls, app):
        ProductionConfig.init_app(app)
        
        # Логирование в stdout для Docker
        import logging
        
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        app.logger.addHandler(stream_handler)

# Словарь конфигураций
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'docker': DockerConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Получить текущую конфигурацию на основе переменной окружения"""
    return config.get(os.environ.get('FLASK_CONFIG', 'default'))