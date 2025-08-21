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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    users = db.relationship('User', backref='company', lazy=True, cascade='all, delete-orphan')
    warehouses = db.relationship('Warehouse', backref='company', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='company', lazy=True, cascade='all, delete-orphan')
    items = db.relationship('InventoryItem', backref='company', lazy=True, cascade='all, delete-orphan')
    
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
    
    def __repr__(self):
        return f'<User {self.username}>'

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
