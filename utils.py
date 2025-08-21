"""
Utilities for multi-tenancy, security and database operations
"""
from functools import wraps
from flask import g, request, abort
from flask_login import current_user
from models import Company, Warehouse, User, AuditLog
from app import db
import json


def get_current_company():
    """Get current user's company"""
    if current_user.is_authenticated:
        return current_user.company
    return None


def ensure_company_context(f):
    """Decorator to ensure all queries are scoped to current company"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            g.company_id = current_user.company_id
        return f(*args, **kwargs)
    return decorated_function


def company_query(model):
    """Helper to automatically filter queries by company"""
    if not current_user.is_authenticated:
        return model.query.filter_by(id=-1)  # Return empty result
    return model.query.filter_by(company_id=current_user.company_id)


def log_audit(table_name, record_id, action, old_values=None, new_values=None):
    """Log all changes for security auditing"""
    if not current_user.is_authenticated:
        return
    
    audit_log = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        user_id=current_user.id,
        company_id=current_user.company_id,
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)


def create_default_warehouse(company):
    """Create default warehouse for new company"""
    default_warehouse = Warehouse(
        name='Almacén Principal',
        code='MAIN',
        address='Ubicación principal',
        company_id=company.id
    )
    db.session.add(default_warehouse)
    return default_warehouse


def setup_new_company(company_name):
    """Complete setup for a new company"""
    # Create company
    company = Company(
        name=company_name,
        code=Company.generate_code()
    )
    db.session.add(company)
    db.session.flush()  # Get ID
    
    # Create default warehouse
    warehouse = create_default_warehouse(company)
    db.session.flush()
    
    return company, warehouse


def validate_company_access(company_id):
    """Ensure current user can access the specified company"""
    if not current_user.is_authenticated:
        abort(401)
    
    if current_user.company_id != company_id:
        abort(403)
    
    return True


def get_company_warehouses():
    """Get all warehouses for current company"""
    if not current_user.is_authenticated:
        return []
    
    return Warehouse.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()


def generate_sku(company_id, category_name=None):
    """Generate a unique SKU for the company"""
    from models import InventoryItem
    import time
    
    prefix = category_name[:3].upper() if category_name else 'ITM'
    timestamp = str(int(time.time()))[-6:]  # Last 6 digits
    
    counter = 1
    while True:
        sku = f"{prefix}-{timestamp}-{counter:03d}"
        if not InventoryItem.query.filter_by(sku=sku, company_id=company_id).first():
            return sku
        counter += 1


def validate_barcode_format(barcode):
    """Basic barcode validation"""
    if not barcode:
        return True  # Optional field
    
    # Remove spaces and convert to uppercase
    barcode = barcode.strip().upper()
    
    # Basic validation: alphanumeric, no spaces
    if not barcode.replace('-', '').isalnum():
        return False
    
    return len(barcode) >= 6 and len(barcode) <= 50


def search_items_by_barcode(barcode, company_id):
    """Search items by barcode within company"""
    from models import InventoryItem
    
    return InventoryItem.query.filter_by(
        barcode=barcode,
        company_id=company_id
    ).first()