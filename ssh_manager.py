import paramiko
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
from typing import List, Tuple, Dict, Optional, Callable
import logging

logging.getLogger("paramiko").setLevel(logging.WARNING)
paramiko.util.log_to_file(os.devnull)

class SSHManager:
    
    def __init__(self, max_workers=20, timeout=15):
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
        
        self.retry_attempts = 1
        self.banner_timeout = 10
        self.auth_timeout = 10
        self.connect_timeout = timeout
    
    def check_port_open(self, host: str, port: int = 22, timeout: int = 5) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def test_connection(self, host: str, port: int, username: str, password: str) -> Tuple[bool, Optional[str]]:
        if not self.check_port_open(host, port, timeout=5):
            return False, "Порт закрыт или недоступен"
        
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self.connect_timeout,
                banner_timeout=self.banner_timeout,
                auth_timeout=self.auth_timeout,
                look_for_keys=False,
                allow_agent=False
            )
            
            stdin, stdout, stderr = client.exec_command('echo "test"', timeout=10)
            result = stdout.read().decode('utf-8', errors='ignore').strip()
            stderr_output = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if result == "test":
                return True, None
            elif stderr_output:
                return False, f"Команда выполнена с ошибкой: {stderr_output}"
            else:
                return False, "Команда не выполнилась корректно"
                
        except paramiko.AuthenticationException:
            return False, "Ошибка аутентификации: неверные логин/пароль"
            
        except paramiko.SSHException as ssh_error:
            error_msg = str(ssh_error)
            if "Error reading SSH protocol banner" in error_msg:
                return False, "SSH сервер не отвечает (banner timeout)"
            elif "not open" in error_msg.lower():
                return False, "SSH порт закрыт или заблокирован"
            elif "timed out" in error_msg.lower():
                return False, "Превышен таймаут SSH подключения"
            else:
                return False, f"SSH ошибка: {error_msg}"
                
        except socket.timeout:
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
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            return False, f"Ошибка: {error_msg}"
            
        finally:
            if client:
                try:
                    client.close()
                except:
                    pass
        
        return False, "Не удалось подключиться"
    
    def execute_command(self, host: str, port: int, username: str, password: str, command: str) -> Tuple[str, Optional[str]]:
        if not self.check_port_open(host, port, timeout=5):
            return "", "Порт закрыт или недоступен"
        
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self.connect_timeout,
                banner_timeout=self.banner_timeout,
                auth_timeout=self.auth_timeout,
                look_for_keys=False,
                allow_agent=False
            )
            
            command_timeout = max(30, self.timeout * 2)
            stdin, stdout, stderr = client.exec_command(command, timeout=command_timeout)
            
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error_output = stderr.read().decode('utf-8', errors='ignore').strip()
            
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status == 0:
                return output, None
            else:
                return output, f"Команда завершилась с кодом {exit_status}: {error_output}"
                
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            return "", f"Ошибка выполнения: {error_msg}"
        finally:
            if client:
                try:
                    client.close()
                except:
                    pass
    
    def get_system_info(self, host: str, port: int, username: str, password: str) -> Dict:
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
        
        is_valid, error = self.test_connection(host, port, username, password)
        info['connection_test'] = {'valid': is_valid, 'error': error}
        
        if not is_valid:
            info['error'] = f"Не удается подключиться: {error}"
            return info
        
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self.connect_timeout,
                banner_timeout=self.banner_timeout,
                auth_timeout=self.auth_timeout,
                look_for_keys=False,
                allow_agent=False
            )
            
            def safe_exec_command(command, timeout=3):
                try:
                    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                    result = stdout.read().decode('utf-8', errors='ignore').strip()
                    return result if result else None
                except:
                    return None
            
            cpu_commands = [
                'nproc',
                'grep -c ^processor /proc/cpuinfo',
                'sysctl -n hw.ncpu'
            ]
            
            memory_commands = [
                'free -h | grep ^Mem | awk \'{print $2}\'',
                'cat /proc/meminfo | grep MemTotal | awk \'{print $2 " " $3}\'',
                'sysctl -n hw.memsize | awk \'{print int($1/1024/1024/1024) "G"}\''
            ]
            
            disk_commands = [
                'df -h / | tail -1 | awk \'{print $2 " " $5}\'',
                'lsblk | grep disk | head -1 | awk \'{print $4}\''
            ]
            
            additional_commands = {
                'os': 'cat /etc/os-release 2>/dev/null | head -1 | cut -d= -f2 | tr -d \'"\'|| uname -s 2>/dev/null || echo "Unknown"',
                'kernel': 'uname -r 2>/dev/null || echo "Unknown"',
                'architecture': 'uname -m 2>/dev/null || echo "Unknown"',
                'uptime': 'uptime 2>/dev/null | awk \'{print $3 " " $4}\' | sed \'s/,//\' || echo "Unknown"'
            }
            
            for cmd in cpu_commands:
                result = safe_exec_command(cmd)
                if result and result.isdigit():
                    cores = int(result)
                    if 1 <= cores <= 256:
                        info['cpu_cores'] = cores
                        info['cpu'] = f"{cores} cores"
                        break
            
            for cmd in memory_commands:
                result = safe_exec_command(cmd)
                if result:
                    if 'G' in result or 'M' in result:
                        info['memory'] = result.split()[0]
                        info['memory_total'] = result.split()[0]
                        break
                    elif result.isdigit():
                        kb = int(result)
                        if kb > 1000000:
                            gb = round(kb / 1024 / 1024, 1)
                            info['memory'] = f"{gb}G"
                            info['memory_total'] = f"{gb}G"
                            info['total_memory_mb'] = int(gb * 1024)
                            break
            
            for cmd in disk_commands:
                result = safe_exec_command(cmd)
                if result and any(unit in result for unit in ['G', 'T', 'M']):
                    info['disk'] = result
                    parts = result.split()
                    for part in parts:
                        if '%' in part:
                            try:
                                usage = int(part.replace('%', ''))
                                info['disk_usage_percent'] = usage
                            except:
                                pass
                    break
            
            for key, command in additional_commands.items():
                try:
                    result = safe_exec_command(command, timeout=5)
                    if result and result != "Unknown":
                        info[key] = result
                except:
                    continue
            
        except Exception as e:
            info['error'] = f"Ошибка получения системной информации: {str(e)}"
        finally:
            if client:
                try:
                    client.close()
                except:
                    pass
        
        return info
    
    def validate_servers_batch(self, servers: List[Tuple], callback: Optional[Callable] = None) -> List[Dict]:
        results = []
        self.stats['start_time'] = time.time()
        self.stats['total_processed'] = 0
        self.stats['successful'] = 0
        self.stats['failed'] = 0
        
        def validate_single(server_data):
            server_id, host, port, username, password = server_data
            start_time = time.time()
            
            try:
                is_valid, error = self.test_connection(host, port, username, password)
                
                result = {
                    'server_id': server_id,
                    'host': host,
                    'is_valid': is_valid,
                    'error': error,
                    'processing_time': time.time() - start_time,
                    'sys_info_collected': False
                }
                
                if is_valid:
                    try:
                        sys_info = self.get_system_info(host, port, username, password)
                        if 'error' not in sys_info:
                            result['sys_info'] = sys_info
                            result['sys_info_collected'] = True
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
        
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SSH-Commander") as executor:
            future_to_server = {executor.submit(execute_single, server): server for server in servers}
            
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
        with self.lock:
            self.stats = {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'start_time': None,
                'last_update': None
            }
    
    def close_all_connections(self):
        with self.lock:
            for connection in self.active_connections.values():
                try:
                    connection.close()
                except:
                    pass
            self.active_connections.clear()
    
    def __del__(self):
        self.close_all_connections() as sys_error:
                        print(f"Ошибка получения системной информации для {host}: {sys_error}")
                
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
        
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SSH-Validator") as executor:
            future_to_server = {executor.submit(validate_single, server): server for server in servers}
            
            for future in as_completed(future_to_server):
                try:
                    result = future.result()
                    results.append(result)
                except Exception