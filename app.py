import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
from flask_migrate import Migrate

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise RuntimeError("SESSION_SECRET environment variable must be set for security")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)  # Protección CSRF global
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # type: ignore
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Custom Jinja2 filters
def nl2br(value):
    """Convert newlines to HTML line breaks."""
    from markupsafe import Markup
    import re
    return Markup(re.sub(r'\n', '<br>', str(value)))

app.jinja_env.filters['nl2br'] = nl2br

with app.app_context():
    # Import models to ensure tables are created
    import models
    db.create_all()

# Main routes that don't belong to specific modules
from flask import render_template, redirect, url_for, g
from flask_login import current_user, login_required

@app.route('/')
def index():
    if current_user.is_authenticated:
        # Super admin va directo a panel de administración
        if current_user.is_admin_global():
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Panel principal dinámico según módulos activos de la empresa"""
    company = current_user.company
    
    # Determinar módulos activos para el usuario actual
    if current_user.is_admin_global():
        modules_active = {
            'inventory': current_user.admin_pref_inventory,
            'pos': current_user.admin_pref_pos,
            'appointments': current_user.admin_pref_appointments,
            'portfolio': current_user.admin_pref_portfolio,
            'scrum': current_user.admin_pref_scrum,
            'notion': current_user.admin_pref_notion
        }
    else:
        modules_active = {
            'inventory': company.module_inventory,
            'pos': company.module_pos,
            'appointments': company.module_appointments,
            'portfolio': company.module_portfolio,
            'scrum': company.module_scrum,
            'notion': company.module_notion
        }
    
    # Intentar obtener estadísticas del caché
    from utils import get_cached_dashboard_stats
    stats = get_cached_dashboard_stats(current_user.company_id, current_user.id, modules_active)
    
    # Si no hay estadísticas en caché, calcular
    if not stats:
        from models import InventoryItem, Sale, Appointment
        from utils import company_query, set_cached_dashboard_stats
        from datetime import datetime, timedelta
        
        stats = {}
        
        # Estadísticas de inventario
        if modules_active.get('inventory'):
            items_query = company_query(InventoryItem)
            stats['total_items'] = items_query.count()
            stats['low_stock_items'] = items_query.filter(InventoryItem.quantity <= InventoryItem.minimum_stock).count()
        
        # Estadísticas de ventas (POS)
        if modules_active.get('pos'):
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            sales_today_query = company_query(Sale).filter(Sale.created_at >= today)
            sales_week_query = company_query(Sale).filter(Sale.created_at >= week_ago)
            stats['sales_today'] = sales_today_query.count()
            stats['sales_week'] = sales_week_query.count()
        
        # Estadísticas de citas
        if modules_active.get('appointments'):
            today = datetime.now()
            upcoming_appointments = company_query(Appointment).filter(
                Appointment.appointment_date >= today,
                Appointment.status == 'pendiente'
            ).count()
            stats['upcoming_appointments'] = upcoming_appointments
        
        # Guardar en caché por 15 minutos
        set_cached_dashboard_stats(current_user.company_id, current_user.id, modules_active, stats, 900)
    
    return render_template('dashboard.html', modules=modules_active, stats=stats, company=company)

@app.before_request
def load_user_company():
    """Load user company for all requests to enable multi-tenant queries"""
    if current_user.is_authenticated:
        g.company_id = current_user.company_id

# Register blueprints
from blueprints import register_blueprints
register_blueprints(app)
