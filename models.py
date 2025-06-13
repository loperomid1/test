from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class SSHServer(db.Model):
    __tablename__ = 'ssh_servers'
    
    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    os_info = db.Column(db.Text)
    cpu_info = db.Column(db.Text)
    memory_info = db.Column(db.Text)
    disk_info = db.Column(db.Text)
    kernel_version = db.Column(db.String(100))
    architecture = db.Column(db.String(50))
    uptime_info = db.Column(db.Text)
    
    total_memory_mb = db.Column(db.Integer)
    used_memory_mb = db.Column(db.Integer)
    disk_usage_percent = db.Column(db.Integer)
    cpu_cores = db.Column(db.Integer)
    
    is_valid = db.Column(db.Boolean, default=None)
    last_check = db.Column(db.DateTime)
    last_error = db.Column(db.Text)
    
    notes = db.Column(db.Text)
    tags = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SSHServer {self.username}@{self.host}:{self.port}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'country': self.country,
            'city': self.city,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'os_info': self.os_info,
            'cpu_info': self.cpu_info,
            'memory_info': self.memory_info,
            'disk_info': self.disk_info,
            'kernel_version': self.kernel_version,
            'architecture': self.architecture,
            'uptime_info': self.uptime_info,
            'total_memory_mb': self.total_memory_mb,
            'used_memory_mb': self.used_memory_mb,
            'disk_usage_percent': self.disk_usage_percent,
            'cpu_cores': self.cpu_cores,
            'is_valid': self.is_valid,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_error': self.last_error,
            'notes': self.notes,
            'tags': self.tags.split(',') if self.tags else [],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    @property
    def memory_usage_percent(self):
        if self.total_memory_mb and self.used_memory_mb and self.total_memory_mb > 0:
            return round((self.used_memory_mb / self.total_memory_mb) * 100, 1)
        return None
    
    @property
    def total_memory_gb(self):
        if self.total_memory_mb:
            return round(self.total_memory_mb / 1024, 1)
        return None
    
    @property
    def os_short_name(self):
        if not self.os_info:
            return 'Unknown'
        
        os_lower = self.os_info.lower()
        if 'ubuntu' in os_lower:
            return 'Ubuntu'
        elif 'debian' in os_lower:
            return 'Debian'
        elif 'centos' in os_lower:
            return 'CentOS'
        elif 'red hat' in os_lower or 'rhel' in os_lower:
            return 'RHEL'
        elif 'fedora' in os_lower:
            return 'Fedora'
        elif 'suse' in os_lower:
            return 'SUSE'
        elif 'alpine' in os_lower:
            return 'Alpine'
        elif 'arch' in os_lower:
            return 'Arch'
        else:
            return 'Linux'
    
    @property
    def status_color(self):
        if self.is_valid is None:
            return 'warning'
        elif self.is_valid:
            return 'success'
        else:
            return 'danger'
    
    @property
    def status_text(self):
        if self.is_valid is None:
            return 'Не проверен'
        elif self.is_valid:
            return 'Доступен'
        else:
            return 'Недоступен'