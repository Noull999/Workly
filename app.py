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
    # Use Flask-Migrate instead of create_all in production
    # db.create_all()  # Commented to favor migrations

# Main routes that don't belong to specific modules
from flask import render_template, redirect, url_for, g, flash
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
        set_cached_dashboard_stats(current_user.company_id, current_user.id, modules_active, stats)
    
    return render_template('dashboard.html', modules=modules_active, stats=stats, company=company)

@app.before_request
def load_user_company():
    """Load user company for all requests to enable multi-tenant queries"""
    if current_user.is_authenticated:
        g.company_id = current_user.company_id

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Perfil de usuario - cambiar datos personales y contraseña"""
    from forms import ProfileForm
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        # Verificar contraseña actual
        if not current_user.check_password(form.current_password.data):
            flash('La contraseña actual es incorrecta.', 'danger')
            return render_template('profile.html', form=form)
        
        # Verificar si el email ya existe (excluyendo el usuario actual)
        from models import User
        existing_user = User.query.filter(User.email == form.email.data, User.id != current_user.id).first()
        if existing_user:
            flash('El correo electrónico ya está registrado por otro usuario.', 'danger')
            return render_template('profile.html', form=form)
        
        # Verificar si el username ya existe (excluyendo el usuario actual)
        existing_user = User.query.filter(User.username == form.username.data, User.id != current_user.id).first()
        if existing_user:
            flash('El nombre de usuario ya está registrado.', 'danger')
            return render_template('profile.html', form=form)
        
        # Actualizar datos
        current_user.username = form.username.data
        current_user.email = form.email.data
        
        # Cambiar contraseña si se proporcionó una nueva
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        
        db.session.commit()
        flash('¡Perfil actualizado exitosamente!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', form=form)

@app.route('/company-settings', methods=['GET', 'POST'])
@login_required
def company_settings():
    """Configuración de empresa - solo para admins"""
    from blueprints.decorators import admin_required
    
    # Verificar permisos manualmente
    if not current_user.is_admin_global() and not current_user.is_admin_empresa():
        flash('Acceso denegado. Se requieren permisos de administrador.', 'danger')
        return redirect(url_for('index'))
    
    from forms import CompanySettingsForm
    company = current_user.company
    form = CompanySettingsForm(obj=company)
    
    if form.validate_on_submit():
        # Solo admin_global puede cambiar el nombre de empresa
        if current_user.is_admin_global() or current_user.is_admin_empresa():
            company.name = form.name.data
            company.logo_url = form.logo_url.data if form.logo_url.data else None
            company.primary_color = form.primary_color.data
            company.secondary_color = form.secondary_color.data
            
            db.session.commit()
            flash('¡Configuración de empresa actualizada exitosamente!', 'success')
            return redirect(url_for('company_settings'))
        else:
            flash('No tienes permisos para modificar la configuración de la empresa.', 'danger')
    
    return render_template('company_settings.html', form=form, company=company)

# Register blueprints
from blueprints import register_blueprints
register_blueprints(app)
