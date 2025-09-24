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
    try:
        # Datos básicos del usuario
        company = current_user.company if current_user.company else None
        
        # Módulos activos simplificados (todos activados por ahora para testing)
        modules_active = {
            'inventory': True,
            'pos': True,
            'appointments': True,
            'portfolio': True,
            'scrum': True,
            'notion': True
        }
        
        # Obtener estadísticas reales de la base de datos
        stats = {
            'inventory': {'total_items': 0, 'low_stock_items': 0, 'low_stock_products': []},
            'pos': {'today_sales': 0, 'total_sales': 0},
            'appointments': {'upcoming_appointments': 0},
            'scrum': {'total_boards': 0, 'pending_tasks': 0, 'my_tasks': []},
            'notion': {'total_pages': 0, 'recent_pages': []},
            'portfolio': {'page_views': 0, 'contact_requests': 0}
        }
        
        # URLs públicas para los módulos
        public_urls = {
            'portfolio': f'/empresa/{company.code if company else "demo"}',
            'booking': f'/empresa/{company.code if company else "demo"}/reservar'
        }
        
        return render_template('dashboard.html', modules=modules_active, stats=stats, company=company, public_urls=public_urls)
    
    except Exception as e:
        # En caso de error, mostrar mensaje de error sin redirección para evitar bucles
        flash(f'Error en dashboard: {str(e)}', 'danger')
        return f"<h1>Error en Dashboard</h1><p>Error: {str(e)}</p><a href='/login'>Ir al Login</a>", 500

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

# Register blueprints - moved to avoid circular imports
def register_all_blueprints():
    """Register all blueprints after app initialization"""
    from blueprints.auth import auth
    from blueprints.admin import admin  
    from blueprints.inventory import inventory
    from blueprints.pos import pos
    from blueprints.appointments import appointments
    from blueprints.scrum import scrum
    from blueprints.notion import notion
    from blueprints.public import public
    
    app.register_blueprint(auth)
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(inventory, url_prefix='/inventory')
    app.register_blueprint(pos, url_prefix='/pos')
    app.register_blueprint(appointments, url_prefix='/appointments')
    app.register_blueprint(scrum, url_prefix='/scrum')
    app.register_blueprint(notion, url_prefix='/notion')
    app.register_blueprint(public, url_prefix='/public')

# Call blueprint registration
register_all_blueprints()
