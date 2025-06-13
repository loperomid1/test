import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime

def setup_logging(app=None, log_level='INFO'):
    """
    Настройка системы логирования для SSH Manager
    
    Args:
        app: Flask приложение (опционально)
        log_level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
    """
    
    # Создаем директорию для логов
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Настройка форматтера
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Основной логгер приложения
    app_logger = logging.getLogger('ssh_manager')
    app_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Файловый обработчик с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'ssh_manager.log',
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Обработчик для ошибок
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'ssh_manager_errors.log',
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Добавляем обработчики
    app_logger.addHandler(file_handler)
    app_logger.addHandler(error_handler)
    app_logger.addHandler(console_handler)
    
    # Настройка логгера SSH операций
    ssh_logger = logging.getLogger('ssh_operations')
    ssh_logger.setLevel(logging.INFO)
    
    ssh_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'ssh_operations.log',
        maxBytes=20*1024*1024,  # 20 MB
        backupCount=10,
        encoding='utf-8'
    )
    ssh_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    ssh_handler.setFormatter(ssh_formatter)
    ssh_logger.addHandler(ssh_handler)
    
    # Логгер для валидации серверов
    validation_logger = logging.getLogger('validation')
    validation_logger.setLevel(logging.INFO)
    
    validation_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'validation.log',
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    validation_handler.setFormatter(ssh_formatter)
    validation_logger.addHandler(validation_handler)
    
    # Подавляем verbose логи от библиотек
    logging.getLogger('paramiko').setLevel(logging.WARNING)
    logging.getLogger('paramiko.transport').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # Интеграция с Flask если передан app
    if app:
        app.logger.handlers.clear()
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        app.logger.setLevel(getattr(logging, log_level.upper()))
    
    app_logger.info("Система логирования инициализирована")
    return app_logger

def log_ssh_operation(host, port, username, operation, result, error=None, duration=None):
    """
    Логирование SSH операций
    
    Args:
        host: хост сервера
        port: порт
        username: имя пользователя
        operation: тип операции (validate, command, system_info)
        result: результат операции (success, failed)
        error: текст ошибки (если есть)
        duration: время выполнения в секундах
    """
    logger = logging.getLogger('ssh_operations')
    
    log_entry = f"HOST:{host}:{port} USER:{username} OP:{operation} RESULT:{result}"
    
    if duration:
        log_entry += f" TIME:{duration:.2f}s"
    
    if error:
        log_entry += f" ERROR:{error}"
    
    if result == 'success':
        logger.info(log_entry)
    else:
        logger.warning(log_entry)

def log_validation_batch(total_servers, successful, failed, duration, threads, timeout):
    """
    Логирование пакетной валидации
    
    Args:
        total_servers: общее количество серверов
        successful: количество успешных проверок
        failed: количество неудачных проверок
        duration: время выполнения в секундах
        threads: количество потоков
        timeout: таймаут подключения
    """
    logger = logging.getLogger('validation')
    
    success_rate = (successful / total_servers * 100) if total_servers > 0 else 0
    servers_per_second = (total_servers / duration) if duration > 0 else 0
    
    log_entry = (
        f"BATCH_VALIDATION: "
        f"TOTAL:{total_servers} SUCCESS:{successful} FAILED:{failed} "
        f"RATE:{success_rate:.1f}% SPEED:{servers_per_second:.2f}srv/s "
        f"TIME:{duration:.2f}s THREADS:{threads} TIMEOUT:{timeout}s"
    )
    
    logger.info(log_entry)

def log_command_execution(servers_count, command, successful, failed, duration, threads):
    """
    Логирование выполнения команд
    
    Args:
        servers_count: количество серверов
        command: выполненная команда
        successful: количество успешных выполнений
        failed: количество неудачных выполнений
        duration: время выполнения
        threads: количество потоков
    """
    logger = logging.getLogger('ssh_operations')
    
    # Обрезаем очень длинные команды для лога
    cmd_preview = command[:50] + "..." if len(command) > 50 else command
    
    log_entry = (
        f"COMMAND_BATCH: "
        f"CMD:'{cmd_preview}' SERVERS:{servers_count} "
        f"SUCCESS:{successful} FAILED:{failed} "
        f"TIME:{duration:.2f}s THREADS:{threads}"
    )
    
    logger.info(log_entry)

def get_log_stats():
    """
    Получение статистики логов
    
    Returns:
        dict: статистика файлов логов
    """
    log_dir = Path('logs')
    stats = {}
    
    if log_dir.exists():
        for log_file in log_dir.glob('*.log'):
            try:
                stat = log_file.stat()
                stats[log_file.name] = {
                    'size_mb': round(stat.st_size / (1024*1024), 2),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                }
            except Exception as e:
                stats[log_file.name] = {'error': str(e)}
    
    return stats

class SSHLoggerAdapter:
    """
    Адаптер для удобного логирования SSH операций
    """
    
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.logger = logging.getLogger('ssh_operations')
    
    def log_connection_attempt(self):
        self.logger.debug(f"Attempting connection to {self.username}@{self.host}:{self.port}")
    
    def log_connection_success(self, duration):
        log_ssh_operation(self.host, self.port, self.username, 'connect', 'success', duration=duration)
    
    def log_connection_failed(self, error, duration):
        log_ssh_operation(self.host, self.port, self.username, 'connect', 'failed', error=error, duration=duration)
    
    def log_command_execution(self, command, success, error=None, duration=None):
        result = 'success' if success else 'failed'
        # Обрезаем команду для лога
        cmd_preview = command[:30] + "..." if len(command) > 30 else command
        log_ssh_operation(
            self.host, self.port, self.username, 
            f'command:{cmd_preview}', result, error=error, duration=duration
        )
    
    def log_system_info_collection(self, success, error=None, duration=None):
        result = 'success' if success else 'failed'
        log_ssh_operation(
            self.host, self.port, self.username, 
            'system_info', result, error=error, duration=duration
        )

# Функция для очистки старых логов
def cleanup_logs(days_to_keep=30):
    """
    Очистка старых файлов логов
    
    Args:
        days_to_keep: количество дней для хранения логов
    """
    log_dir = Path('logs')
    if not log_dir.exists():
        return
    
    import time
    cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
    
    for log_file in log_dir.glob('*.log.*'):  # Ротированные файлы
        try:
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
                logging.getLogger('ssh_manager').info(f"Удален старый лог файл: {log_file.name}")
        except Exception as e:
            logging.getLogger('ssh_manager').error(f"Ошибка удаления лог файла {log_file.name}: {e}")

# Настройки для разных окружений
LOG_CONFIGS = {
    'development': {
        'level': 'DEBUG',
        'console': True,
        'file': True
    },
    'production': {
        'level': 'INFO',
        'console': False,
        'file': True
    },
    'testing': {
        'level': 'WARNING',
        'console': True,
        'file': False
    }
}