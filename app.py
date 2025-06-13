from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from pathlib import Path
from models import SSHServer, db
from ssh_manager import SSHManager
from utils import parse_ssh_file, get_server_geo
from context_utils import init_context_utils, task_manager, with_app_context
import threading
import time

# Создаем приложение
app = Flask(__name__)

# Получаем базовую директорию проекта
basedir = Path(__file__).parent.absolute()

# Конфигурация приложения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me-in-production')

# Создаем абсолютный путь к базе данных (для разработки)
db_dir = basedir / 'database'
db_dir.mkdir(exist_ok=True)
db_path = db_dir / 'ssh_servers_dev.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Создаем папку для загрузок
upload_dir = basedir / 'uploads'
upload_dir.mkdir(exist_ok=True)
app.config['UPLOAD_FOLDER'] = str(upload_dir)

# Создаем папку для логов
logs_dir = basedir / 'logs'
logs_dir.mkdir(exist_ok=True)

print(f"📊 Используется база данных: {db_path}")
print(f"📁 Папка загрузок: {upload_dir}")

db.init_app(app)

# Инициализируем утилиты контекста
init_context_utils(app)

# Глобальные переменные для отслеживания статуса операций
validation_status = {
    'running': False, 
    'progress': 0, 
    'total': 0, 
    'results': [], 
    'threads': 10,
    'timeout': 15,
    'start_time': None,
    'estimated_time': None
}
command_status = {
    'running': False, 
    'progress': 0, 
    'total': 0, 
    'results': [], 
    'threads': 10,
    'timeout': 15,
    'start_time': None,
    'estimated_time': None
}

# Инициализируем SSH Manager с дефолтными настройками
ssh_manager = SSHManager(max_workers=10, timeout=15)

@app.route('/')
def index():
    """Главная страница с обзором серверов"""
    servers = SSHServer.query.all()
    stats = {
        'total': len(servers),
        'valid': len([s for s in servers if s.is_valid]),
        'invalid': len([s for s in servers if not s.is_valid]),
        'unchecked': len([s for s in servers if s.is_valid is None])
    }
    return render_template('index.html', servers=servers, stats=stats)

@app.route('/servers')
def servers():
    """Страница со списком серверов"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Фильтры
    status_filter = request.args.get('status', 'all')
    country_filter = request.args.get('country', 'all')
    os_filter = request.args.get('os', 'all')
    search = request.args.get('search', '')
    
    # Сортировка
    sort_by = request.args.get('sort', 'host')
    sort_order = request.args.get('order', 'asc')
    
    query = SSHServer.query
    
    # Применяем фильтры
    if status_filter == 'valid':
        query = query.filter(SSHServer.is_valid == True)
    elif status_filter == 'invalid':
        query = query.filter(SSHServer.is_valid == False)
    elif status_filter == 'unchecked':
        query = query.filter(SSHServer.is_valid == None)
    
    if country_filter != 'all':
        query = query.filter(SSHServer.country == country_filter)
    
    if os_filter != 'all':
        query = query.filter(SSHServer.os_info.contains(os_filter))
    
    if search:
        query = query.filter(SSHServer.host.contains(search))
    
    # Применяем сортировку
    sort_column = getattr(SSHServer, sort_by, SSHServer.host)
    if sort_order == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    servers = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Получаем уникальные значения для фильтров
    countries = db.session.query(SSHServer.country).distinct().all()
    countries = [c[0] for c in countries if c[0]]
    
    # Получаем уникальные ОС
    os_systems = db.session.query(SSHServer.os_info).filter(SSHServer.os_info.isnot(None)).distinct().all()
    os_list = []
    for os_info in os_systems:
        if os_info[0]:
            os_lower = os_info[0].lower()
            if 'ubuntu' in os_lower and 'Ubuntu' not in os_list:
                os_list.append('Ubuntu')
            elif 'debian' in os_lower and 'Debian' not in os_list:
                os_list.append('Debian')
            elif 'centos' in os_lower and 'CentOS' not in os_list:
                os_list.append('CentOS')
            elif 'red hat' in os_lower and 'RHEL' not in os_list:
                os_list.append('RHEL')
            elif 'fedora' in os_lower and 'Fedora' not in os_list:
                os_list.append('Fedora')
    
    return render_template('servers.html', 
                         servers=servers, 
                         countries=countries,
                         os_list=os_list,
                         current_status=status_filter,
                         current_country=country_filter,
                         current_os=os_filter,
                         current_search=search,
                         current_sort=sort_by,
                         current_order=sort_order)

@app.route('/map')
def map_view():
    """Страница с картой серверов"""
    servers = SSHServer.query.filter(
        SSHServer.latitude.isnot(None),
        SSHServer.longitude.isnot(None)
    ).all()
    
    servers_data = []
    for server in servers:
        servers_data.append({
            'id': server.id,
            'host': server.host,
            'port': server.port,
            'country': server.country,
            'city': server.city,
            'latitude': server.latitude,
            'longitude': server.longitude,
            'is_valid': server.is_valid,
            'last_check': server.last_check.isoformat() if server.last_check else None
        })
    
    return render_template('map.html', servers=servers_data)

@app.route('/upload', methods=['GET', 'POST'])
def upload_servers():
    """Загрузка серверов из файла"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                servers_data = parse_ssh_file(filepath)
                added_count = 0
                
                for server_data in servers_data:
                    # Проверяем, не существует ли уже такой сервер
                    existing = SSHServer.query.filter_by(
                        host=server_data['host'],
                        port=server_data['port'],
                        username=server_data['username']
                    ).first()
                    
                    if not existing:
                        server = SSHServer(**server_data)
                        # Получаем геоданные
                        try:
                            geo_data = get_server_geo(server_data['host'])
                            if geo_data:
                                server.country = geo_data.get('country')
                                server.city = geo_data.get('city')
                                server.latitude = geo_data.get('latitude')
                                server.longitude = geo_data.get('longitude')
                        except Exception as geo_error:
                            print(f"Ошибка получения геоданных для {server_data['host']}: {geo_error}")
                            # Продолжаем без геоданных
                        
                        db.session.add(server)
                        added_count += 1
                
                db.session.commit()
                flash(f'Успешно добавлено {added_count} серверов', 'success')
                
            except Exception as e:
                flash(f'Ошибка при обработке файла: {str(e)}', 'error')
                db.session.rollback()
            
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
    
    return render_template('upload.html')

