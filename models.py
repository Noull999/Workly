from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import string

class Company(db.Model):
    """Multi-tenancy: Each company has its own data isolated"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)  # URL-friendly identifier
    logo_url = db.Column(db.String(255), nullable=True)  # URL del logo
    primary_color = db.Column(db.String(7), default='#007bff')  # Color primario en hex
    secondary_color = db.Column(db.String(7), default='#6c757d')  # Color secundario en hex
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Módulos activados
    module_pos = db.Column(db.Boolean, default=False)
    module_appointments = db.Column(db.Boolean, default=False)
    module_portfolio = db.Column(db.Boolean, default=False)
    
    # Configuración para página de presentación
    portfolio_description = db.Column(db.Text, nullable=True)
    portfolio_services = db.Column(db.Text, nullable=True)  # JSON o texto
    contact_phone = db.Column(db.String(50), nullable=True)
    contact_whatsapp = db.Column(db.String(50), nullable=True)
    contact_email = db.Column(db.String(120), nullable=True)
    contact_address = db.Column(db.String(200), nullable=True)
    social_facebook = db.Column(db.String(200), nullable=True)
    social_instagram = db.Column(db.String(200), nullable=True)
    social_linkedin = db.Column(db.String(200), nullable=True)
    
    # Relationships
    users = db.relationship('User', backref='company', lazy=True, cascade='all, delete-orphan')
    warehouses = db.relationship('Warehouse', backref='company', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='company', lazy=True, cascade='all, delete-orphan')
    items = db.relationship('InventoryItem', backref='company', lazy=True, cascade='all, delete-orphan')
    services = db.relationship('Service', backref='company', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='company', lazy=True, cascade='all, delete-orphan')
    pos_sales = db.relationship('Sale', backref='company', lazy=True, cascade='all, delete-orphan')
    
    @classmethod
    def generate_code(cls):
        """Generate a unique company code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if not cls.query.filter_by(code=code).first():
                return code
    
    def __repr__(self):
        return f'<Company {self.name}>'

class Warehouse(db.Model):
    """Multiple warehouses/locations per company"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False)  # Short code like 'MAIN', 'SEC1'
    address = db.Column(db.String(200))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('InventoryItem', backref='warehouse', lazy=True)
    
    # Unique constraints
    __table_args__ = (
        db.UniqueConstraint('code', 'company_id', name='unique_warehouse_code_per_company'),
    )
    
    def __repr__(self):
        return f'<Warehouse {self.name}>'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='empleado')  # admin_global, admin_empresa, empleado
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    
    # Relationship with inventory items
    inventory_items = db.relationship('InventoryItem', backref='owner', lazy=True, cascade='all, delete-orphan')
    
    # Unique constraints per company (username and email unique within each company)
    __table_args__ = (
        db.UniqueConstraint('username', 'company_id', name='unique_username_per_company'),
        db.UniqueConstraint('email', 'company_id', name='unique_email_per_company'),
    )
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin_global(self):
        return self.role == 'admin_global'
    
    def is_admin_empresa(self):
        return self.role == 'admin_empresa'
    
    def is_empleado(self):
        return self.role == 'empleado'
    
    def can_manage_company(self, company_id):
        """Check if user can manage a specific company"""
        if self.is_admin_global():
            return True
        if self.is_admin_empresa() and self.company_id == company_id:
            return True
        return False
    
    def can_manage_users(self, target_company_id=None):
        """Check if user can manage users"""
        if self.is_admin_global():
            return True
        if self.is_admin_empresa() and (target_company_id is None or self.company_id == target_company_id):
            return True
        return False
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with inventory items
    items = db.relationship('InventoryItem', backref='category_ref', lazy=True)
    
    # Unique constraint per company
    __table_args__ = (
        db.UniqueConstraint('name', 'company_id', name='unique_category_per_company'),
    )
    
    def __repr__(self):
        return f'<Category {self.name}>'

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    minimum_stock = db.Column(db.Integer, default=5)
    sku = db.Column(db.String(50))
    barcode = db.Column(db.String(100))  # Support for barcodes/QR codes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False)
    
    # Unique constraints per company
    __table_args__ = (
        db.UniqueConstraint('sku', 'company_id', name='unique_sku_per_company'),
        db.UniqueConstraint('barcode', 'company_id', name='unique_barcode_per_company'),
    )
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.minimum_stock
    
    @classmethod
    def generate_barcode(cls, company_id):
        """Generate a unique barcode within the company"""
        import time
        while True:
            # Simple barcode: timestamp + random digits
            barcode = f"{int(time.time())}{secrets.randbelow(999):03d}"
            if not cls.query.filter_by(barcode=barcode, company_id=company_id).first():
                return barcode
    
    def __repr__(self):
        return f'<InventoryItem {self.name}>'


class AuditLog(db.Model):
    """Security: Track all changes to data"""
    id = db.Column(db.Integer, primary_key=True)
    table_name = db.Column(db.String(64), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    old_values = db.Column(db.Text)  # JSON string of old values
    new_values = db.Column(db.Text)  # JSON string of new values
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))  # IPv6 compatible
    
    def __repr__(self):
        return f'<AuditLog {self.action} on {self.table_name}>'


# ===== MÓDULOS ADICIONALES =====

class Service(db.Model):
    """Servicios para el módulo de citas"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    price = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    appointments = db.relationship('Appointment', backref='service', lazy=True)
    
    def __repr__(self):
        return f'<Service {self.name}>'


class Appointment(db.Model):
    """Citas/Reservas"""
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_phone = db.Column(db.String(50), nullable=True)
    client_email = db.Column(db.String(120), nullable=True)
    appointment_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pendiente')  # pendiente, confirmada, cancelada, completada
    notes = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=True)  # Si fue creada desde la página pública
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Usuario que la gestiona
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Appointment {self.client_name} - {self.appointment_date}>'


class Sale(db.Model):
    """Ventas del módulo POS"""
    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), nullable=False)  # Número de venta
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(50), default='efectivo')  # efectivo, tarjeta, transferencia
    status = db.Column(db.String(20), default='completada')  # completada, cancelada, pendiente
    notes = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Vendedor
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')
    
    @classmethod
    def generate_sale_number(cls, company_id):
        """Generate unique sale number"""
        import time
        timestamp = int(time.time())
        count = cls.query.filter_by(company_id=company_id).count() + 1
        return f"V{timestamp}-{count:04d}"
    
    def __repr__(self):
        return f'<Sale {self.sale_number}>'


class SaleItem(db.Model):
    """Items de cada venta"""
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    
    # Relationship
    inventory_item = db.relationship('InventoryItem', backref='sales')
    
    def __repr__(self):
        return f'<SaleItem {self.quantity}x {self.inventory_item.name if self.inventory_item else "Unknown"}>'
