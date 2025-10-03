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
    company_email = db.Column(db.String(120), unique=True, nullable=False)  # Email principal de la empresa
    logo_url = db.Column(db.String(255), nullable=True)  # URL del logo
    primary_color = db.Column(db.String(7), default='#007bff')  # Color primario en hex
    secondary_color = db.Column(db.String(7), default='#6c757d')  # Color secundario en hex
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Módulos activados
    module_inventory = db.Column(db.Boolean, default=True)  # Base del sistema
    module_pos = db.Column(db.Boolean, default=False)
    module_appointments = db.Column(db.Boolean, default=False)
    module_portfolio = db.Column(db.Boolean, default=False)
    module_scrum = db.Column(db.Boolean, default=False)
    module_notion = db.Column(db.Boolean, default=False)
    
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
    scrum_boards = db.relationship('Board', backref='company', lazy=True, cascade='all, delete-orphan')
    
    @classmethod
    def generate_code(cls):
        """Generate a unique company code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if not cls.query.filter_by(code=code).first():
                return code
    
    def __repr__(self):
        return f'<Company {self.name} ({self.company_email})>'

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
    
    # Preferencias de módulos para super admin (solo aplicable si role es admin_global)
    admin_pref_inventory = db.Column(db.Boolean, default=True)
    admin_pref_pos = db.Column(db.Boolean, default=True)
    admin_pref_appointments = db.Column(db.Boolean, default=True)
    admin_pref_portfolio = db.Column(db.Boolean, default=True)
    admin_pref_scrum = db.Column(db.Boolean, default=True)
    admin_pref_notion = db.Column(db.Boolean, default=True)
    
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
    price = db.Column(db.Numeric(10, 2), nullable=True)  # Optional price field
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
    additional_info = db.Column(db.Text)  # JSON string for additional context
    
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
    offline_uuid = db.Column(db.String(36), nullable=True, unique=True)  # UUID para ventas offline
    offline_timestamp = db.Column(db.DateTime, nullable=True)  # Timestamp original offline
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')
    payment_details = db.relationship('PaymentDetail', backref='sale', lazy=True, cascade='all, delete-orphan')
    cash_session_id = db.Column(db.Integer, db.ForeignKey('cash_session.id'), nullable=True)
    
    @classmethod
    def generate_sale_number(cls, company_id):
        """Generate unique sale number"""
        import time
        timestamp = int(time.time())
        count = cls.query.filter_by(company_id=company_id).count() + 1
        return f"V{timestamp}-{count:04d}"
    
    def get_cash_amount(self):
        """Obtiene el monto pagado en efectivo"""
        from typing import cast
        from decimal import Decimal
        payments = cast(list, self.payment_details)
        cash_payments = [p for p in payments if p.payment_method == 'efectivo']
        return sum([float(p.amount) for p in cash_payments])
    
    def get_total_paid(self):
        """Obtiene el total pagado (suma de todos los métodos)"""
        from typing import cast
        payments = cast(list, self.payment_details)
        return sum([float(p.amount) for p in payments])
    
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


# ===== POS ADVANCED MODELS =====

class CashSession(db.Model):
    """Sesiones de caja diaria - Apertura y cierre de caja"""
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    opening_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # Monto inicial
    closing_amount = db.Column(db.Numeric(10, 2), nullable=True)  # Monto final
    expected_amount = db.Column(db.Numeric(10, 2), nullable=True)  # Monto esperado
    difference_amount = db.Column(db.Numeric(10, 2), nullable=True)  # Diferencia
    total_sales = db.Column(db.Numeric(10, 2), default=0)  # Total ventas
    total_expenses = db.Column(db.Numeric(10, 2), default=0)  # Total egresos
    status = db.Column(db.String(20), default='open')  # open, closed
    notes = db.Column(db.Text)
    opened_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    sales = db.relationship('Sale', backref='cash_session', lazy=True)
    expenses = db.relationship('CashExpense', backref='cash_session', lazy=True)
    opened_by = db.relationship('User', foreign_keys=[opened_by_id], backref='opened_sessions')
    closed_by = db.relationship('User', foreign_keys=[closed_by_id], backref='closed_sessions')
    
    __table_args__ = (
        db.UniqueConstraint('session_date', 'company_id', name='unique_session_per_date_per_company'),
    )
    
    def calculate_expected_amount(self):
        """Calcula el monto esperado en caja"""
        from typing import cast
        sales_list = cast(list, self.sales)
        expenses_list = cast(list, self.expenses)
        cash_sales = sum([s.get_cash_amount() for s in sales_list])
        cash_expenses = sum([float(e.amount) for e in expenses_list])
        return float(self.opening_amount) + cash_sales - cash_expenses
    
    def __repr__(self):
        return f'<CashSession {self.session_date} - {self.status}>'


class PaymentDetail(db.Model):
    """Detalles de pago - Soporte para múltiples métodos de pago por venta"""
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # efectivo, tarjeta, transferencia, vale
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reference = db.Column(db.String(100), nullable=True)  # Número de voucher, referencia, etc.
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<PaymentDetail {self.payment_method}: ${self.amount}>'


class CashExpense(db.Model):
    """Egresos de caja diarios"""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), default='general')  # suministros, servicios, general, etc.
    receipt_number = db.Column(db.String(50), nullable=True)
    cash_session_id = db.Column(db.Integer, db.ForeignKey('cash_session.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CashExpense {self.description}: ${self.amount}>'


class OfflineSync(db.Model):
    """Registro de ventas offline pendientes de sincronización"""
    id = db.Column(db.Integer, primary_key=True)
    sale_data = db.Column(db.JSON, nullable=False)  # Datos de la venta en JSON
    sync_status = db.Column(db.String(20), default='pending')  # pending, synced, error
    error_message = db.Column(db.Text, nullable=True)
    attempts = db.Column(db.Integer, default=0)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<OfflineSync {self.sync_status} - {self.created_at}>'


# ===== SCRUM LITE MODULE =====

class Board(db.Model):
    """Tableros Kanban para Scrum Lite"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    columns = db.relationship('Column', backref='board', lazy=True, cascade='all, delete-orphan', order_by='Column.position')
    sprints = db.relationship('Sprint', backref='board', lazy=True, cascade='all, delete-orphan')
    tasks = db.relationship('Task', backref='board', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Board {self.name}>'


class Column(db.Model):
    """Columnas del tablero Kanban"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    color = db.Column(db.String(7), default='#6c757d')
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='column', lazy=True, order_by='Task.position')
    
    def __repr__(self):
        return f'<Column {self.name}>'


class Sprint(db.Model):
    """Sprints/Iteraciones"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='sprint', lazy=True)
    
    def __repr__(self):
        return f'<Sprint {self.name}>'


class Task(db.Model):
    """Tareas del tablero"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='to_do')  # to_do, in_progress, done
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    position = db.Column(db.Integer, nullable=False, default=0)
    story_points = db.Column(db.Integer, default=1)
    due_date = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    column_id = db.Column(db.Integer, db.ForeignKey('column.id'), nullable=False)
    sprint_id = db.Column(db.Integer, db.ForeignKey('sprint.id'), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    comments = db.relationship('TaskComment', backref='task', lazy=True, cascade='all, delete-orphan')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_tasks')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_tasks')
    
    def __repr__(self):
        return f'<Task {self.title[:30]}>'


class TaskComment(db.Model):
    """Comentarios en tareas"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    author = db.relationship('User', backref='task_comments')
    
    def __repr__(self):
        return f'<TaskComment by {self.author.username if self.author else "Unknown"}>'


# ===== MÓDULO NOTION =====

class NotionPage(db.Model):
    """Páginas del wiki/colaborativo tipo Notion"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(250), nullable=False)  # URL-friendly title
    icon = db.Column(db.String(10), default='📄')  # Emoji icon
    is_public = db.Column(db.Boolean, default=False)  # Visible to all in company
    is_template = db.Column(db.Boolean, default=False)  # Es una plantilla
    parent_id = db.Column(db.Integer, db.ForeignKey('notion_page.id'), nullable=True)  # Jerarquía
    position = db.Column(db.Integer, default=0)  # Orden en sidebar
    
    # Access control
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    blocks = db.relationship('NotionBlock', backref='page', lazy=True, cascade='all, delete-orphan', order_by='NotionBlock.position')
    permissions = db.relationship('NotionPermission', backref='page', lazy=True, cascade='all, delete-orphan')
    child_pages = db.relationship('NotionPage', backref=db.backref('parent', remote_side=[id]), lazy=True)
    creator = db.relationship('User', backref='created_pages')
    module_links = db.relationship('ModuleLink', 
                                   primaryjoin="and_(NotionPage.id==ModuleLink.source_id, ModuleLink.source_module=='notion')",
                                   foreign_keys='ModuleLink.source_id',
                                   lazy=True, cascade='all, delete-orphan')
    
    # Unique constraints
    __table_args__ = (
        db.UniqueConstraint('slug', 'company_id', name='unique_page_slug_per_company'),
    )
    
    def __repr__(self):
        return f'<NotionPage {self.title}>'


class NotionBlock(db.Model):
    """Bloques de contenido en las páginas"""
    id = db.Column(db.Integer, primary_key=True)
    block_type = db.Column(db.String(20), nullable=False)  # text, heading1, heading2, heading3, list, checklist, file
    content = db.Column(db.Text)  # Contenido del bloque
    properties = db.Column(db.Text)  # JSON con propiedades adicionales (formato, color, etc.)
    position = db.Column(db.Integer, default=0)
    
    page_id = db.Column(db.Integer, db.ForeignKey('notion_page.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<NotionBlock {self.block_type}>'


class NotionPermission(db.Model):
    """Permisos de acceso a páginas"""
    id = db.Column(db.Integer, primary_key=True)
    permission_type = db.Column(db.String(20), nullable=False)  # read, edit, admin
    
    page_id = db.Column(db.Integer, db.ForeignKey('notion_page.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    granted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notion_permissions')
    granted_by = db.relationship('User', foreign_keys=[granted_by_id])
    
    # Unique constraints
    __table_args__ = (
        db.UniqueConstraint('page_id', 'user_id', name='unique_permission_per_user_page'),
    )
    
    def __repr__(self):
        return f'<NotionPermission {self.permission_type} for {self.user.username}>'


class NotionChecklist(db.Model):
    """Listas de tareas colaborativas"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    checklist_type = db.Column(db.String(30), default='general')  # general, inventory_restock, daily_cash, etc.
    
    page_id = db.Column(db.Integer, db.ForeignKey('notion_page.id'), nullable=True)  # Opcional, puede estar en una página
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('NotionChecklistItem', backref='checklist', lazy=True, cascade='all, delete-orphan', order_by='NotionChecklistItem.position')
    creator = db.relationship('User', backref='created_checklists')
    
    def __repr__(self):
        return f'<NotionChecklist {self.title}>'


class NotionChecklistItem(db.Model):
    """Items de las listas de tareas"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    position = db.Column(db.Integer, default=0)
    due_date = db.Column(db.DateTime, nullable=True)
    
    checklist_id = db.Column(db.Integer, db.ForeignKey('notion_checklist.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_checklist_items')
    completed_by = db.relationship('User', foreign_keys=[completed_by_id])
    
    def __repr__(self):
        return f'<NotionChecklistItem {self.content[:50]}>'


# ===== INTEGRACIONES ENTRE MÓDULOS =====

class ModuleLink(db.Model):
    """Enlaces/conexiones entre diferentes módulos"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Módulo origen
    source_module = db.Column(db.String(20), nullable=False)  # notion, scrum, pos, appointments, inventory
    source_id = db.Column(db.Integer, nullable=False)  # ID del objeto en el módulo origen
    
    # Módulo destino
    target_module = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    
    # Información adicional del enlace
    link_type = db.Column(db.String(30), default='reference')  # reference, dependency, related
    description = db.Column(db.String(200))  # Descripción del enlace
    
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    created_by = db.relationship('User', backref='created_module_links')
    
    def __repr__(self):
        return f'<ModuleLink {self.source_module}:{self.source_id} -> {self.target_module}:{self.target_id}>'


# ===== MEJORAS SCRUM LITE =====

class CompletedTask(db.Model):
    """Historial de tareas completadas con trazabilidad"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Datos de la tarea original
    original_task_id = db.Column(db.Integer, nullable=False)  # ID de la tarea original
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    story_points = db.Column(db.Integer, default=1)
    priority = db.Column(db.String(20), default='medium')
    
    # Información del board/sprint
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    sprint_id = db.Column(db.Integer, db.ForeignKey('sprint.id'), nullable=True)
    column_name = db.Column(db.String(100), nullable=False)  # Nombre de la columna donde estaba
    
    # Usuarios involucrados
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False)  # Cuando se creó la tarea original
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)  # Cuando se completó
    
    # Comentarios finales
    completion_notes = db.Column(db.Text)  # Comentarios al completar
    
    # Relationships
    board = db.relationship('Board', backref='completed_tasks')
    sprint = db.relationship('Sprint', backref='completed_tasks')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='completed_assigned_tasks')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='completed_created_tasks')
    completed_by = db.relationship('User', foreign_keys=[completed_by_id], backref='completed_tasks_done')
    
    def __repr__(self):
        return f'<CompletedTask {self.title[:30]}>'

class PublicPage(db.Model):
    """Página pública personalizada para usuarios específicos"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False, default='Página oficial de Yanglee')
    description = db.Column(db.Text, nullable=True)  # Biografía corta editable
    primary_color = db.Column(db.String(7), default='#ff6600')  # Color principal
    secondary_color = db.Column(db.String(7), default='#1a1a1a')  # Color secundario
    background_type = db.Column(db.String(20), default='color')  # color, gradient, image
    background_value = db.Column(db.String(500), nullable=True)  # Valor según tipo
    profile_image_url = db.Column(db.String(500), nullable=True)  # Avatar del usuario
    banner_image_url = db.Column(db.String(500), nullable=True)  # Portada
    social_links = db.Column(db.Text, nullable=True)  # JSON con redes sociales
    sections = db.Column(db.Text, nullable=True)  # JSON con bloques configurables
    animations_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('public_page', uselist=False))
    
    def __repr__(self):
        return f'<PublicPage {self.title} - User {self.user_id}>'


class Clip(db.Model):
    """Clips de video asociados a usuarios (máximo 3 por usuario)"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    order_position = db.Column(db.Integer, default=0)  # Orden de visualización
    is_featured = db.Column(db.Boolean, default=False)  # Marcar como clip destacado
    featured_thumbnail_url = db.Column(db.String(500), nullable=True)  # Imagen para clip destacado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('clips', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Clip {self.title or "Sin título"} - User {self.user_id}>'
