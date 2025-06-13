"""
Утилиты для диагностики и устранения проблем SSH подключений
"""

import socket
import subprocess
import paramiko
import time
from typing import Dict, List, Tuple, Optional
import re
import threading
from concurrent.futures import ThreadPoolExecutor

class SSHDiagnostics:
    """Класс для диагностики SSH проблем"""
    
    def __init__(self):
        self.common_issues = {
            'ssh_banner': {
                'patterns': [
                    'error reading ssh protocol banner',
                    'ssh protocol banner',
                    'banner timeout'
                ],
                'description': 'Проблема чтения SSH banner',
                'solutions': [
                    'Увеличить banner_timeout до 15-20 секунд',
                    'Уменьшить количество одновременных подключений',
                    'Проверить нагрузку на целевой сервер',
                    'Добавить повторные попытки подключения'
                ],
                'severity': 'medium'
            },
            'timeout': {
                'patterns': [
                    'connection timeout',
                    'timed out',
                    'timeout',
                    'connection timed out'
                ],
                'description': 'Превышение времени ожидания подключения',
                'solutions': [
                    'Увеличить общий timeout до 20-30 секунд',
                    'Проверить сетевую доступность (ping)',
                    'Проверить загрузку сети',
                    'Убедиться в работе SSH сервиса на целевом хосте'
                ],
                'severity': 'high'
            },
            'auth_failed': {
                'patterns': [
                    'authentication failed',
                    'authentication exception',
                    'invalid credentials',
                    'login incorrect'
                ],
                'description': 'Ошибка аутентификации',
                'solutions': [
                    'Проверить правильность логина и пароля',
                    'Убедиться в существовании пользователя на сервере',
                    'Проверить права пользователя на SSH доступ',
                    'Проверить настройки SSH сервера (/etc/ssh/sshd_config)'
                ],
                'severity': 'high'
            },
            'connection_refused': {
                'patterns': [
                    'connection refused',
                    'connection denied',
                    'no route to host'
                ],
                'description': 'Соединение отклонено или невозможно',
                'solutions': [
                    'Проверить, что SSH сервис запущен (systemctl status ssh)',
                    'Проверить правильность порта SSH',
                    'Проверить настройки файрвола',
                    'Убедиться в сетевой доступности хоста'
                ],
                'severity': 'high'
            },
            'permission_denied': {
                'patterns': [
                    'permission denied',
                    'access denied',
                    'operation not permitted'
                ],
                'description': 'Отказ в доступе',
                'solutions': [
                    'Проверить права пользователя',
                    'Убедиться, что пользователь входит в нужные группы',
                    'Проверить настройки AllowUsers в sshd_config',
                    'Проверить SELinux/AppArmor настройки'
                ],
                'severity': 'medium'
            },
            'host_key': {
                'patterns': [
                    'host key verification failed',
                    'known_hosts',
                    'host key mismatch'
                ],
                'description': 'Проблема с ключом хоста',
                'solutions': [
                    'Обновить known_hosts файл',
                    'Использовать AutoAddPolicy в коде',
                    'Проверить, не сменился ли ключ сервера',
                    'Удалить старый ключ из known_hosts'
                ],
                'severity': 'low'
            }
        }
    
    def classify_error(self, error_message: str) -> Dict:
        """
        Классификация ошибки и получение рекомендаций
        
        Args:
            error_message: текст ошибки
            
        Returns:
            Dict с информацией об ошибке и рекомендациями
        """
        error_lower = error_message.lower()
        
        for issue_type, issue_info in self.common_issues.items():
            for pattern in issue_info['patterns']:
                if pattern in error_lower:
                    return {
                        'type': issue_type,
                        'description': issue_info['description'],
                        'solutions': issue_info['solutions'],
                        'severity': issue_info['severity'],
                        'original_error': error_message
                    }
        
        # Если не нашли известную ошибку
        return {
            'type': 'unknown',
            'description': 'Неизвестная ошибка',
            'solutions': [
                'Проверить сетевое подключение',
                'Проверить корректность данных сервера',
                'Попробовать подключиться вручную через SSH клиент',
                'Проверить логи на целевом сервере'
            ],
            'severity': 'unknown',
            'original_error': error_message
        }
    
    def diagnose_connection(self, host: str, port: int, username: str = None, 
                          timeout: int = 10) -> Dict:
        """
        Комплексная диагностика подключения к серверу
        
        Args:
            host: хост для проверки
            port: порт SSH
            username: имя пользователя (опционально)
            timeout: таймаут для проверок
            
        Returns:
            Dict с результатами диагностики
        """
        diagnosis = {
            'host': host,
            'port': port,
            'tests': {},
            'recommendations': [],
            'overall_status': 'unknown'
        }
        
        # Тест 1: Ping доступность
        diagnosis['tests']['ping'] = self._test_ping(host, timeout)
        
        # Тест 2: Проверка порта
        diagnosis['tests']['port'] = self._test_port(host, port, timeout)
        
        # Тест 3: SSH баннер
        diagnosis['tests']['ssh_banner'] = self._test_ssh_banner(host, port, timeout)
        
        # Тест 4: DNS разрешение
        diagnosis['tests']['dns'] = self._test_dns(host)
        
        # Анализ результатов и формирование рекомендаций
        diagnosis['recommendations'] = self._analyze_test_results(diagnosis['tests'])
        diagnosis['overall_status'] = self._get_overall_status(diagnosis['tests'])
        
        return diagnosis
    
    def _test_ping(self, host: str, timeout: int) -> Dict:
        """Тест ping доступности"""
        try:
            # Используем ping команду системы
            result = subprocess.run(
                ['ping', '-c', '3', '-W', str(timeout), host],
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )
            
            if result.returncode == 0:
                # Извлекаем время отклика
                output = result.stdout
                time_match = re.search(r'time=(\d+\.?\d*)ms', output)
                avg_time = float(time_match.group(1)) if time_match else None
                
                return {
                    'status': 'success',
                    'message': 'Хост доступен по ping',
                    'avg_time_ms': avg_time,
                    'details': output
                }
            else:
                return {
                    'status': 'failed',
                    'message': 'Хост недоступен по ping',
                    'details': result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                'status': 'failed',
                'message': 'Превышен таймаут ping',
                'details': 'Ping timeout'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Ошибка выполнения ping: {str(e)}',
                'details': str(e)
            }
    
    def _test_port(self, host: str, port: int, timeout: int) -> Dict:
        """Тест доступности порта"""
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            result = sock.connect_ex((host, port))
            connect_time = (time.time() - start_time) * 1000  # в миллисекундах
            
            sock.close()
            
            if result == 0:
                return {
                    'status': 'success',
                    'message': f'Порт {port} открыт и доступен',
                    'connect_time_ms': round(connect_time, 2)
                }
            else:
                return {
                    'status': 'failed',
                    'message': f'Порт {port} недоступен или закрыт',
                    'error_code': result
                }
        except socket.timeout:
            return {
                'status': 'failed',
                'message': f'Таймаут подключения к порту {port}',
                'details': 'Connection timeout'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Ошибка проверки порта: {str(e)}',
                'details': str(e)
            }
    
    def _test_ssh_banner(self, host: str, port: int, timeout: int) -> Dict:
        """Тест получения SSH баннера"""
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            sock.connect((host, port))
            
            # Читаем SSH баннер
            banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
            banner_time = (time.time() - start_time) * 1000
            
            sock.close()
            
            if banner.startswith('SSH-'):
                return {
                    'status': 'success',
                    'message': 'SSH баннер получен успешно',
                    'banner': banner,
                    'banner_time_ms': round(banner_time, 2)
                }
            else:
                return {
                    'status': 'failed',
                    'message': 'Получен некорректный SSH баннер',
                    'banner': banner
                }
        except socket.timeout:
            return {
                'status': 'failed',
                'message': 'Таймаут получения SSH баннера',
                'details': 'Banner timeout'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Ошибка получения SSH баннера: {str(e)}',
                'details': str(e)
            }
    
    def _test_dns(self, host: str) -> Dict:
        """Тест DNS разрешения"""
        try:
            start_time = time.time()
            ip_address = socket.gethostbyname(host)
            dns_time = (time.time() - start_time) * 1000
            
            return {
                'status': 'success',
                'message': 'DNS разрешение успешно',
                'ip_address': ip_address,
                'dns_time_ms': round(dns_time, 2)
            }
        except socket.gaierror as e:
            return {
                'status': 'failed',
                'message': 'Ошибка DNS разрешения',
                'details': str(e)
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Ошибка DNS: {str(e)}',
                'details': str(e)
            }
    
    def _analyze_test_results(self, tests: Dict) -> List[str]:
        """Анализ результатов тестов и формирование рекомендаций"""
        recommendations = []
        
        # Анализ ping
        if tests['ping']['status'] == 'failed':
            recommendations.append('Хост недоступен по сети. Проверьте сетевое подключение и правильность адреса.')
        elif tests['ping']['status'] == 'success' and tests['ping'].get('avg_time_ms', 0) > 1000:
            recommendations.append('Высокая задержка сети (>1сек). Рассмотрите увеличение таймаутов.')
        
        # Анализ порта
        if tests['port']['status'] == 'failed':
            recommendations.append('SSH порт недоступен. Проверьте работу SSH сервиса и настройки файрвола.')
        elif tests['port']['status'] == 'success' and tests['port'].get('connect_time_ms', 0) > 5000:
            recommendations.append('Медленное подключение к SSH порту. Проверьте нагрузку на сервер.')
        
        # Анализ SSH баннера
        if tests['ssh_banner']['status'] == 'failed':
            if 'timeout' in tests['ssh_banner'].get('details', '').lower():
                recommendations.append('Таймаут SSH баннера. Увеличьте banner_timeout или уменьшите нагрузку на сервер.')
            else:
                recommendations.append('Проблема с SSH сервисом. Проверьте конфигурацию SSH сервера.')
        
        # Анализ DNS
        if tests['dns']['status'] == 'failed':
            recommendations.append('Проблема DNS разрешения. Попробуйте использовать IP адрес напрямую.')
        elif tests['dns']['status'] == 'success' and tests['dns'].get('dns_time_ms', 0) > 1000:
            recommendations.append('Медленное DNS разрешение. Рассмотрите использование IP адреса.')
        
        if not recommendations:
            recommendations.append('Все базовые тесты пройдены успешно. Проблема может быть в аутентификации.')
        
        return recommendations
    
    def _get_overall_status(self, tests: Dict) -> str:
        """Определение общего статуса на основе результатов тестов"""
        statuses = [test['status'] for test in tests.values()]
        
        if all(status == 'success' for status in statuses):
            return 'healthy'
        elif any(status == 'success' for status in statuses):
            return 'partial'
        else:
            return 'failed'
    
    def batch_diagnose(self, servers: List[Tuple[str, int]], max_workers: int = 10) -> Dict:
        """
        Пакетная диагностика серверов
        
        Args:
            servers: список кортежей (host, port)
            max_workers: количество потоков
            
        Returns:
            Dict с результатами диагностики
        """
        results = {}
        
        def diagnose_single(server_data):
            host, port = server_data
            return host, self.diagnose_connection(host, port)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_server = {
                executor.submit(diagnose_single, server): server 
                for server in servers
            }
            
            for future in future_to_server:
                try:
                    host, diagnosis = future.result(timeout=30)
                    results[host] = diagnosis
                except Exception as e:
                    server = future_to_server[future]
                    results[server[0]] = {
                        'host': server[0],
                        'port': server[1],
                        'error': f'Ошибка диагностики: {str(e)}',
                        'overall_status': 'error'
                    }
        
        return results
    
    def generate_fix_script(self, diagnosis: Dict) -> str:
        """
        Генерация скрипта для автоматического исправления проблем
        
        Args:
            diagnosis: результат диагностики
            
        Returns:
            bash скрипт для исправления проблем
        """
        script_lines = [
            '#!/bin/bash',
            f'# Скрипт исправления проблем для {diagnosis["host"]}:{diagnosis["port"]}',
            f'# Сгенерирован автоматически',
            '',
            'echo "Начинаем диагностику и исправление проблем..."',
            ''
        ]
        
        tests = diagnosis.get('tests', {})
        
        # Исправления для различных проблем
        if tests.get('ping', {}).get('status') == 'failed':
            script_lines.extend([
                '# Проверка сетевой доступности',
                f'echo "Проверяем ping до {diagnosis["host"]}..."',
                f'ping -c 3 {diagnosis["host"]} || echo "Хост недоступен"',
                ''
            ])
        
        if tests.get('port', {}).get('status') == 'failed':
            script_lines.extend([
                '# Проверка SSH порта',
                f'echo "Проверяем SSH порт {diagnosis["port"]}..."',
                f'nc -zv {diagnosis["host"]} {diagnosis["port"]} || echo "SSH порт недоступен"',
                ''
            ])
        
        if tests.get('ssh_banner', {}).get('status') == 'failed':
            script_lines.extend([
                '# Проверка SSH сервиса',
                f'echo "Проверяем SSH баннер..."',
                f'timeout 10 telnet {diagnosis["host"]} {diagnosis["port"]} || echo "SSH сервис недоступен"',
                ''
            ])
        
        script_lines.extend([
            'echo "Диагностика завершена."',
            'echo "Проверьте вывод выше для выявления проблем."'
        ])
        
        return '\n'.join(script_lines)

