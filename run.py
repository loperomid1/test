#!/usr/bin/env python3
"""
SSH Manager - Скрипт запуска приложения
Исправленная версия для новых версий SQLAlchemy
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в PATH
sys.path.insert(0, str(Path(__file__).parent))

try:
    from app import app
    from models import db
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("🔧 Убедитесь, что установлены все зависимости: pip install -r requirements.txt")
    sys.exit(1)

def load_env():
    """Загрузка переменных окружения из .env файла"""
    env_file = Path('.env')
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("✅ Переменные окружения загружены из .env")
        except ImportError:
            print("⚠️  python-dotenv не установлен. Установите: pip install python-dotenv")
        except Exception as e:
            print(f"⚠️  Ошибка загрузки .env файла: {e}")
    else:
        print("ℹ️  Файл .env не найден. Используются значения по умолчанию.")

def check_database():
    """Проверка и инициализация базы данных"""
    with app.app_context():
        try:
            # Проверяем подключение к БД (исправленная версия)
            from sqlalchemy import text
            result = db.session.execute(text('SELECT 1')).scalar()
            
            if result != 1:
                print("❌ Проблема с подключением к базе данных")
                return False
            
            # Проверяем существование таблиц (исправленная версия)
            try:
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                
                if 'ssh_servers' not in tables:
                    print("🗄️  Таблицы не найдены. Инициализируем базу данных...")
                    db.create_all()
                    print("✅ База данных инициализирована")
                else:
                    print("✅ База данных готова к работе")
            except Exception as table_error:
                print("🗄️  Проверяем таблицы через модели...")
                try:
                    from models import SSHServer
                    SSHServer.query.count()
                    print("✅ База данных готова к работе")
                except Exception as model_error:
                    print("🗄️  Таблицы не найдены. Инициализируем базу данных...")
                    db.create_all()
                    print("✅ База данных инициализирована")
                
        except Exception as e:
            print(f"❌ Ошибка базы данных: {e}")
            print("🔧 Попробуйте запустить: python init_db.py init")
            return False
    
    return True

def show_config_info():
    """Показать информацию о конфигурации"""
    config_name = os.environ.get('FLASK_CONFIG', 'default')
    debug_mode = app.config.get('DEBUG', False)
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'не настроена')
    
    print("\n" + "="*50)
    print("🚀 SSH Manager - Информация о запуске")
    print("="*50)
    print(f"📋 Конфигурация: {config_name}")
    print(f"🐛 Режим отладки: {'Включен' if debug_mode else 'Отключен'}")
    print(f"🗄️  База данных: {db_uri}")
    print(f"🔧 SSH таймаут: {app.config.get('SSH_TIMEOUT', 10)} сек")
    print(f"⚡ Макс. подключений: {app.config.get('SSH_MAX_WORKERS', 20)}")
    print("="*50)

def check_dependencies():
    """Проверка установленных зависимостей"""
    required_packages = ['flask', 'flask_sqlalchemy', 'paramiko', 'requests']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Отсутствуют пакеты: {', '.join(missing_packages)}")
        print("🔧 Установите их: pip install " + " ".join(missing_packages))
        return False
    
    return True

def create_directories():
    """Создание необходимых директорий"""
    directories = ['uploads', 'database', 'logs']
    
    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            dir_path.mkdir(exist_ok=True)
            print(f"📁 Создана директория: {directory}")

def main():
    """Главная функция запуска"""
    print("🚀 Запуск SSH Manager...")
    
    # Проверяем зависимости
    if not check_dependencies():
        sys.exit(1)
    
    # Создаем необходимые директории
    create_directories()
    
    # Загружаем переменные окружения
    load_env()
    
    # Показываем информацию о конфигурации
    show_config_info()
    
    # Проверяем базу данных
    if not check_database():
        sys.exit(1)
    
    # Получаем настройки запуска
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = app.config.get('DEBUG', False)
    
    print(f"\n🌐 Приложение будет доступно по адресу: http://{host}:{port}")
    
    if debug:
        print("⚠️  ВНИМАНИЕ: Режим отладки включен. Не используйте в продакшене!")
    
    print("\n🔥 Запуск сервера...")
    print("   Для остановки нажмите Ctrl+C")
    print("="*50)
    
    try:
        # Запускаем приложение
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n\n👋 Остановка сервера...")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n❌ Порт {port} уже используется!")
            print("🔧 Попробуйте:")
            print(f"   1. Изменить порт в .env файле")
            print(f"   2. Остановить другое приложение на порту {port}")
            print(f"   3. Использовать другой порт: set FLASK_PORT=5001 && python run.py")
        else:
            print(f"\n❌ Ошибка сети: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()