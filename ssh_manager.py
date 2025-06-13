import paramiko
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import queue
from typing import List, Tuple, Dict, Optional, Callable
import logging

# Настройка логирования
logging.getLogger("paramiko").setLevel(logging.WARNING)

class SSHManager:
    """Улучшенный класс для управления SSH соединениями с надежной обработкой ошибок"""
    
    def __init__(self, max_workers=20, timeout=10):
        self.max_workers = max_workers
        self.timeout = timeout
        self.active_connections = {}
        self.lock = threading.Lock()
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'start_time': None,
            'last_update': None
        }
        
        # Настройки для улучшенной надежности
        self.retry_attempts = 2
        self.banner_timeout = min(5, timeout // 2)  # Таймаут для SSH banner
        self.auth_timeout = min(10, timeout)        # Таймаут для аутентификации
    
    def test_connection(self, host: str, port: int, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Тестирование SSH соединения с улучшенной обработкой ошибок
        
        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        for attempt in range(self.retry_attempts):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Более детальные настройки таймаутов
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=self.timeout,
                    banner_timeout=self.banner_timeout,
                    auth_timeout=self.auth_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                    # Дополнительные параметры для надежности
                    disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']},
                    compress=False
                )
                
                # Быстрый тест выполнения команды
                try:
                    stdin, stdout, stderr = client.exec_command('echo "test"', timeout=5)
                    result = stdout.read().decode().strip()
                    stderr_output = stderr.read().decode().strip()
                    
                    client.close()
                    
                    if result == "test":
                        return True, None
                    elif stderr_output:
                        return False, f"Команда выполнена с ошибкой: {stderr_output}"
                    else:
                        return False, "Команда не выполнилась корректно"
                        
                except Exception as exec_error:
                    client.close()
                    return False, f"Ошибка выполнения команды: {str(exec_error)}"
                    
            except paramiko.AuthenticationException:
                return False, "Ошибка аутентификации: неверные логин/пароль"
            except paramiko.SSHException as ssh_error:
                error_msg = str(ssh_error)
                if "Error reading SSH protocol banner" in error_msg:
                    if attempt < self.retry_attempts - 1:
                        time.sleep(1)  # Небольшая пауза перед повтором
                        continue
                    return False, "SSH сервер не отвечает (banner timeout)"
                elif "not open" in error_msg.lower():
                    return False, "SSH порт закрыт или заблокирован"
                elif "timed out" in error_msg.lower():
                    return False, "Превышен таймаут SSH подключения"
                else:
                    return False, f"SSH ошибка: {error_msg}"
            except socket.timeout:
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return False, "Превышен таймаут подключения"
            except socket.gaierror as dns_error:
                return False, f"Не удается разрешить имя хоста: {str(dns_error)}"
            except ConnectionRefusedError:
                return False, "Соединение отклонено (порт закрыт)"
            except ConnectionResetError:
                return False, "Соединение сброшено удаленным хостом"
            except OSError as os_error:
                error_msg = str(os_error)
                if "No route to host" in error_msg:
                    return False, "Нет маршрута до хоста"
                elif "Network is unreachable" in error_msg:
                    return False, "Сеть недоступна"
                else:
                    return False, f"Сетевая ошибка: {error_msg}"
            except Exception as e:
                error_msg = str(e)
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return False, f"Неизвестная ошибка: {error_msg}"
        
        return False, "Не удалось подключиться после нескольких попыток"
    
    def execute_command(self, host: str, port: int, username: str, password: str, command: str) -> Tuple[str, Optional[str]]:
        """
        Выполнение команды на удаленном сервере с улучшенной обработкой ошибок
        
        Returns:
            tuple: (output: str, error: str or None)
        """
        for attempt in range(self.retry_attempts):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=self.timeout,
                    banner_timeout=self.banner_timeout,
                    auth_timeout=self.auth_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                    compress=False
                )
                
                # Выполняем команду с расширенным таймаутом
                command_timeout = max(30, self.timeout * 2)
                stdin, stdout, stderr = client.exec_command(command, timeout=command_timeout)
                
                # Читаем результат
                output = stdout.read().decode('utf-8', errors='ignore').strip()
                error_output = stderr.read().decode('utf-8', errors='ignore').strip()
                
                # Получаем код возврата
                exit_status = stdout.channel.recv_exit_status()
                
                client.close()
                
                if exit_status == 0:
                    return output, None
                else:
                    return output, f"Команда завершилась с кодом {exit_status}: {error_output}"
                    
            except paramiko.AuthenticationException:
                return "", "Ошибка аутентификации"
            except paramiko.SSHException as ssh_error:
                error_msg = str(ssh_error)
                if "Error reading SSH protocol banner" in error_msg and attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return "", f"SSH ошибка: {error_msg}"
            except socket.timeout:
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return "", "Превышен таймаут выполнения команды"
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return "", f"Ошибка выполнения: {str(e)}"
        
        return "", "Не удалось выполнить команду после нескольких попыток"
    
    def get_system_info(self, host: str, port: int, username: str, password: str) -> Dict:
        """
        Получение информации о системе с улучшенной обработкой ошибок
        
        Returns:
            dict: Словарь с информацией о системе
        """
        info = {
            'os': None,
            'cpu': None,
            'memory': None,
            'disk': None,
            'uptime': None,
            'kernel': None,
            'architecture': None,
            'total_memory_mb': None,
            'used_memory_mb': None,
            'disk_usage_percent': None,
            'cpu_cores': None,
            'connection_test': None
        }
        
        # Сначала проверяем базовое подключение
        is_valid, error = self.test_connection(host, port, username, password)
        info['connection_test'] = {'valid': is_valid, 'error': error}
        
        if not is_valid:
            info['error'] = f"Не удается подключиться: {error}"
            return info
        
        # Команды для получения системной информации
        commands = {
            'os': 'cat /etc/os-release 2>/dev/null | head -1 | cut -d= -f2 | tr -d \'"\'|| uname -s 2>/dev/null || echo "Unknown"',
            'cpu': 'cat /proc/cpuinfo 2>/dev/null | grep "model name" | head -1 | cut -d: -f2 | sed "s/^[ \t]*//" || echo "Unknown CPU"',
            'cpu_cores': 'nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "1"',
            'memory': 'free -m 2>/dev/null | grep Mem || echo "Mem: 0 0 0"',
            'disk': 'df -h / 2>/dev/null | tail -1 || echo "/ 0G 0G 0G 0% /"',
            'uptime': 'uptime 2>/dev/null | awk \'{print $3 " " $4}\' | sed \'s/,//\' || echo "Unknown"',
            'kernel': 'uname -r 2>/dev/null || echo "Unknown"',
            'architecture': 'uname -m 2>/dev/null || echo "Unknown"'
        }
        
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self.timeout,
                banner_timeout=self.banner_timeout,
                auth_timeout=self.auth_timeout,
                look_for_keys=False,
                allow_agent=False,
                compress=False
            )
            
            # Выполняем все команды последовательно с обработкой ошибок
            for key, command in commands.items():
                try:
                    stdin, stdout, stderr = client.exec_command(command, timeout=15)
                    output = stdout.read().decode('utf-8', errors='ignore').strip()
                    if output and output != "Unknown":
                        info[key] = output
                except Exception as cmd_error:
                    print(f"Ошибка выполнения команды {key}: {cmd_error}")
                    continue
            
            client.close()
            
            # Парсим дополнительную информацию
            self._parse_system_info(info)
            
        except Exception as e:
            info['error'] = f"Ошибка получения системной информации: {str(e)}"
        
        return info
    
    def _parse_system_info(self, info: Dict):
        """Парсинг системной информации"""
        try:
            # Парсим память
            if info.get('memory'):
                memory_parts = info['memory'].split()
                if len(memory_parts) >= 3 and memory_parts[0] == 'Mem:':
                    try:
                        info['total_memory_mb'] = int(memory_parts[1])
                        info['used_memory_mb'] = int(memory_parts[2])
                    except (ValueError, IndexError):
                        pass
            
            # Парсим использование диска
            if info.get('disk'):
                disk_parts = info['disk'].split()
                if len(disk_parts) >= 5:
                    try:
                        usage_str = disk_parts[4].replace('%', '')
                        info['disk_usage_percent'] = int(usage_str)
                    except (ValueError, IndexError):
                        pass
            
            # Парсим количество ядер CPU
            if info.get('cpu_cores'):
                try:
                    info['cpu_cores'] = int(info['cpu_cores'])
                except ValueError:
                    info['cpu_cores'] = 1
                    
        except Exception as parse_error:
            print(f"Ошибка парсинга системной информации: {parse_error}")
    
    def validate_servers_batch(self, servers: List[Tuple], callback: Optional[Callable] = None) -> List[Dict]:
        """
        Валидация серверов в пакетном режиме с улучшенной обработкой ошибок
        
        Args:
            servers: список серверов для валидации (server_id, host, port, username, password)
            callback: функция обратного вызова для обновления прогресса
        
        Returns:
            list: результаты валидации
        """
        results = []
        self.stats['start_time'] = time.time()
        self.stats['total_processed'] = 0
        self.stats['successful'] = 0
        self.stats['failed'] = 0
        
        def validate_single(server_data):
            server_id, host, port, username, password = server_data
            start_time = time.time()
            
            try:
                # Проверяем подключение
                is_valid, error = self.test_connection(host, port, username, password)
                
                result = {
                    'server_id': server_id,
                    'host': host,
                    'is_valid': is_valid,
                    'error': error,
                    'processing_time': time.time() - start_time,
                    'sys_info_collected': False
                }
                
                # Если сервер доступен, получаем системную информацию
                if is_valid:
                    try:
                        sys_info = self.get_system_info(host, port, username, password)
                        if 'error' not in sys_info:
                            result['sys_info'] = sys_info
                            result['sys_info_collected'] = True
                    except Exception as sys_error:
                        print(f"Ошибка получения системной информации для {host}: {sys_error}")
                
                # Обновляем статистику
                with self.lock:
                    self.stats['total_processed'] += 1
                    if is_valid:
                        self.stats['successful'] += 1
                    else:
                        self.stats['failed'] += 1
                    self.stats['last_update'] = time.time()
                
                if callback:
                    callback(result)
                
                return result
                
            except Exception as e:
                result = {
                    'server_id': server_id,
                    'host': host,
                    'is_valid': False,
                    'error': f"Критическая ошибка: {str(e)}",
                    'processing_time': time.time() - start_time,
                    'sys_info_collected': False
                }
                
                with self.lock:
                    self.stats['total_processed'] += 1
                    self.stats['failed'] += 1
                    self.stats['last_update'] = time.time()
                
                if callback:
                    callback(result)
                
                return result
        
        # Используем ThreadPoolExecutor для контролируемой многопоточности
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SSH-Validator") as executor:
            # Отправляем все задачи
            future_to_server = {executor.submit(validate_single, server): server for server in servers}
            
            # Собираем результаты по мере готовности
            for future in as_completed(future_to_server):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    server = future_to_server[future]
                    error_result = {
                        'server_id': server[0],
                        'host': server[1],
                        'is_valid': False,
                        'error': f'Критическое исключение при обработке: {exc}',
                        'processing_time': 0,
                        'sys_info_collected': False
                    }
                    results.append(error_result)
                    if callback:
                        callback(error_result)
        
        return results
    
    def execute_commands_batch(self, servers: List[Tuple], command: str, callback: Optional[Callable] = None) -> List[Dict]:
        """
        Выполнение команды на нескольких серверах с улучшенной обработкой ошибок
        
        Args:
            servers: список серверов (server_id, host, port, username, password)
            command: команда для выполнения
            callback: функция обратного вызова
        
        Returns:
            list: результаты выполнения
        """
        results = []
        self.stats['start_time'] = time.time()
        self.stats['total_processed'] = 0
        self.stats['successful'] = 0
        self.stats['failed'] = 0
        
        def execute_single(server_data):
            server_id, host, port, username, password = server_data
            start_time = time.time()
            
            try:
                output, error = self.execute_command(host, port, username, password, command)
                
                result = {
                    'server_id': server_id,
                    'host': host,
                    'output': output,
                    'error': error,
                    'success': error is None,
                    'processing_time': time.time() - start_time
                }
                
                # Обновляем статистику
                with self.lock:
                    self.stats['total_processed'] += 1
                    if error is None:
                        self.stats['successful'] += 1
                    else:
                        self.stats['failed'] += 1
                    self.stats['last_update'] = time.time()
                
                if callback:
                    callback(result)
                
                return result
                
            except Exception as e:
                result = {
                    'server_id': server_id,
                    'host': host,
                    'output': '',
                    'error': f"Критическая ошибка: {str(e)}",
                    'success': False,
                    'processing_time': time.time() - start_time
                }
                
                with self.lock:
                    self.stats['total_processed'] += 1
                    self.stats['failed'] += 1
                    self.stats['last_update'] = time.time()
                
                if callback:
                    callback(result)
                
                return result
        
        # Используем ThreadPoolExecutor для контролируемой многопоточности
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SSH-Commander") as executor:
            # Отправляем все задачи
            future_to_server = {executor.submit(execute_single, server): server for server in servers}
            
            # Собираем результаты по мере готовности
            for future in as_completed(future_to_server):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    server = future_to_server[future]
                    error_result = {
                        'server_id': server[0],
                        'host': server[1],
                        'output': '',
                        'error': f'Критическое исключение: {exc}',
                        'success': False,
                        'processing_time': 0
                    }
                    results.append(error_result)
                    if callback:
                        callback(error_result)
        
        return results
    
    def get_performance_stats(self) -> Dict:
        """
        Получение статистики производительности
        
        Returns:
            dict: статистика производительности
        """
        with self.lock:
            stats = self.stats.copy()
        
        if stats['start_time'] and stats['last_update']:
            elapsed_time = stats['last_update'] - stats['start_time']
            if elapsed_time > 0:
                stats['servers_per_second'] = round(stats['total_processed'] / elapsed_time, 2)
                stats['average_processing_time'] = round(elapsed_time / stats['total_processed'], 2) if stats['total_processed'] > 0 else 0
            else:
                stats['servers_per_second'] = 0
                stats['average_processing_time'] = 0
        else:
            stats['servers_per_second'] = 0
            stats['average_processing_time'] = 0
        
        stats['success_rate'] = round((stats['successful'] / stats['total_processed']) * 100, 1) if stats['total_processed'] > 0 else 0
        
        return stats
    
    def reset_stats(self):
        """Сброс статистики"""
        with self.lock:
            self.stats = {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'start_time': None,
                'last_update': None
            }
    
    def close_all_connections(self):
        """Закрытие всех активных соединений"""
        with self.lock:
            for connection in self.active_connections.values():
                try:
                    connection.close()
                except:
                    pass
            self.active_connections.clear()
    
    def __del__(self):
        """Деструктор - закрываем все соединения"""
        self.close_all_connections()