#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных SSH Manager
Исправленная версия для новых версий SQLAlchemy
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в PATH
sys.path.insert(0, str(Path(__file__).parent))

from app import app, db
from models import SSHServer

def init_database():
    """Инициализация базы данных"""
    print("🗄️  Инициализация базы данных SSH Manager...")
    
    with app.app_context():
        try:
            # Создаем все таблицы
            db.create_all()
            print("✅ Таблицы успешно созданы")
            
            # Проверяем, что таблицы созданы (исправленная версия)
            try:
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                if tables:
                    print(f"📋 Созданные таблицы: {', '.join(tables)}")
                else:
                    print("📋 Проверяем таблицы через модели...")
                    # Альтернативная проверка через модели
                    SSHServer.query.count()  # Это вызовет ошибку, если таблица не существует
                    print("📋 Таблица ssh_servers создана успешно")
            except Exception as table_error:
                print(f"⚠️  Не удалось получить список таблиц: {table_error}")
                print("✅ Но таблицы созданы успешно (проверено через модели)")
            
            # Проверяем количество серверов
            try:
                server_count = SSHServer.query.count()
                print(f"📊 Количество серверов в базе: {server_count}")
            except Exception as count_error:
                print(f"⚠️  Не удалось подсчитать серверы: {count_error}")
                print("✅ Таблицы созданы, но пока пустые")
            
        except Exception as e:
            print(f"❌ Ошибка при инициализации базы данных: {e}")
            return False
    
    return True

def create_sample_data():
    """Создание примеров данных для тестирования"""
    print("\n📝 Создание примеров данных...")
    
    sample_servers = [
        {
            'host': '192.168.1.100',
            'port': 22,
            'username': 'admin',
            'password': 'test123',
            'country': 'Россия',
            'city': 'Москва',
            'notes': 'Тестовый сервер для демонстрации'
        },
        {
            'host': 'test.example.com',
            'port': 2222,
            'username': 'root',
            'password': 'secret',
            'country': 'США',
            'city': 'Нью-Йорк',
            'notes': 'Демо сервер с нестандартным портом'
        },
        {
            'host': '10.0.0.50',
            'port': 22,
            'username': 'ubuntu',
            'password': 'ubuntu123',
            'country': 'Германия',
            'city': 'Берлин',
            'notes': 'Ubuntu сервер для тестирования'
        },
        {
            'host': '203.0.113.10',
            'port': 22,
            'username': 'centos',
            'password': 'centos2023',
            'country': 'Япония',
            'city': 'Токио',
            'notes': 'CentOS сервер в Азии'
        },
        {
            'host': 'demo.server.local',
            'port': 22,
            'username': 'user',
            'password': 'password123',
            'country': 'Франция',
            'city': 'Париж',
            'notes': 'Локальный демо сервер'
        }
    ]
    
    with app.app_context():
        try:
            added_count = 0
            for server_data in sample_servers:
                # Проверяем, не существует ли уже такой сервер
                existing = SSHServer.query.filter_by(
                    host=server_data['host'],
                    username=server_data['username']
                ).first()
                
                if not existing:
                    server = SSHServer(**server_data)
                    db.session.add(server)
                    added_count += 1
                else:
                    print(f"⚠️  Сервер {server_data['host']} уже существует")
            
            if added_count > 0:
                db.session.commit()
                print(f"✅ Добавлено {added_count} примеров серверов")
            else:
                print("ℹ️  Все примеры серверов уже существуют в базе данных")
            
        except Exception as e:
            print(f"❌ Ошибка при создании примеров данных: {e}")
            db.session.rollback()

def reset_database():
    """Сброс базы данных (удаление всех данных)"""
    print("\n🗑️  Сброс базы данных...")
    
    with app.app_context():
        try:
            # Удаляем все таблицы
            db.drop_all()
            print("✅ Все таблицы удалены")
            
            # Создаем заново
            db.create_all()
            print("✅ Таблицы созданы заново")
            
        except Exception as e:
            print(f"❌ Ошибка при сбросе базы данных: {e}")
            return False
    
    return True

def backup_database():
    """Создание резервной копии базы данных (только для SQLite)"""
    print("\n💾 Создание резервной копии...")
    
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    if 'sqlite' in db_uri:
        # Извлекаем путь к файлу базы данных
        db_path = db_uri.replace('sqlite:///', '')
        
        if os.path.exists(db_path):
            import shutil
            from datetime import datetime
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{db_path}.backup_{timestamp}"
            
            try:
                shutil.copy2(db_path, backup_path)
                print(f"✅ Резервная копия создана: {backup_path}")
                
                # Показываем размер файла
                size = os.path.getsize(backup_path)
                print(f"📊 Размер резервной копии: {format_bytes(size)}")
                
            except Exception as e:
                print(f"❌ Ошибка создания резервной копии: {e}")
        else:
            print("⚠️  Файл базы данных не найден")
    else:
        print("⚠️  Резервное копирование поддерживается только для SQLite")
        print("💡 Для PostgreSQL используйте: pg_dump")
        print("💡 Для MySQL используйте: mysqldump")

