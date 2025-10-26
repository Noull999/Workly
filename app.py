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

# Configuración de cookies de sesión para OAuth
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Lax permite redirecciones GET de OAuth
app.config['SESSION_COOKIE_SECURE'] = True  # Requiere HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutos

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

def from_json(value):
    """Parse JSON string to Python object."""
    import json
    try:
        return json.loads(value) if value else {}
    except (json.JSONDecodeError, TypeError):
        return {}

app.jinja_env.filters['nl2br'] = nl2br
app.jinja_env.filters['from_json'] = from_json

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
        if company:
            from models import InventoryItem, Sale, SaleItem, Appointment, Board, Task, NotionPage, NotionChecklistItem
            from datetime import datetime, date
            from utils import company_query
            
            # Estadísticas de Inventario
            total_items = company_query(InventoryItem).count()
            low_stock_items = company_query(InventoryItem).filter(InventoryItem.quantity <= 5).count()
            low_stock_products = company_query(InventoryItem).filter(InventoryItem.quantity <= 5).limit(5).all()
            
            # Datos para gráfico de stock bajo (top 5)
            low_stock_chart_labels = [item.name[:20] for item in low_stock_products]
            low_stock_chart_data = [item.quantity for item in low_stock_products]
            
            # Estadísticas de POS
            today = date.today()
            today_sales = company_query(Sale).filter(Sale.created_at >= datetime.combine(today, datetime.min.time())).count()
            total_sales = company_query(Sale).count()
            
            # Datos para gráfico de ventas (últimos 7 días)
            from datetime import timedelta
            sales_by_day = []
            labels_days = []
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                day_sales = company_query(Sale).filter(
                    Sale.created_at >= datetime.combine(day, datetime.min.time()),
                    Sale.created_at < datetime.combine(day + timedelta(days=1), datetime.min.time())
                ).count()
                sales_by_day.append(day_sales)
                labels_days.append(day.strftime('%d/%m'))
            
            # Estadísticas de Citas
            upcoming_appointments = company_query(Appointment).filter(Appointment.appointment_date >= datetime.now()).count()
            
            # Estadísticas de Scrum
            total_boards = company_query(Board).filter_by(is_active=True).count()
            pending_tasks = company_query(Task).filter(Task.status.in_(['to_do', 'in_progress'])).count()
            my_tasks = company_query(Task).filter_by(assignee_id=current_user.id).filter(Task.status != 'done').limit(5).all()
            
            # Datos para gráfico de tareas por estado
            tasks_todo = company_query(Task).filter_by(status='to_do').count()
            tasks_in_progress = company_query(Task).filter_by(status='in_progress').count()
            tasks_done = company_query(Task).filter_by(status='done').count()
            task_status_labels = ['Por Hacer', 'En Progreso', 'Completadas']
            task_status_data = [tasks_todo, tasks_in_progress, tasks_done]
            
            # Estadísticas de Notion
            total_pages = company_query(NotionPage).count()
            recent_pages = company_query(NotionPage).order_by(NotionPage.updated_at.desc()).limit(5).all()
            active_checklists = company_query(NotionChecklistItem).filter_by(is_completed=False).count()
            
            stats = {
                'inventory': {
                    'total_items': total_items, 
                    'low_stock_items': low_stock_items, 
                    'low_stock_products': low_stock_products,
                    'low_stock_chart_labels': low_stock_chart_labels,
                    'low_stock_chart_data': low_stock_chart_data
                },
                'pos': {'today_sales': today_sales, 'total_sales': total_sales, 'sales_by_day': sales_by_day, 'labels_days': labels_days},
                'appointments': {'upcoming_appointments': upcoming_appointments},
                'scrum': {
                    'total_boards': total_boards, 
                    'pending_tasks': pending_tasks, 
                    'my_tasks': my_tasks,
                    'task_status_labels': task_status_labels,
                    'task_status_data': task_status_data
                },
                'notion': {'total_pages': total_pages, 'recent_pages': recent_pages, 'active_checklists': active_checklists},
                'portfolio': {'page_views': 0, 'contact_requests': 0}  # Estos podrían calcularse si hay modelos para ello
            }
        else:
            stats = {
                'inventory': {'total_items': 0, 'low_stock_items': 0, 'low_stock_products': []},
                'pos': {'today_sales': 0, 'total_sales': 0},
                'appointments': {'upcoming_appointments': 0},
                'scrum': {'total_boards': 0, 'pending_tasks': 0, 'my_tasks': []},
                'notion': {'total_pages': 0, 'recent_pages': [], 'active_checklists': 0},
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

# ===== CLIPS API ENDPOINTS =====
from flask import request, jsonify

@app.route('/api/clips/<int:user_id>', methods=['GET'])
def get_user_clips(user_id):
    """Listar todos los clips de un usuario"""
    from models import User, Clip
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    clips = Clip.query.filter_by(user_id=user_id).order_by(Clip.order_position, Clip.created_at).all()
    
    return jsonify({
        'user_id': user_id,
        'user_email': user.email,
        'total_clips': len(clips),
        'clips': [{
            'id': clip.id,
            'video_url': clip.video_url,
            'title': clip.title,
            'description': clip.description,
            'thumbnail_url': clip.thumbnail_url,
            'order_position': clip.order_position,
            'created_at': clip.created_at.isoformat()
        } for clip in clips]
    }), 200

@app.route('/api/clips/<int:user_id>', methods=['POST'])
@csrf.exempt  # Exentar de CSRF para API
def add_user_clip(user_id):
    """Agregar un clip a un usuario (máximo 3 clips)"""
    from models import User, Clip
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    # Validar que no tenga más de 3 clips
    current_clips_count = Clip.query.filter_by(user_id=user_id).count()
    if current_clips_count >= 3:
        return jsonify({'error': 'El usuario ya tiene el máximo de 3 clips'}), 400
    
    # Obtener datos del request
    data = request.get_json()
    if not data or 'video_url' not in data:
        return jsonify({'error': 'Se requiere video_url'}), 400
    
    # Crear nuevo clip
    clip = Clip(
        user_id=user_id,
        video_url=data['video_url'],
        title=data.get('title'),
        description=data.get('description'),
        thumbnail_url=data.get('thumbnail_url'),
        order_position=data.get('order_position', current_clips_count)
    )
    
    db.session.add(clip)
    db.session.commit()
    
    return jsonify({
        'message': 'Clip agregado exitosamente',
        'clip': {
            'id': clip.id,
            'video_url': clip.video_url,
            'title': clip.title,
            'description': clip.description,
            'thumbnail_url': clip.thumbnail_url,
            'order_position': clip.order_position
        }
    }), 201

@app.route('/api/clips/delete/<int:clip_id>', methods=['DELETE'])
@csrf.exempt  # Exentar de CSRF para API
def delete_clip(clip_id):
    """Eliminar un clip"""
    from models import Clip
    
    clip = Clip.query.get(clip_id)
    if not clip:
        return jsonify({'error': 'Clip no encontrado'}), 404
    
    db.session.delete(clip)
    db.session.commit()
    
    return jsonify({'message': 'Clip eliminado exitosamente'}), 200

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
    from blueprints.reports import reports
    from blueprints.mercadopago import mercadopago_bp
    from blueprints.kick import kick_bp
    
    app.register_blueprint(auth)
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(inventory, url_prefix='/inventory')
    app.register_blueprint(pos, url_prefix='/pos')
    app.register_blueprint(appointments, url_prefix='/appointments')
    app.register_blueprint(scrum, url_prefix='/scrum')
    app.register_blueprint(notion, url_prefix='/notion')
    app.register_blueprint(public)
    app.register_blueprint(reports, url_prefix='/reports')
    app.register_blueprint(mercadopago_bp)
    app.register_blueprint(kick_bp)

# Call blueprint registration
register_all_blueprints()

# Ruta especial para URL personalizada de Yanglee
@app.route('/portfolio/yanglee')
def portfolio_yanglee_redirect():
    return redirect(url_for('public.yanglee_page'))