@app.route('/validate', methods=['POST'])
def validate_servers():
    """Запуск валидации серверов с настройками потоков"""
    global validation_status, ssh_manager
    
    if validation_status['running']:
        return jsonify({'error': 'Валидация уже запущена'})
    
    data = request.json or {}
    server_ids = data.get('server_ids', [])
    threads = int(data.get('threads', 10))
    timeout = int(data.get('timeout', 15))
    
    # Валидация настроек
    threads = max(1, min(threads, 100))  # От 1 до 100 потоков
    timeout = max(5, min(timeout, 60))   # От 5 до 60 секунд
    
    if not server_ids:
        servers = SSHServer.query.all()
        server_ids = [s.id for s in servers]
    
    # Обновляем SSH Manager с новыми настройками
    ssh_manager = SSHManager(max_workers=threads, timeout=timeout)
    
    validation_status = {
        'running': True,
        'progress': 0,
        'total': len(server_ids),
        'results': [],
        'threads': threads,
        'timeout': timeout,
        'start_time': datetime.now(),
        'estimated_time': None
    }
    
    def validate_thread():
        global validation_status
        
        # ВАЖНО: Создаем контекст приложения для фонового потока
        with app.app_context():
            try:
                processed = 0
                start_time = time.time()
                
                # Подготавливаем данные серверов для валидации
                batch_servers = []
                for server_id in server_ids:
                    try:
                        server = SSHServer.query.get(server_id)
                        if server:
                            batch_servers.append((
                                server_id,
                                server.host,
                                server.port,
                                server.username,
                                server.password
                            ))
                    except Exception as db_error:
                        print(f"Ошибка получения сервера {server_id} из БД: {db_error}")
                        continue
                
                if not batch_servers:
                    validation_status['running'] = False
                    print("Нет серверов для валидации")
                    return
                
                validation_status['total'] = len(batch_servers)
                
                # Функция обратного вызова для обновления прогресса
                def update_callback(result):
                    nonlocal processed
                    
                    # ВАЖНО: Работаем в том же контексте приложения
                    try:
                        processed += 1
                        validation_status['progress'] = processed
                        
                        # Обновляем оценку времени
                        elapsed = time.time() - start_time
                        if processed > 0:
                            time_per_server = elapsed / processed
                            remaining = validation_status['total'] - processed
                            validation_status['estimated_time'] = remaining * time_per_server
                        
                        # Сохраняем результат в базе
                        try:
                            server = SSHServer.query.get(result['server_id'])
                            if server:
                                server.is_valid = result['is_valid']
                                server.last_check = datetime.utcnow()
                                server.last_error = result['error'] if not result['is_valid'] else None
                                
                                # Если получили системную информацию, сохраняем её
                                if result.get('sys_info_collected') and result.get('sys_info'):
                                    sys_info = result['sys_info']
                                    
                                    # Сохраняем системную информацию
                                    server.os_info = sys_info.get('os')
                                    server.cpu_info = sys_info.get('cpu')
                                    server.memory_info = sys_info.get('memory')
                                    server.disk_info = sys_info.get('disk')
                                    server.kernel_version = sys_info.get('kernel')
                                    server.architecture = sys_info.get('architecture')
                                    server.uptime_info = sys_info.get('uptime')
                                    server.total_memory_mb = sys_info.get('total_memory_mb')
                                    server.used_memory_mb = sys_info.get('used_memory_mb')
                                    server.disk_usage_percent = sys_info.get('disk_usage_percent')
                                    server.cpu_cores = sys_info.get('cpu_cores')
                                
                                db.session.commit()
                                
                        except Exception as db_error:
                            db.session.rollback()
                            print(f"Ошибка сохранения в БД для {result.get('host', 'unknown')}: {db_error}")
                        
                        validation_status['results'].append(result)
                        
                    except Exception as callback_error:
                        print(f"Ошибка в callback: {callback_error}")
                
                # Выполняем валидацию батча
                try:
                    ssh_manager.validate_servers_batch(batch_servers, update_callback)
                except Exception as batch_error:
                    print(f"Ошибка обработки батча: {batch_error}")
                    
                    # Обрабатываем серверы по одному в случае ошибки
                    for server_data in batch_servers:
                        if not validation_status['running']:
                            break
                        try:
                            server_id, host, port, username, password = server_data
                            is_valid, error = ssh_manager.test_connection(host, port, username, password)
                            update_callback({
                                'server_id': server_id,
                                'host': host,
                                'is_valid': is_valid,
                                'error': error,
                                'sys_info_collected': False
                            })
                        except Exception as single_error:
                            print(f"Ошибка обработки сервера {server_data[0]}: {single_error}")
                
            except Exception as thread_error:
                print(f"Критическая ошибка в потоке валидации: {thread_error}")
            finally:
                validation_status['running'] = False
                validation_status['estimated_time'] = 0
    
    # Запускаем поток валидации
    thread = threading.Thread(target=validate_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

@app.route('/validation_status')
def validation_status_endpoint():
    """Получение статуса валидации"""
    status_copy = validation_status.copy()
    
    # Добавляем дополнительную информацию
    if status_copy['start_time']:
        elapsed = (datetime.now() - status_copy['start_time']).total_seconds()
        status_copy['elapsed_time'] = elapsed
        
        if status_copy['progress'] > 0:
            time_per_server = elapsed / status_copy['progress']
            status_copy['servers_per_second'] = round(status_copy['progress'] / elapsed, 2) if elapsed > 0 else 0
    
    # Конвертируем datetime в строку для JSON
    if status_copy.get('start_time'):
        status_copy['start_time'] = status_copy['start_time'].isoformat()
    
    return jsonify(status_copy)

@app.route('/execute_command', methods=['POST'])
def execute_command():
    """Выполнение команды на серверах"""
    global command_status, ssh_manager
    
    if command_status['running']:
        return jsonify({'error': 'Команда уже выполняется'})
    
    data = request.json
    command = data.get('command', '').strip()
    server_ids = data.get('server_ids', [])
    threads = int(data.get('threads', 10))
    timeout = int(data.get('timeout', 15))
    
    if not command:
        return jsonify({'error': 'Команда не указана'})
    
    # Валидация настроек
    threads = max(1, min(threads, 50))  # От 1 до 50 потоков для команд
    timeout = max(5, min(timeout, 60))   # От 5 до 60 секунд
    
    if not server_ids:
        # Если не указаны конкретные серверы, используем все валидные
        servers = SSHServer.query.filter(SSHServer.is_valid == True).all()
        server_ids = [s.id for s in servers]
    
    # Обновляем SSH Manager с новыми настройками
    ssh_manager = SSHManager(max_workers=threads, timeout=timeout)
    
    command_status = {
        'running': True,
        'progress': 0,
        'total': len(server_ids),
        'results': [],
        'threads': threads,
        'timeout': timeout,
        'start_time': datetime.now(),
        'estimated_time': None
    }
    
    def execute_thread():
        global command_status
        
        # ВАЖНО: Создаем контекст приложения для фонового потока
        with app.app_context():
            try:
                processed = 0
                start_time = time.time()
                
                # Подготавливаем данные серверов
                servers_data = []
                for server_id in server_ids:
                    try:
                        server = SSHServer.query.get(server_id)
                        if server and server.is_valid:
                            servers_data.append((
                                server_id,
                                server.host,
                                server.port,
                                server.username,
                                server.password
                            ))
                    except Exception as db_error:
                        print(f"Ошибка получения сервера {server_id} из БД: {db_error}")
                        continue
                
                if not servers_data:
                    command_status['running'] = False
                    print("Нет доступных серверов для выполнения команды")
                    return
                
                command_status['total'] = len(servers_data)
                
                def update_callback(result):
                    nonlocal processed
                    processed += 1
                    command_status['progress'] = processed
                    
                    # Обновляем оценку времени
                    elapsed = time.time() - start_time
                    if processed > 0:
                        time_per_server = elapsed / processed
                        remaining = command_status['total'] - processed
                        command_status['estimated_time'] = remaining * time_per_server
                    
                    command_status['results'].append(result)
                
                # Выполняем команды с обработкой ошибок
                try:
                    ssh_manager.execute_commands_batch(servers_data, command, update_callback)
                except Exception as exec_error:
                    print(f"Ошибка выполнения команд: {exec_error}")
                    
                    # Выполняем команды по одной если батч не работает
                    for server_data in servers_data:
                        if not command_status['running']:
                            break
                        try:
                            server_id, host, port, username, password = server_data
                            output, error = ssh_manager.execute_command(host, port, username, password, command)
                            update_callback({
                                'server_id': server_id,
                                'host': host,
                                'output': output,
                                'error': error,
                                'success': error is None,
                                'processing_time': time.time() - start_time
                            })
                        except Exception as single_error:
                            print(f"Ошибка выполнения команды на сервере {server_data[1]}: {single_error}")
                
            except Exception as thread_error:
                print(f"Критическая ошибка в потоке выполнения команд: {thread_error}")
            finally:
                command_status['running'] = False
                command_status['estimated_time'] = 0
    
    # Запускаем поток выполнения команд
    thread = threading.Thread(target=execute_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

@app.route('/command_status')
def command_status_endpoint():
    """Получение статуса выполнения команд"""
    status_copy = command_status.copy()
    
    # Добавляем дополнительную информацию
    if status_copy['start_time']:
        elapsed = (datetime.now() - status_copy['start_time']).total_seconds()
        status_copy['elapsed_time'] = elapsed
        
        if status_copy['progress'] > 0:
            status_copy['servers_per_second'] = round(status_copy['progress'] / elapsed, 2) if elapsed > 0 else 0
    
    # Конвертируем datetime в строку для JSON
    if status_copy.get('start_time'):
        status_copy['start_time'] = status_copy['start_time'].isoformat()
    
    return jsonify(status_copy)

@app.route('/update_system_info', methods=['POST'])
def update_system_info():
    """Обновление только системной информации без проверки доступности"""
    global command_status, ssh_manager
    
    if command_status['running']:
        return jsonify({'error': 'Уже выполняется операция'})
    
    data = request.json or {}
    server_ids = data.get('server_ids', [])
    threads = int(data.get('threads', 10))
    timeout = int(data.get('timeout', 20))
    
    # Валидация настроек
    threads = max(1, min(threads, 50))
    timeout = max(10, min(timeout, 60))
    
    if not server_ids:
        servers = SSHServer.query.filter(SSHServer.is_valid == True).all()
        server_ids = [s.id for s in servers]
    
    # Обновляем SSH Manager
    ssh_manager = SSHManager(max_workers=threads, timeout=timeout)
    
    command_status = {
        'running': True,
        'progress': 0,
        'total': len(server_ids),
        'results': [],
        'threads': threads,
        'timeout': timeout,
        'start_time': datetime.now(),
        'estimated_time': None
    }
    
    def system_info_thread():
        global command_status
        
        # ВАЖНО: Создаем контекст приложения для фонового потока
        with app.app_context():
            try:
                processed = 0
                start_time = time.time()
                
                for i, server_id in enumerate(server_ids):
                    if not command_status['running']:
                        break
                    
                    try:
                        server = SSHServer.query.get(server_id)
                        if server and server.is_valid:
                            print(f"Обновление системной информации для {server.host}...")
                            
                            try:
                                sys_info = ssh_manager.get_system_info(
                                    server.host, server.port, server.username, server.password
                                )
                                
                                # Обновляем системную информацию
                                if 'error' not in sys_info:
                                    server.os_info = sys_info.get('os')
                                    server.cpu_info = sys_info.get('cpu')
                                    server.memory_info = sys_info.get('memory')
                                    server.disk_info = sys_info.get('disk')
                                    server.kernel_version = sys_info.get('kernel')
                                    server.architecture = sys_info.get('architecture')
                                    server.uptime_info = sys_info.get('uptime')
                                    server.total_memory_mb = sys_info.get('total_memory_mb')
                                    server.used_memory_mb = sys_info.get('used_memory_mb')
                                    server.disk_usage_percent = sys_info.get('disk_usage_percent')
                                    server.cpu_cores = sys_info.get('cpu_cores')
                                    
                                    command_status['results'].append({
                                        'server_id': server_id,
                                        'host': server.host,
                                        'success': True,
                                        'message': 'Системная информация обновлена'
                                    })
                                else:
                                    command_status['results'].append({
                                        'server_id': server_id,
                                        'host': server.host,
                                        'success': False,
                                        'message': sys_info.get('error', 'Неизвестная ошибка')
                                    })
                                
                                try:
                                    db.session.commit()
                                    print(f"✅ Информация обновлена для {server.host}")
                                except Exception as commit_error:
                                    db.session.rollback()
                                    print(f"Ошибка сохранения для {server.host}: {commit_error}")
                                    command_status['results'].append({
                                        'server_id': server_id,
                                        'host': server.host,
                                        'success': False,
                                        'message': f'Ошибка сохранения: {commit_error}'
                                    })
                            
                            except Exception as sys_error:
                                print(f"Ошибка получения системной информации для {server.host}: {sys_error}")
                                command_status['results'].append({
                                    'server_id': server_id,
                                    'host': server.host,
                                    'success': False,
                                    'message': str(sys_error)
                                })
                        else:
                            command_status['results'].append({
                                'server_id': server_id,
                                'host': f'server_{server_id}',
                                'success': False,
                                'message': 'Сервер недоступен или не найден'
                            })
                    
                    except Exception as server_error:
                        print(f"Ошибка обработки сервера {server_id}: {server_error}")
                        command_status['results'].append({
                            'server_id': server_id,
                            'host': f'server_{server_id}',
                            'success': False,
                            'message': str(server_error)
                        })
                    
                    processed += 1
                    command_status['progress'] = processed
                    
                    # Обновляем оценку времени
                    elapsed = time.time() - start_time
                    if processed > 0:
                        time_per_server = elapsed / processed
                        remaining = command_status['total'] - processed
                        command_status['estimated_time'] = remaining * time_per_server
                
            except Exception as thread_error:
                print(f"Критическая ошибка в потоке системной информации: {thread_error}")
            finally:
                command_status['running'] = False
                command_status['estimated_time'] = 0
    
    # Запускаем поток получения системной информации
    thread = threading.Thread(target=system_info_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

@app.route('/clear_errors', methods=['POST'])
def clear_errors():
    """Очистка ошибок серверов"""
    data = request.json or {}
    action = data.get('action', 'clear_all')
    
    try:
        if action == 'clear_all':
            # Очищаем все ошибки и сбрасываем статус
            servers = SSHServer.query.all()
            for server in servers:
                server.is_valid = None
                server.last_error = None
                server.last_check = None
            
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': f'Очищены ошибки для {len(servers)} серверов'
            })
            
        elif action == 'clear_server':
            # Очищаем ошибки для конкретного сервера
            server_id = data.get('server_id')
            if not server_id:
                return jsonify({'success': False, 'error': 'Не указан ID сервера'})
            
            server = SSHServer.query.get(server_id)
            if not server:
                return jsonify({'success': False, 'error': 'Сервер не найден'})
            
            server.is_valid = None
            server.last_error = None
            server.last_check = None
            
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': f'Очищены ошибки для сервера {server.host}'
            })
            
        elif action == 'clear_invalid':
            # Очищаем только недоступные серверы
            servers = SSHServer.query.filter(SSHServer.is_valid == False).all()
            for server in servers:
                server.is_valid = None
                server.last_error = None
                server.last_check = None
            
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': f'Очищены ошибки для {len(servers)} недоступных серверов'
            })
            
        else:
            return jsonify({'success': False, 'error': 'Неизвестное действие'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stop_operation', methods=['POST'])
def stop_operation():
    """Остановка текущей операции"""
    global validation_status, command_status
    
    operation = request.json.get('operation')
    
    if operation == 'validation':
        validation_status['running'] = False
    elif operation == 'command':
        command_status['running'] = False
    
    return jsonify({'success': True})

@app.route('/server/<int:server_id>')
def server_detail(server_id):
    """Детальная информация о сервере"""
    server = SSHServer.query.get_or_404(server_id)
    return render_template('server_detail.html', server=server)

@app.route('/delete_server/<int:server_id>', methods=['POST'])
def delete_server(server_id):
    """Удаление сервера"""
    server = SSHServer.query.get_or_404(server_id)
    db.session.delete(server)
    db.session.commit()
    flash('Сервер удален', 'success')
    return redirect(url_for('servers'))

@app.route('/api/servers')
def api_servers():
    """API для получения списка серверов"""
    servers = SSHServer.query.all()
    return jsonify([{
        'id': s.id,
        'host': s.host,
        'port': s.port,
        'username': s.username,
        'country': s.country,
        'city': s.city,
        'is_valid': s.is_valid,
        'last_check': s.last_check.isoformat() if s.last_check else None
    } for s in servers])

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Страница настроек приложения"""
    if request.method == 'POST':
        # Обработка сохранения настроек
        data = request.json
        # Здесь можно сохранить настройки в файл или базу данных
        return jsonify({'success': True})
    
    # Возвращаем текущие настройки
    current_settings = {
        'default_threads': 10,
        'default_timeout': 15,
        'max_threads': 100,
        'max_timeout': 60
    }
    
    return render_template('settings.html', settings=current_settings)

@app.route('/errors')
def error_monitoring():
    """Страница мониторинга ошибок"""
    # Получаем статистику ошибок из базы данных
    error_servers = SSHServer.query.filter(SSHServer.is_valid == False).all()
    
    # Группируем ошибки по типам
    error_types = {}
    for server in error_servers:
        if server.last_error:
            error_type = classify_error(server.last_error)
            error_types[error_type] = error_types.get(error_type, 0) + 1
    
    return render_template('error_monitoring.html', 
                         error_servers=error_servers,
                         error_types=error_types)

def classify_error(error_message):
    """Классификация ошибок по типам"""
    error_msg = error_message.lower()
    
    if 'banner' in error_msg or 'protocol' in error_msg:
        return 'SSH Banner'
    elif 'timeout' in error_msg or 'timed out' in error_msg:
        return 'Timeout'
    elif 'authentication' in error_msg or 'auth' in error_msg:
        return 'Authentication'
    elif 'connection refused' in error_msg or 'network' in error_msg:
        return 'Network'
    elif 'permission' in error_msg or 'denied' in error_msg:
        return 'Permission'
    else:
        return 'Other'

@app.route('/api/error_stats')
def api_error_stats():
    """API для получения статистики ошибок"""
    error_servers = SSHServer.query.filter(SSHServer.is_valid == False).all()
    
    stats = {
        'total_errors': len(error_servers),
        'error_types': {},
        'problematic_servers': []
    }
    
    for server in error_servers:
        if server.last_error:
            error_type = classify_error(server.last_error)
            stats['error_types'][error_type] = stats['error_types'].get(error_type, 0) + 1
            
            stats['problematic_servers'].append({
                'host': server.host,
                'port': server.port,
                'error': server.last_error,
                'last_check': server.last_check.isoformat() if server.last_check else None
            })
    
    return jsonify(stats)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("🚀 SSH Manager запущен!")
    print("🌐 Откройте: http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)