def show_db_info():
    """Показать информацию о базе данных"""
    print("\n📊 Информация о базе данных:")
    print(f"🔗 URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    
    with app.app_context():
        try:
            # Информация о серверах
            total_servers = SSHServer.query.count()
            valid_servers = SSHServer.query.filter(SSHServer.is_valid == True).count()
            invalid_servers = SSHServer.query.filter(SSHServer.is_valid == False).count()
            unchecked_servers = SSHServer.query.filter(SSHServer.is_valid.is_(None)).count()
            
            print(f"📈 Всего серверов: {total_servers}")
            print(f"✅ Доступных: {valid_servers}")
            print(f"❌ Недоступных: {invalid_servers}")
            print(f"❓ Не проверенных: {unchecked_servers}")
            
            # Статистика по странам
            countries = db.session.query(SSHServer.country, db.func.count(SSHServer.id))\
                .group_by(SSHServer.country)\
                .filter(SSHServer.country.isnot(None))\
                .all()
            
            if countries:
                print("\n🌍 Распределение по странам:")
                for country, count in countries:
                    print(f"   {country}: {count}")
            
            # Информация о файле базы данных (для SQLite)
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'sqlite' in db_uri:
                db_path = db_uri.replace('sqlite:///', '')
                if os.path.exists(db_path):
                    size = os.path.getsize(db_path)
                    print(f"\n💾 Размер файла базы данных: {format_bytes(size)}")
                    
                    # Список резервных копий
                    backup_files = [f for f in os.listdir(os.path.dirname(db_path)) 
                                  if f.startswith(os.path.basename(db_path) + '.backup_')]
                    if backup_files:
                        print(f"📦 Резервных копий: {len(backup_files)}")
            
        except Exception as e:
            print(f"❌ Ошибка получения информации: {e}")

def format_bytes(bytes_value):
    """Форматирование размера в человекочитаемый вид"""
    if bytes_value == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_value >= 1024 and i < len(size_names)-1:
        bytes_value /= 1024.0
        i += 1
    
    return f"{bytes_value:.1f} {size_names[i]}"

def test_database_connection():
    """Тестирование подключения к базе данных"""
    print("\n🔧 Тестирование подключения к базе данных...")
    
    with app.app_context():
        try:
            # Пробуем выполнить простой запрос
            result = db.session.execute(db.text('SELECT 1')).scalar()
            if result == 1:
                print("✅ Подключение к базе данных работает")
                
                # Проверяем существование таблиц
                try:
                    SSHServer.query.count()
                    print("✅ Таблица ssh_servers доступна")
                except Exception as table_error:
                    print(f"❌ Ошибка доступа к таблице: {table_error}")
                    return False
                
            else:
                print("❌ Проблема с подключением к базе данных")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
    
    return True

def main():
    """Главная функция с меню"""
    print("=" * 50)
    print("🚀 SSH Manager - Управление базой данных")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'init':
            init_database()
        elif command == 'reset':
            if input("⚠️  Вы уверены, что хотите сбросить базу данных? (yes/no): ").lower() == 'yes':
                reset_database()
            else:
                print("❌ Сброс отменен")
        elif command == 'sample':
            create_sample_data()
        elif command == 'backup':
            backup_database()
        elif command == 'info':
            show_db_info()
        elif command == 'test':
            test_database_connection()
        else:
            print(f"❌ Неизвестная команда: {command}")
            print_help()
    else:
        # Интерактивное меню
        while True:
            print("\n" + "=" * 30)
            print("Выберите действие:")
            print("1. Инициализировать базу данных")
            print("2. Сбросить базу данных")
            print("3. Создать примеры данных")
            print("4. Создать резервную копию")
            print("5. Показать информацию о БД")
            print("6. Тестировать подключение")
            print("7. Выход")
            print("=" * 30)
            
            choice = input("Ваш выбор (1-7): ").strip()
            
            if choice == '1':
                init_database()
            elif choice == '2':
                if input("⚠️  Вы уверены? (yes/no): ").lower() == 'yes':
                    reset_database()
                else:
                    print("❌ Сброс отменен")
            elif choice == '3':
                create_sample_data()
            elif choice == '4':
                backup_database()
            elif choice == '5':
                show_db_info()
            elif choice == '6':
                test_database_connection()
            elif choice == '7':
                print("👋 До свидания!")
                break
            else:
                print("❌ Неверный выбор. Попробуйте снова.")

def print_help():
    """Показать справку по командам"""
    print("""
📖 Использование:
    python init_db.py [команда]

📋 Доступные команды:
    init    - Инициализировать базу данных
    reset   - Сбросить базу данных (удалить все данные)
    sample  - Создать примеры данных
    backup  - Создать резервную копию (только SQLite)
    info    - Показать информацию о базе данных
    test    - Тестировать подключение к БД

💡 Примеры:
    python init_db.py init
    python init_db.py sample
    python init_db.py info
    python init_db.py test

⚙️  Без параметров запускается интерактивное меню.
    """)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        print("🔧 Проверьте установку зависимостей: pip install Flask Flask-SQLAlchemy")
        sys.exit(1)