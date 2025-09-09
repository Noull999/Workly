"""
Utilities for multi-tenancy, security and database operations
"""
from functools import wraps
from flask import g, request, abort
from flask_login import current_user
from models import Company, Warehouse, User, AuditLog
from app import db
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal


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


def serialize_json(obj):
    """Custom JSON serializer that handles Decimal objects"""
    def convert_decimal(o):
        if isinstance(o, Decimal):
            return float(o)
        elif isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, dict):
            return {k: convert_decimal(v) for k, v in o.items()}
        elif isinstance(o, list):
            return [convert_decimal(item) for item in o]
        return o
    
    if obj is None:
        return None
    return json.dumps(convert_decimal(obj))


def log_audit(table_name, record_id, action, old_values=None, new_values=None, additional_context=None):
    """Enhanced audit logging with contextual information"""
    if not current_user.is_authenticated:
        return
    
    try:
        # Enhanced context information
        user_agent = request.headers.get('User-Agent', 'unknown')[:200] if hasattr(request, 'headers') else 'unknown'
        
        context = {
            'user_agent': user_agent,
            'username': current_user.username,
            'company_name': current_user.company.name if current_user.company else 'unknown',
            'timestamp_utc': datetime.utcnow().isoformat(),
            'action_summary': _get_action_summary(table_name, action, old_values, new_values)
        }
        
        # Add any additional context provided
        if additional_context:
            context.update(additional_context)
        
        audit_log = AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_values=serialize_json(old_values) if old_values else None,
            new_values=serialize_json(new_values) if new_values else None,
            user_id=current_user.id,
            company_id=current_user.company_id,
            ip_address=request.remote_addr if hasattr(request, 'remote_addr') else 'unknown',
            additional_info=serialize_json(context)
        )
        db.session.add(audit_log)
    except Exception as e:
        # Log audit failures gracefully
        print(f"Audit logging failed: {str(e)}")

def _get_action_summary(table_name, action, old_values=None, new_values=None):
    """Generate human-readable summary of the action"""
    if table_name == 'inventory_item':
        if action == 'CREATE':
            name = new_values.get('name', 'Unknown') if new_values else 'Unknown'
            return f"Artículo '{name}' creado"
        elif action == 'UPDATE':
            changes = []
            if old_values and new_values:
                if old_values.get('quantity') != new_values.get('quantity'):
                    changes.append(f"cantidad: {old_values.get('quantity')} → {new_values.get('quantity')}")
                if old_values.get('name') != new_values.get('name'):
                    changes.append(f"nombre actualizado")
            return f"Artículo modificado" + (f": {', '.join(changes)}" if changes else "")
        elif action == 'DELETE':
            return f"Artículo eliminado"
    
    return f"{table_name} {action.lower()}"


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


# Simple cache implementation for performance optimization
_stats_cache = {}

def get_cached_dashboard_stats(company_id, user_id, modules_active):
    """Get cached dashboard stats or compute new ones"""
    cache_key = f"dashboard_stats_{company_id}_{user_id}_{hash(str(modules_active))}"
    current_time = time.time()
    
    # Check if we have cached data and it's still valid (5 minutes)
    if cache_key in _stats_cache:
        cached_data, cache_time = _stats_cache[cache_key]
        if current_time - cache_time < 300:  # 5 minutes cache
            return cached_data
    
    # Cache miss or expired, return None to indicate need to recompute
    return None

def set_cached_dashboard_stats(company_id, user_id, modules_active, stats):
    """Cache dashboard stats"""
    cache_key = f"dashboard_stats_{company_id}_{user_id}_{hash(str(modules_active))}"
    _stats_cache[cache_key] = (stats, time.time())
    
    # Simple cache cleanup - remove old entries (older than 1 hour)
    current_time = time.time()
    keys_to_remove = []
    for key, (_, cache_time) in _stats_cache.items():
        if current_time - cache_time > 3600:  # 1 hour
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del _stats_cache[key]