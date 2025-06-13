import re
import requests
import socket
from urllib.parse import urlparse

def parse_ssh_file(filepath):
    """
    Парсинг файла с SSH серверами
    
    Поддерживаемые форматы:
    - host:port:username:password
    - host:port:username:password (с доменными именами)
    
    Args:
        filepath: путь к файлу
    
    Returns:
        list: список словарей с данными серверов
    """
    servers = []
    
    with open(filepath, 'r', encoding='utf-8') as file:
        for line_num, line in enumerate(file, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            try:
                parts = line.split(':')
                if len(parts) < 4:
                    print(f"Строка {line_num}: недостаточно данных - {line}")
                    continue
                
                host = parts[0].strip()
                port = int(parts[1].strip())
                username = parts[2].strip()
                # Пароль может содержать двоеточия, поэтому собираем оставшиеся части
                password = ':'.join(parts[3:]).strip()
                
                if not all([host, username, password]):
                    print(f"Строка {line_num}: пустые поля - {line}")
                    continue
                
                server_data = {
                    'host': host,
                    'port': port,
                    'username': username,
                    'password': password
                }
                
                servers.append(server_data)
                
            except ValueError as e:
                print(f"Строка {line_num}: ошибка парсинга - {line}, ошибка: {e}")
                continue
            except Exception as e:
                print(f"Строка {line_num}: неожиданная ошибка - {line}, ошибка: {e}")
                continue
    
    return servers

def get_server_geo(host):
    """
    Получение геоданных сервера по IP или домену
    
    Args:
        host: IP адрес или домен
    
    Returns:
        dict: геоданные или None при ошибке
    """
    try:
        # Если передан домен, получаем IP
        ip = host
        if not is_valid_ip(host):
            ip = socket.gethostbyname(host)
        
        # Используем бесплатный API для геолокации
        response = requests.get(
            f'http://ip-api.com/json/{ip}',
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    'country': data.get('country'),
                    'city': data.get('city'),
                    'latitude': data.get('lat'),
                    'longitude': data.get('lon'),
                    'region': data.get('regionName'),
                    'timezone': data.get('timezone'),
                    'isp': data.get('isp')
                }
    
    except Exception as e:
        print(f"Ошибка получения геоданных для {host}: {e}")
    
    return None

def is_valid_ip(ip):
    """
    Проверка, является ли строка валидным IP адресом
    
    Args:
        ip: строка для проверки
    
    Returns:
        bool: True если валидный IP
    """
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False

def format_bytes(bytes_value):
    """
    Форматирование размера в человекочитаемый вид
    
    Args:
        bytes_value: размер в байтах
    
    Returns:
        str: отформатированная строка
    """
    if bytes_value == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_value >= 1024 and i < len(size_names)-1:
        bytes_value /= 1024
        i += 1
    
    return f"{bytes_value:.1f} {size_names[i]}"

def validate_server_data(host, port, username, password):
    """
    Валидация данных сервера
    
    Args:
        host: хост
        port: порт
        username: имя пользователя
        password: пароль
    
    Returns:
        tuple: (is_valid: bool, errors: list)
    """
    errors = []
    
    # Проверка хоста
    if not host:
        errors.append("Хост не может быть пустым")
    elif len(host) > 255:
        errors.append("Хост слишком длинный")
    
    # Проверка порта
    if not isinstance(port, int) or port < 1 or port > 65535:
        errors.append("Порт должен быть числом от 1 до 65535")
    
    # Проверка имени пользователя
    if not username:
        errors.append("Имя пользователя не может быть пустым")
    elif len(username) > 100:
        errors.append("Имя пользователя слишком длинное")
    
    # Проверка пароля
    if not password:
        errors.append("Пароль не может быть пустым")
    elif len(password) > 255:
        errors.append("Пароль слишком длинный")
    
    return len(errors) == 0, errors

def parse_system_info(info_dict):
    """
    Парсинг системной информации
    
    Args:
        info_dict: словарь с сырой информацией о системе
    
    Returns:
        dict: обработанная информация
    """
    parsed = {}
    
    # Парсинг информации об ОС
    if info_dict.get('os'):
        os_info = info_dict['os']
        parsed['os_name'] = extract_os_name(os_info)
        parsed['kernel_version'] = extract_kernel_version(os_info)
        parsed['arch'] = extract_architecture(os_info)
    
    # Парсинг информации о CPU
    if info_dict.get('cpu'):
        cpu_info = info_dict['cpu'].strip()
        parsed['cpu_model'] = cpu_info
    
    # Парсинг информации о памяти
    if info_dict.get('memory'):
        memory_info = info_dict['memory']
        parsed['memory'] = parse_memory_info(memory_info)
    
    # Парсинг информации о диске
    if info_dict.get('disk'):
        disk_info = info_dict['disk']
        parsed['disk'] = parse_disk_info(disk_info)
    
    return parsed

def extract_os_name(os_info):
    """Извлечение названия ОС из uname -a"""
    if 'Ubuntu' in os_info:
        return 'Ubuntu'
    elif 'Debian' in os_info:
        return 'Debian'
    elif 'CentOS' in os_info:
        return 'CentOS'
    elif 'Red Hat' in os_info or 'RHEL' in os_info:
        return 'Red Hat'
    elif 'Fedora' in os_info:
        return 'Fedora'
    elif 'SUSE' in os_info:
        return 'SUSE'
    elif 'Darwin' in os_info:
        return 'macOS'
    else:
        return 'Unknown'

def extract_kernel_version(os_info):
    """Извлечение версии ядра"""
    match = re.search(r'(\d+\.\d+\.\d+)', os_info)
    return match.group(1) if match else None

def extract_architecture(os_info):
    """Извлечение архитектуры"""
    if 'x86_64' in os_info:
        return 'x86_64'
    elif 'i386' in os_info or 'i686' in os_info:
        return 'i386'
    elif 'aarch64' in os_info:
        return 'aarch64'
    elif 'armv' in os_info:
        return 'ARM'
    else:
        return 'Unknown'

def parse_memory_info(memory_info):
    """Парсинг информации о памяти из free -h"""
    try:
        parts = memory_info.split()
        if len(parts) >= 3:
            total = parts[1]
            used = parts[2]
            return f"Всего: {total}, Используется: {used}"
    except:
        pass
    return memory_info

def parse_disk_info(disk_info):
    """Парсинг информации о дисках из df -h"""
    lines = disk_info.split('\n')
    parsed_lines = []
    
    for line in lines[1:]:  # Пропускаем заголовок
        parts = line.split()
        if len(parts) >= 6:
            filesystem = parts[0]
            size = parts[1]
            used = parts[2]
            mount = parts[-1]
            parsed_lines.append(f"{filesystem}: {used}/{size} ({mount})")
    
    return '\n'.join(parsed_lines) if parsed_lines else disk_info