import threading
import functools
from flask import current_app, has_app_context
from typing import Callable, Any, Optional

class AppContextManager:
    
    def __init__(self, app=None):
        self.app = app
        self._local = threading.local()
    
    def set_app(self, app):
        self.app = app
    
    def ensure_context(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if has_app_context():
                return func(*args, **kwargs)
            elif self.app:
                with self.app.app_context():
                    return func(*args, **kwargs)
            else:
                raise RuntimeError("Flask приложение не настроено для AppContextManager")
        
        return wrapper
    
    def run_in_context(self, func: Callable, *args, **kwargs) -> Any:
        if has_app_context():
            return func(*args, **kwargs)
        elif self.app:
            with self.app.app_context():
                return func(*args, **kwargs)
        else:
            raise RuntimeError("Flask приложение не настроено для AppContextManager")
    
    def create_thread_with_context(self, target: Callable, args: tuple = (), 
                                 kwargs: dict = None, name: str = None) -> threading.Thread:
        if kwargs is None:
            kwargs = {}
        
        def wrapped_target():
            if self.app:
                with self.app.app_context():
                    target(*args, **kwargs)
            else:
                target(*args, **kwargs)
        
        return threading.Thread(target=wrapped_target, name=name)

context_manager = AppContextManager()

def with_app_context(func: Callable) -> Callable:
    return context_manager.ensure_context(func)

def run_with_context(app, func: Callable, *args, **kwargs) -> Any:
    if has_app_context():
        return func(*args, **kwargs)
    else:
        with app.app_context():
            return func(*args, **kwargs)

def safe_db_operation(app, operation: Callable, *args, **kwargs) -> tuple[bool, Any, Optional[str]]:
    try:
        if has_app_context():
            result = operation(*args, **kwargs)
            return True, result, None
        else:
            with app.app_context():
                result = operation(*args, **kwargs)
                return True, result, None
    except Exception as e:
        return False, None, str(e)

class ThreadSafeCounter:
    
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.Lock()
    
    def increment(self, amount: int = 1) -> int:
        with self._lock:
            self._value += amount
            return self._value
    
    def decrement(self, amount: int = 1) -> int:
        with self._lock:
            self._value -= amount
            return self._value
    
    def get(self) -> int:
        with self._lock:
            return self._value
    
    def set(self, value: int) -> int:
        with self._lock:
            self._value = value
            return self._value
    
    def reset(self) -> int:
        with self._lock:
            self._value = 0
            return self._value

class BackgroundTaskManager:
    
    def __init__(self, app=None):
        self.app = app
        self.active_tasks = {}
        self.task_counter = ThreadSafeCounter()
        self._lock = threading.Lock()
    
    def set_app(self, app):
        self.app = app
    
    def start_task(self, task_id: str, target: Callable, args: tuple = (), 
                   kwargs: dict = None) -> bool:
        if kwargs is None:
            kwargs = {}
        
        with self._lock:
            if task_id in self.active_tasks:
                return False
        
        def wrapped_task():
            try:
                if self.app:
                    with self.app.app_context():
                        target(*args, **kwargs)
                else:
                    target(*args, **kwargs)
            except Exception as e:
                print(f"Ошибка в фоновой задаче {task_id}: {e}")
            finally:
                with self._lock:
                    self.active_tasks.pop(task_id, None)
        
        thread = threading.Thread(target=wrapped_task, name=f"Task-{task_id}")
        thread.daemon = True
        
        with self._lock:
            self.active_tasks[task_id] = {
                'thread': thread,
                'started_at': threading.current_thread().ident
            }
        
        thread.start()
        return True
    
    def stop_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self.active_tasks:
                self.active_tasks.pop(task_id, None)
                return True
            return False
    
    def is_task_running(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self.active_tasks
    
    def get_active_tasks(self) -> list:
        with self._lock:
            return list(self.active_tasks.keys())
    
    def cleanup_finished_tasks(self):
        with self._lock:
            finished_tasks = []
            for task_id, task_info in self.active_tasks.items():
                if not task_info['thread'].is_alive():
                    finished_tasks.append(task_id)
            
            for task_id in finished_tasks:
                self.active_tasks.pop(task_id, None)

task_manager = BackgroundTaskManager()

class ProgressTracker:
    
    def __init__(self, total: int):
        self.total = total
        self.completed = ThreadSafeCounter()
        self.errors = ThreadSafeCounter()
        self.start_time = None
        self.callbacks = []
        self._lock = threading.Lock()
    
    def start(self):
        import time
        self.start_time = time.time()
    
    def increment_completed(self, callback_data: dict = None):
        completed = self.completed.increment()
        
        if callback_data:
            for callback in self.callbacks:
                try:
                    callback(callback_data)
                except Exception as e:
                    print(f"Ошибка в callback прогресса: {e}")
        
        return completed
    
    def increment_errors(self):
        return self.errors.increment()
    
    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)
    
    def get_progress(self) -> dict:
        completed = self.completed.get()
        errors = self.errors.get()
        
        progress = {
            'total': self.total,
            'completed': completed,
            'errors': errors,
            'percentage': (completed / self.total * 100) if self.total > 0 else 0
        }
        
        if self.start_time:
            import time
            elapsed = time.time() - self.start_time
            progress['elapsed_time'] = elapsed
            
            if completed > 0:
                time_per_item = elapsed / completed
                remaining = self.total - completed
                progress['estimated_time_remaining'] = remaining * time_per_item
                progress['items_per_second'] = completed / elapsed
        
        return progress
    
    def is_complete(self) -> bool:
        return self.completed.get() + self.errors.get() >= self.total

def init_context_utils(app):
    context_manager.set_app(app)
    task_manager.set_app(app)