# Функции-помощники для интеграции с Flask приложением
def diagnose_server_problems(host: str, port: int, error_message: str = None) -> Dict:
    """
    Диагностика проблем конкретного сервера
    
    Args:
        host: хост сервера
        port: порт SSH
        error_message: сообщение об ошибке (если есть)
        
    Returns:
        Dict с результатами диагностики и рекомендациями
    """
    diagnostics = SSHDiagnostics()
    
    # Выполняем полную диагностику
    diagnosis = diagnostics.diagnose_connection(host, port)
    
    # Если есть сообщение об ошибке, классифицируем его
    if error_message:
        error_analysis = diagnostics.classify_error(error_message)
        diagnosis['error_analysis'] = error_analysis
    
    return diagnosis

def get_optimization_recommendations(servers_stats: Dict) -> List[Dict]:
    """
    Получение рекомендаций по оптимизации на основе статистики серверов
    
    Args:
        servers_stats: статистика серверов и ошибок
        
    Returns:
        List рекомендаций
    """
    recommendations = []
    
    total_servers = servers_stats.get('total', 0)
    failed_servers = servers_stats.get('failed', 0)
    error_types = servers_stats.get('error_types', {})
    
    if total_servers == 0:
        return recommendations
    
    failure_rate = (failed_servers / total_servers) * 100
    
    # Общие рекомендации по failure rate
    if failure_rate > 50:
        recommendations.append({
            'type': 'critical',
            'title': 'Высокий процент неудачных подключений',
            'description': f'Неудачные подключения: {failure_rate:.1f}%',
            'recommendations': [
                'Проверьте сетевое подключение',
                'Увеличьте таймауты подключения',
                'Уменьшите количество одновременных потоков',
                'Проверьте актуальность учетных данных'
            ]
        })
    
    # Рекомендации по типам ошибок
    banner_errors = error_types.get('SSH Banner', 0)
    if banner_errors > total_servers * 0.2:
        recommendations.append({
            'type': 'warning',
            'title': 'Много ошибок SSH Banner',
            'description': f'Ошибки banner: {banner_errors} ({banner_errors/total_servers*100:.1f}%)',
            'recommendations': [
                'Увеличьте banner_timeout до 15-20 секунд',
                'Уменьшите количество одновременных подключений',
                'Добавьте повторные попытки подключения'
            ]
        })
    
    timeout_errors = error_types.get('Timeout', 0)
    if timeout_errors > total_servers * 0.15:
        recommendations.append({
            'type': 'warning',
            'title': 'Частые таймауты подключения',
            'description': f'Таймауты: {timeout_errors} ({timeout_errors/total_servers*100:.1f}%)',
            'recommendations': [
                'Увеличьте общий timeout до 25-30 секунд',
                'Проверьте качество сетевого подключения',
                'Рассмотрите использование локальных серверов для тестов'
            ]
        })
    
    return recommendations