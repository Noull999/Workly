from flask import render_template, redirect, url_for, flash, request, jsonify, g
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from datetime import datetime
from app import app, db
from models import User, InventoryItem, Category, Company, Warehouse, AuditLog, Service, Appointment, Sale, SaleItem, Board, Sprint, Task, Column, TaskComment
from forms import LoginForm, RegisterForm, InventoryItemForm, CategoryForm, WarehouseForm, CompanyForm, UserManagementForm, ProfileForm, CompanySettingsForm, EditAdminCredentialsForm, ModuleSettingsForm, ServiceForm, AppointmentForm, PublicAppointmentForm, PortfolioForm, SaleForm
from utils import company_query, log_audit, setup_new_company, validate_company_access
from sqlalchemy import or_, func
from functools import wraps

# Decoradores para control de acceso por roles
def admin_global_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin_global():
            flash('Acceso denegado. Se requieren permisos de administrador global.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (not current_user.is_admin_global() and not current_user.is_admin_empresa()):
            flash('Acceso denegado. Se requieren permisos de administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def module_required(module_name):
    """Decorator to check if a module is active for the current company"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            
            # Super admin tiene acceso a todos los módulos
            if current_user.is_admin_global():
                return f(*args, **kwargs)
            
            company = current_user.company
            module_active = getattr(company, f'module_{module_name}', False)
            
            if not module_active:
                return render_template('errors/module_disabled.html', module_name=module_name), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    if current_user.is_authenticated:
        # Super admin va directo a panel de administración
        if current_user.is_admin_global():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'¡Bienvenido de nuevo, {user.username}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        flash('Usuario o contraseña inválidos', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/register')
def register():
    """Página informativa sobre cómo obtener acceso al sistema"""
    return render_template('access_info.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('index'))

@app.before_request
def load_user_company():
    """Load user company for all requests to enable multi-tenant queries"""
    if current_user.is_authenticated:
        g.company_id = current_user.company_id

@app.route('/dashboard')
@login_required
def dashboard():
    """Panel principal dinámico según módulos activos de la empresa"""
    company = current_user.company
    
    # Obtener estadísticas según módulos activos
    stats = {}
    
    # Estadísticas de inventario si está activo
    if (current_user.is_admin_global() and current_user.admin_pref_inventory) or (not current_user.is_admin_global() and company.module_inventory):
        total_items = company_query(InventoryItem).count()
        low_stock_items = company_query(InventoryItem).filter(InventoryItem.quantity <= InventoryItem.minimum_stock).count()
        # Obtener productos con stock bajo (máximo 5)
        low_stock_products = company_query(InventoryItem).filter(
            InventoryItem.quantity <= InventoryItem.minimum_stock
        ).limit(5).all()
        
        stats['inventory'] = {
            'total_items': total_items,
            'low_stock_items': low_stock_items,
            'low_stock_products': low_stock_products
        }
    
    # Estadísticas de POS si está activo
    if (current_user.is_admin_global() and current_user.admin_pref_pos) or (not current_user.is_admin_global() and company.module_pos):
        total_sales = company_query(Sale).count()
        today_sales = company_query(Sale).filter(func.date(Sale.created_at) == func.current_date()).count()
        # Calcular total de ventas de hoy
        from sqlalchemy import func as sql_func
        today_revenue = db.session.query(sql_func.sum(Sale.total_amount)).filter(
            Sale.company_id == current_user.company_id,
            func.date(Sale.created_at) == func.current_date()
        ).scalar() or 0
        
        stats['pos'] = {
            'total_sales': total_sales,
            'today_sales': today_sales,
            'today_revenue': float(today_revenue)
        }
    
    # Estadísticas de citas si está activo
    if (current_user.is_admin_global() and current_user.admin_pref_appointments) or (not current_user.is_admin_global() and company.module_appointments):
        pending_appointments = company_query(Appointment).filter_by(status='pendiente').count()
        confirmed_appointments = company_query(Appointment).filter_by(status='confirmada').count()
        today_appointments = company_query(Appointment).filter(func.date(Appointment.appointment_date) == func.current_date()).count()
        total_appointments = company_query(Appointment).count()
        stats['appointments'] = {
            'pending': pending_appointments,
            'confirmed': confirmed_appointments,
            'today': today_appointments,
            'total': total_appointments
        }
        
        # Obtener próximas citas (5 más próximas)
        upcoming_appointments = company_query(Appointment).filter(
            Appointment.appointment_date >= datetime.now(),
            Appointment.status.in_(['pendiente', 'confirmada'])
        ).order_by(Appointment.appointment_date.asc()).limit(5).all()
        stats['appointments']['upcoming'] = upcoming_appointments
    
    # Estadísticas de Scrum Lite si está activo
    if (current_user.is_admin_global() and current_user.admin_pref_scrum) or (not current_user.is_admin_global() and company.module_scrum):
        total_boards = company_query(Board).filter_by(is_active=True).count()
        # Tareas asignadas al usuario actual
        my_tasks = company_query(Task).filter_by(assignee_id=current_user.id).filter(
            Task.status != 'done'
        ).limit(5).all()
        # Tareas pendientes en general
        pending_tasks = company_query(Task).filter(Task.status != 'done').count()
        
        stats['scrum'] = {
            'total_boards': total_boards,
            'my_tasks': my_tasks,
            'pending_tasks': pending_tasks
        }
    
    # URLs de páginas públicas si están activas
    public_urls = {}
    if (current_user.is_admin_global() and current_user.admin_pref_portfolio) or (not current_user.is_admin_global() and company.module_portfolio):
        public_urls['portfolio'] = url_for('public_portfolio', company_code=company.code, _external=True)
    if (current_user.is_admin_global() and current_user.admin_pref_appointments) or (not current_user.is_admin_global() and company.module_appointments):
        public_urls['booking'] = url_for('public_booking', company_code=company.code, _external=True)
    
    return render_template('dashboard.html', stats=stats, company=company, public_urls=public_urls)

@app.route('/inventory')
@login_required
@module_required('inventory')
def inventory():
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    warehouse_filter = request.args.get('warehouse', '')
    sort_by = request.args.get('sort', 'name')
    
    # Use company-scoped query
    query = company_query(InventoryItem)
    
    # Apply search filter (include barcode)
    if search:
        query = query.filter(or_(
            InventoryItem.name.contains(search),
            InventoryItem.description.contains(search),
            InventoryItem.sku.contains(search),
            InventoryItem.barcode.contains(search)
        ))
    
    # Apply category filter
    if category_filter and category_filter != 'all':
        if category_filter == 'none':
            query = query.filter(InventoryItem.category_id.is_(None))
        else:
            query = query.filter(InventoryItem.category_id == int(category_filter))
    
    # Apply warehouse filter
    if warehouse_filter and warehouse_filter != 'all':
        query = query.filter(InventoryItem.warehouse_id == int(warehouse_filter))
    
    # Apply sorting
    if sort_by == 'name':
        query = query.order_by(InventoryItem.name)
    elif sort_by == 'quantity':
        query = query.order_by(InventoryItem.quantity.desc())
    elif sort_by == 'created_at':
        query = query.order_by(InventoryItem.created_at.desc())
    elif sort_by == 'warehouse':
        query = query.join(Warehouse).order_by(Warehouse.name)
    
    items = query.all()
    categories = company_query(Category).all()
    warehouses = company_query(Warehouse).filter_by(is_active=True).all()
    
    # Calculate statistics
    total_items = len(items)
    low_stock_items = [item for item in items if item.is_low_stock]
    
    return render_template('inventory.html', 
                         items=items, 
                         categories=categories,
                         warehouses=warehouses,
                         search=search,
                         category_filter=category_filter,
                         warehouse_filter=warehouse_filter,
                         sort_by=sort_by,
                         total_items=total_items,
                         low_stock_count=len(low_stock_items))

@app.route('/add_item', methods=['GET', 'POST'])
@login_required
@module_required('inventory')
def add_item():
    form = InventoryItemForm()
    if form.validate_on_submit():
        # Check for duplicate SKU if provided (within company)
        if form.sku.data:
            existing_item = company_query(InventoryItem).filter_by(sku=form.sku.data).first()
            if existing_item:
                flash('El SKU ya existe en tu empresa', 'danger')
                return render_template('add_item.html', form=form)
        
        # Check for duplicate barcode if provided (within company)
        if form.barcode.data:
            existing_item = company_query(InventoryItem).filter_by(barcode=form.barcode.data).first()
            if existing_item:
                flash('El código de barras ya existe en tu empresa', 'danger')
                return render_template('add_item.html', form=form)
        
        # Verify warehouse belongs to the company
        warehouse = company_query(Warehouse).filter_by(id=form.warehouse_id.data).first()
        if not warehouse:
            flash('Almacén no válido', 'danger')
            return render_template('add_item.html', form=form)
        
        item = InventoryItem(
            name=form.name.data,
            description=form.description.data,
            quantity=form.quantity.data,
            minimum_stock=form.minimum_stock.data,
            sku=form.sku.data if form.sku.data else None,
            barcode=form.barcode.data if form.barcode.data else None,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            warehouse_id=form.warehouse_id.data,
            user_id=current_user.id,
            company_id=current_user.company_id
        )
        db.session.add(item)
        db.session.commit()
        
        # Log the audit
        log_audit('inventory_item', item.id, 'CREATE', None, {
            'name': item.name, 'quantity': item.quantity, 'warehouse_id': item.warehouse_id
        })
        
        flash('¡Artículo agregado exitosamente!', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('add_item.html', form=form)

@app.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
@module_required('inventory')
def edit_item(item_id):
    item = company_query(InventoryItem).filter_by(id=item_id).first_or_404()
    
    # Store original values for audit
    original_values = {
        'name': item.name,
        'quantity': item.quantity,
        'warehouse_id': item.warehouse_id,
        'barcode': item.barcode,
        'sku': item.sku
    }
    
    form = InventoryItemForm(obj=item)
    
    if form.validate_on_submit():
        # Check for duplicate SKU if changed (within company)
        if form.sku.data and form.sku.data != item.sku:
            existing_item = company_query(InventoryItem).filter_by(sku=form.sku.data).first()
            if existing_item:
                flash('El SKU ya existe en tu empresa', 'danger')
                return render_template('edit_item.html', form=form, item=item)
        
        # Check for duplicate barcode if changed (within company)
        if form.barcode.data and form.barcode.data != item.barcode:
            existing_item = company_query(InventoryItem).filter_by(barcode=form.barcode.data).first()
            if existing_item:
                flash('El código de barras ya existe en tu empresa', 'danger')
                return render_template('edit_item.html', form=form, item=item)
        
        # Verify warehouse belongs to the company
        warehouse = company_query(Warehouse).filter_by(id=form.warehouse_id.data).first()
        if not warehouse:
            flash('Almacén no válido', 'danger')
            return render_template('edit_item.html', form=form, item=item)
        
        # Update item
        item.name = form.name.data
        item.description = form.description.data
        item.quantity = form.quantity.data
        item.minimum_stock = form.minimum_stock.data
        item.sku = form.sku.data if form.sku.data else None
        item.barcode = form.barcode.data if form.barcode.data else None
        item.category_id = form.category_id.data if form.category_id.data != 0 else None
        item.warehouse_id = form.warehouse_id.data
        
        db.session.commit()
        
        # Log the audit
        new_values = {
            'name': item.name,
            'quantity': item.quantity,
            'warehouse_id': item.warehouse_id,
            'barcode': item.barcode,
            'sku': item.sku
        }
        log_audit('inventory_item', item.id, 'UPDATE', original_values, new_values)
        
        flash('¡Artículo actualizado exitosamente!', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('edit_item.html', form=form, item=item)

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
@module_required('inventory')
def delete_item(item_id):
    item = company_query(InventoryItem).filter_by(id=item_id).first_or_404()
    
    # Store values for audit before deletion
    item_data = {
        'name': item.name,
        'quantity': item.quantity,
        'warehouse_id': item.warehouse_id
    }
    
    db.session.delete(item)
    db.session.commit()
    
    # Log the audit
    log_audit('inventory_item', item_id, 'DELETE', item_data, None)
    
    flash('¡Artículo eliminado exitosamente!', 'success')
    return redirect(url_for('inventory'))

@app.route('/reports')
@login_required
@module_required('inventory')
def reports():
    # Calculate comprehensive statistics using multi-tenant queries
    items = company_query(InventoryItem).all()
    
    total_items = len(items)
    low_stock_items = [item for item in items if item.is_low_stock]
    
    # Category breakdown
    category_stats = db.session.query(
        Category.name,
        func.count(InventoryItem.id).label('item_count'),
        func.sum(InventoryItem.quantity).label('total_quantity')
    ).join(InventoryItem, Category.id == InventoryItem.category_id)\
     .filter(InventoryItem.company_id == current_user.company_id)\
     .group_by(Category.name).all()
    
    # Warehouse breakdown
    warehouse_stats = db.session.query(
        Warehouse.name,
        func.count(InventoryItem.id).label('item_count'),
        func.sum(InventoryItem.quantity).label('total_quantity')
    ).join(InventoryItem, Warehouse.id == InventoryItem.warehouse_id)\
     .filter(InventoryItem.company_id == current_user.company_id)\
     .group_by(Warehouse.name).all()
    
    # Items without category
    uncategorized_count = company_query(InventoryItem).filter_by(category_id=None).count()
    
    uncategorized_quantity = db.session.query(
        func.sum(InventoryItem.quantity)
    ).filter(InventoryItem.company_id == current_user.company_id,
             InventoryItem.category_id.is_(None)).scalar() or 0
    
    return render_template('reports.html',
                         total_items=total_items,
                         items=items,
                         low_stock_items=low_stock_items,
                         category_stats=category_stats,
                         warehouse_stats=warehouse_stats,
                         uncategorized_count=uncategorized_count,
                         uncategorized_quantity=uncategorized_quantity)

@app.route('/categories', methods=['GET', 'POST'])
@login_required
@module_required('inventory')
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        existing_category = company_query(Category).filter_by(name=form.name.data).first()
        if existing_category:
            flash('La categoría ya existe en tu empresa', 'danger')
        else:
            category = Category(
                name=form.name.data, 
                description=form.description.data,
                company_id=current_user.company_id
            )
            db.session.add(category)
            db.session.commit()
            
            # Log the audit
            log_audit('category', category.id, 'CREATE', None, {
                'name': category.name, 'description': category.description
            })
            
            flash('¡Categoría creada exitosamente!', 'success')
            return redirect(url_for('categories'))
    
    categories = company_query(Category).all()
    return render_template('categories.html', form=form, categories=categories)

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    category = company_query(Category).filter_by(id=category_id).first_or_404()
    
    # Check if category has items within the company
    item_count = company_query(InventoryItem).filter_by(category_id=category_id).count()
    if item_count > 0:
        flash(f'No se puede eliminar la categoría. Contiene {item_count} artículos.', 'danger')
    else:
        # Store values for audit before deletion
        category_data = {'name': category.name, 'description': category.description}
        
        db.session.delete(category)
        db.session.commit()
        
        # Log the audit
        log_audit('category', category_id, 'DELETE', category_data, None)
        
        flash('¡Categoría eliminada exitosamente!', 'success')
    return redirect(url_for('categories'))

# New route for warehouse management
@app.route('/warehouses', methods=['GET', 'POST'])
@login_required
@module_required('inventory')
def warehouses():
    form = WarehouseForm()
    if form.validate_on_submit():
        existing_warehouse = company_query(Warehouse).filter_by(code=form.code.data).first()
        if existing_warehouse:
            flash('El código de almacén ya existe en tu empresa', 'danger')
        else:
            warehouse = Warehouse(
                name=form.name.data,
                code=form.code.data,
                address=form.address.data,
                company_id=current_user.company_id
            )
            db.session.add(warehouse)
            db.session.commit()
            
            # Log the audit
            log_audit('warehouse', warehouse.id, 'CREATE', None, {
                'name': warehouse.name, 'code': warehouse.code
            })
            
            flash('¡Almacén creado exitosamente!', 'success')
            return redirect(url_for('warehouses'))
    
    warehouses = company_query(Warehouse).filter_by(is_active=True).all()
    return render_template('warehouses.html', form=form, warehouses=warehouses)

@app.route('/delete_warehouse/<int:warehouse_id>', methods=['POST'])
@login_required
def delete_warehouse(warehouse_id):
    warehouse = company_query(Warehouse).filter_by(id=warehouse_id).first_or_404()
    
    # Check if warehouse has items
    item_count = company_query(InventoryItem).filter_by(warehouse_id=warehouse_id).count()
    if item_count > 0:
        flash(f'No se puede eliminar el almacén. Contiene {item_count} artículos.', 'danger')
    else:
        # Store values for audit before deletion
        warehouse_data = {'name': warehouse.name, 'code': warehouse.code}
        
        # Soft delete - mark as inactive
        warehouse.is_active = False
        db.session.commit()
        
        # Log the audit
        log_audit('warehouse', warehouse_id, 'DEACTIVATE', warehouse_data, {'is_active': False})
        
        flash('¡Almacén desactivado exitosamente!', 'success')
    return redirect(url_for('warehouses'))

# ===== RUTAS DE ADMINISTRACIÓN GLOBAL =====

@app.route('/admin')
@login_required
@admin_global_required
def admin_panel():
    """Panel de administración global - solo para admin_global"""
    companies = Company.query.filter_by(is_active=True).all()
    users = User.query.all()
    total_companies = len(companies)
    total_users = len(users)
    
    # Estadísticas por empresa
    company_stats = {}
    for company in companies:
        company_users = [u for u in users if u.company_id == company.id]
        company_stats[company.id] = {
            'users': len(company_users),
            'items': len(company.items) if hasattr(company, 'items') else 0
        }
    
    return render_template('admin/dashboard.html', 
                         companies=companies,
                         total_companies=total_companies,
                         total_users=total_users,
                         company_stats=company_stats)

@app.route('/admin/dashboard')
@login_required
@admin_global_required
def admin_dashboard():
    """Dashboard principal para super admin"""
    companies = Company.query.all()
    users = User.query.all()
    total_companies = len(companies)
    total_users = len(users)
    active_companies = len([c for c in companies if c.is_active])
    
    # Estadísticas de uso de módulos
    module_stats = {
        'inventory': sum(1 for c in companies if c.module_inventory and c.is_active),
        'pos': sum(1 for c in companies if c.module_pos and c.is_active),
        'appointments': sum(1 for c in companies if c.module_appointments and c.is_active),
        'portfolio': sum(1 for c in companies if c.module_portfolio and c.is_active),
        'scrum': sum(1 for c in companies if c.module_scrum and c.is_active)
    }
    
    modules_active = sum(module_stats.values())
    
    # Empresas más recientes
    recent_companies = Company.query.order_by(Company.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         companies=companies,
                         recent_companies=recent_companies,
                         total_companies=total_companies,
                         total_users=total_users,
                         active_companies=active_companies,
                         modules_active=modules_active,
                         module_stats=module_stats)

@app.route('/admin/companies', methods=['GET', 'POST'])
@login_required
@admin_global_required
def manage_companies():
    """Gestión de empresas - crear, editar, listar"""
    form = CompanyForm()
    if form.validate_on_submit():
        # Generar código único
        code = Company.generate_code()
        
        company = Company(
            name=form.name.data,
            code=code,
            logo_url=form.logo_url.data if form.logo_url.data else None,
            primary_color=form.primary_color.data,
            secondary_color=form.secondary_color.data
        )
        db.session.add(company)
        db.session.flush()  # Get company ID
        
        # Crear admin automático para la empresa
        admin_user = User(
            username=f"admin_{code.lower()}",
            email=f"admin@{company.name.lower().replace(' ', '')}.com",
            role='admin_empresa',
            company_id=company.id
        )
        admin_user.set_password('empresa123')  # Contraseña por defecto
        db.session.add(admin_user)
        
        # Crear almacén principal automático
        warehouse = Warehouse(
            name='Almacén Principal',
            code='MAIN',
            address='Almacén principal de la empresa',
            company_id=company.id
        )
        db.session.add(warehouse)
        
        db.session.commit()
        
        flash(f'¡Empresa "{company.name}" creada exitosamente! Admin: {admin_user.username}, contraseña: empresa123. Usa los botones "Editar" y "Credenciales" para personalizar.', 'success')
        return redirect(url_for('manage_companies'))
    
    companies = Company.query.filter_by(is_active=True).all()
    return render_template('admin/companies.html', form=form, companies=companies)

@app.route('/admin/edit_company/<int:company_id>', methods=['GET', 'POST'])
@login_required
@admin_global_required
def edit_company(company_id):
    """Editar empresa existente"""
    company = Company.query.get_or_404(company_id)
    form = CompanyForm(obj=company)
    
    if form.validate_on_submit():
        company.name = form.name.data
        company.logo_url = form.logo_url.data if form.logo_url.data else None
        company.primary_color = form.primary_color.data
        company.secondary_color = form.secondary_color.data
        
        db.session.commit()
        flash(f'¡Empresa "{company.name}" actualizada exitosamente!', 'success')
        return redirect(url_for('manage_companies'))
    
    return render_template('admin/edit_company.html', form=form, company=company)

@app.route('/admin/edit_admin_credentials/<int:company_id>', methods=['GET', 'POST'])
@login_required
@admin_global_required
def edit_admin_credentials(company_id):
    """Editar credenciales del administrador de empresa"""
    company = Company.query.get_or_404(company_id)
    
    # Buscar el administrador de la empresa
    admin_user = User.query.filter_by(company_id=company_id, role='admin_empresa').first()
    if not admin_user:
        flash('No se encontró un administrador para esta empresa.', 'danger')
        return redirect(url_for('manage_companies'))
    
    form = EditAdminCredentialsForm()
    
    # Pre-llenar el formulario con los datos actuales
    if request.method == 'GET':
        form.username.data = admin_user.username
        form.email.data = admin_user.email
    
    if form.validate_on_submit():
        # Verificar si el username ya existe (excluyendo el usuario actual)
        existing_user = User.query.filter(User.username == form.username.data, User.id != admin_user.id).first()
        if existing_user:
            flash('El nombre de usuario ya está registrado.', 'danger')
            return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)
        
        # Verificar si el email ya existe (excluyendo el usuario actual)
        existing_user = User.query.filter(User.email == form.email.data, User.id != admin_user.id).first()
        if existing_user:
            flash('El correo electrónico ya está registrado.', 'danger')
            return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)
        
        # Actualizar credenciales
        admin_user.username = form.username.data
        admin_user.email = form.email.data
        admin_user.set_password(form.password.data)
        
        db.session.commit()
        
        flash(f'¡Credenciales del administrador de "{company.name}" actualizadas exitosamente! Nuevas credenciales: {admin_user.username} / {form.password.data}', 'success')
        return redirect(url_for('manage_companies'))
    
    return render_template('admin/edit_admin_credentials.html', form=form, company=company, admin_user=admin_user)

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    """Gestión de usuarios"""
    form = UserManagementForm()
    
    if form.validate_on_submit():
        # Validar permisos
        if not current_user.can_manage_users(form.company_id.data):
            flash('No tienes permisos para crear usuarios en esa empresa.', 'danger')
            return render_template('admin/users.html', form=form, users=[])
        
        # Verificar email único
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('El correo electrónico ya está registrado.', 'danger')
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
                company_id=form.company_id.data
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            
            flash(f'¡Usuario "{user.username}" creado exitosamente!', 'success')
            return redirect(url_for('manage_users'))
    
    # Filtrar usuarios según permisos
    if current_user.is_admin_global():
        users = User.query.all()
    else:
        users = User.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template('admin/users.html', form=form, users=users)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Eliminar usuario"""
    user = User.query.get_or_404(user_id)
    
    # Validar permisos
    if not current_user.can_manage_users(user.company_id):
        flash('No tienes permisos para eliminar este usuario.', 'danger')
        return redirect(url_for('manage_users'))
    
    # No permitir que se elimine a sí mismo
    if user.id == current_user.id:
        flash('No puedes eliminarte a ti mismo.', 'danger')
        return redirect(url_for('manage_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Usuario "{username}" eliminado exitosamente.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/admin/company/<int:company_id>/toggle_status', methods=['POST'])
@login_required
@admin_global_required
def toggle_company_status(company_id):
    """Activar/desactivar empresa"""
    company = Company.query.get_or_404(company_id)
    company.is_active = not company.is_active
    db.session.commit()
    
    status = 'activada' if company.is_active else 'desactivada'
    flash(f'Empresa "{company.name}" {status} exitosamente.', 'success')
    return redirect(url_for('manage_companies'))

# ===== RUTAS DE PERFIL Y CONFIGURACIÓN =====

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Perfil de usuario - cambiar datos personales y contraseña"""
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        # Verificar contraseña actual
        if not current_user.check_password(form.current_password.data):
            flash('La contraseña actual es incorrecta.', 'danger')
            return render_template('profile.html', form=form)
        
        # Verificar si el email ya existe (excluyendo el usuario actual)
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
@admin_required
def company_settings():
    """Configuración de empresa - solo para admins"""
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


# ===== RUTAS PARA MÓDULOS ADICIONALES =====

@app.route('/admin/modules', methods=['GET', 'POST'])
@login_required
@admin_global_required
def manage_modules():
    """Gestionar módulos activos por empresa"""
    companies = Company.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        # Verificar si es actualización de preferencias del super admin
        if request.form.get('admin_preferences') == '1':
            # Actualizar preferencias del super admin
            current_user.admin_pref_inventory = 'admin_pref_inventory' in request.form
            current_user.admin_pref_pos = 'admin_pref_pos' in request.form
            current_user.admin_pref_appointments = 'admin_pref_appointments' in request.form
            current_user.admin_pref_portfolio = 'admin_pref_portfolio' in request.form
            current_user.admin_pref_scrum = 'admin_pref_scrum' in request.form
            
            db.session.commit()
            flash('Tus preferencias de módulos han sido actualizadas', 'success')
            return redirect(url_for('manage_modules'))
        else:
            # Actualizar módulos de empresa
            company_id = request.form.get('company_id')
            company = Company.query.get_or_404(company_id)
            
            # Actualizar módulos
            company.module_inventory = 'module_inventory' in request.form
            company.module_pos = 'module_pos' in request.form
            company.module_appointments = 'module_appointments' in request.form
            company.module_portfolio = 'module_portfolio' in request.form
            company.module_scrum = 'module_scrum' in request.form
            
            db.session.commit()
            flash(f'Módulos actualizados para {company.name}', 'success')
            return redirect(url_for('manage_modules'))
    
    return render_template('admin/modules.html', companies=companies)

@app.route('/portfolio/config', methods=['GET', 'POST'])
@login_required
@admin_required
def portfolio_config():
    """Configurar página de presentación de la empresa"""
    if not current_user.company.module_portfolio:
        flash('El módulo de página de presentación no está activo para tu empresa.', 'warning')
        return redirect(url_for('inventory'))
    
    company = current_user.company
    form = PortfolioForm(obj=company)
    
    if form.validate_on_submit():
        company.portfolio_description = form.portfolio_description.data
        company.portfolio_services = form.portfolio_services.data
        company.contact_phone = form.contact_phone.data
        company.contact_whatsapp = form.contact_whatsapp.data
        company.contact_email = form.contact_email.data
        company.contact_address = form.contact_address.data
        company.social_facebook = form.social_facebook.data
        company.social_instagram = form.social_instagram.data
        company.social_linkedin = form.social_linkedin.data
        
        db.session.commit()
        flash('¡Página de presentación configurada exitosamente!', 'success')
        return redirect(url_for('portfolio_config'))
    
    # URL de la página pública
    portfolio_url = url_for('public_portfolio', company_code=company.code, _external=True)
    
    return render_template('modules/portfolio_config.html', 
                         form=form, company=company, portfolio_url=portfolio_url)

@app.route('/services', methods=['GET', 'POST'])
@login_required
def manage_services():
    """Gestionar servicios para citas"""
    if not current_user.company.module_appointments:
        flash('El módulo de citas no está activo para tu empresa.', 'warning')
        return redirect(url_for('inventory'))
    
    form = ServiceForm()
    if form.validate_on_submit():
        service = Service(
            name=form.name.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            price=form.price.data,
            is_active=form.is_active.data,
            company_id=current_user.company_id
        )
        db.session.add(service)
        db.session.commit()
        flash(f'Servicio "{service.name}" agregado exitosamente!', 'success')
        return redirect(url_for('manage_services'))
    
    services = company_query(Service).all()
    return render_template('modules/services.html', form=form, services=services)

@app.route('/services/<int:service_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    """Editar servicio"""
    service = company_query(Service).filter_by(id=service_id).first_or_404()
    form = ServiceForm(obj=service)
    
    if form.validate_on_submit():
        service.name = form.name.data
        service.description = form.description.data
        service.duration_minutes = form.duration_minutes.data
        service.price = form.price.data
        service.is_active = form.is_active.data
        db.session.commit()
        flash(f'Servicio "{service.name}" actualizado exitosamente!', 'success')
        return redirect(url_for('manage_services'))
    
    return render_template('modules/edit_service.html', form=form, service=service)

@app.route('/appointments', methods=['GET', 'POST'])
@login_required
def manage_appointments():
    """Gestionar citas"""
    if not current_user.company.module_appointments:
        flash('El módulo de citas no está activo para tu empresa.', 'warning')
        return redirect(url_for('inventory'))
    
    form = AppointmentForm()
    if form.validate_on_submit():
        appointment = Appointment(
            client_name=form.client_name.data,
            client_phone=form.client_phone.data,
            client_email=form.client_email.data,
            appointment_date=form.appointment_date.data,
            service_id=form.service_id.data,
            status=form.status.data,
            notes=form.notes.data,
            is_public=False,
            company_id=current_user.company_id,
            user_id=current_user.id
        )
        db.session.add(appointment)
        db.session.commit()
        flash(f'Cita para {appointment.client_name} agendada exitosamente!', 'success')
        return redirect(url_for('manage_appointments'))
    
    appointments = company_query(Appointment).order_by(Appointment.appointment_date.desc()).all()
    
    # URL de la página pública de reservas
    booking_url = url_for('public_booking', company_code=current_user.company.code, _external=True)
    
    return render_template('modules/appointments.html', 
                         form=form, appointments=appointments, booking_url=booking_url)

@app.route('/pos', methods=['GET', 'POST'])
@login_required
def pos_sales():
    """Punto de venta"""
    if not current_user.company.module_pos:
        flash('El módulo POS no está activo para tu empresa.', 'warning')
        return redirect(url_for('inventory'))
    
    form = SaleForm()
    
    # Obtener items de inventario con stock
    items = company_query(InventoryItem).filter(InventoryItem.quantity > 0).all()
    
    return render_template('modules/pos.html', form=form, items=items)

# ===== RUTAS PÚBLICAS (SIN LOGIN) =====

@app.route('/empresa/<company_code>')
def public_portfolio(company_code):
    """Página pública de presentación de empresa"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_portfolio:
        return render_template('errors/module_disabled.html'), 404
    
    # URL de reserva si tiene módulo de citas activo
    booking_url = None
    if company.module_appointments:
        booking_url = url_for('public_booking', company_code=company.code)
    
    return render_template('public/portfolio.html', company=company, booking_url=booking_url, current_year=datetime.now().year)

@app.route('/empresa/<company_code>/reservar', methods=['GET', 'POST'])
def public_booking(company_code):
    """Página pública para reservar citas"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_appointments:
        return render_template('errors/module_disabled.html'), 404
    
    form = PublicAppointmentForm()
    
    # Cargar servicios activos
    services = Service.query.filter_by(company_id=company.id, is_active=True).all()
    form.service_id.choices = [(s.id, f"{s.name} ({s.duration_minutes} min)") for s in services]
    
    if form.validate_on_submit():
        appointment = Appointment(
            client_name=form.client_name.data,
            client_phone=form.client_phone.data,
            client_email=form.client_email.data,
            appointment_date=form.appointment_date.data,
            service_id=form.service_id.data,
            notes=form.notes.data,
            is_public=True,
            company_id=company.id,
            status='pendiente'
        )
        db.session.add(appointment)
        db.session.commit()
        
        flash('¡Reserva realizada exitosamente! Te contactaremos pronto para confirmar.', 'success')
        return redirect(url_for('booking_confirmation', company_code=company.code, appointment_id=appointment.id))
    
    return render_template('public/booking.html', company=company, form=form, services=services)

@app.route('/empresa/<company_code>/reserva/<int:appointment_id>/confirmacion')
def booking_confirmation(company_code, appointment_id):
    """Confirmación de reserva"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    appointment = Appointment.query.filter_by(id=appointment_id, company_id=company.id).first_or_404()
    
    return render_template('public/booking_confirmation.html', 
                         company=company, appointment=appointment)


# ===== SCRUM LITE MODULE =====

@app.route('/scrum')
@login_required
@module_required('scrum')
def scrum_dashboard():
    """Dashboard principal de Scrum Lite"""
    company = current_user.company
    boards = company_query(Board).filter_by(is_active=True).all()
    
    # Estadísticas rápidas
    my_tasks = company_query(Task).filter_by(assignee_id=current_user.id).filter(
        Task.status != 'done'
    ).all()
    
    return render_template('modules/scrum/dashboard.html', boards=boards, my_tasks=my_tasks, company=company)


@app.route('/scrum/board/<int:board_id>')
@login_required
@module_required('scrum')
def scrum_board(board_id):
    """Vista del tablero Kanban"""
    board = company_query(Board).filter_by(id=board_id, is_active=True).first_or_404()
    columns = company_query(Column).filter_by(board_id=board_id).order_by(Column.position).all()
    
    # Organizar tareas por columna
    board_data = []
    for column in columns:
        tasks = company_query(Task).filter_by(column_id=column.id).order_by(Task.position).all()
        board_data.append({
            'column': column,
            'tasks': tasks
        })
    
    return render_template('modules/scrum/board.html', board=board, board_data=board_data, company=current_user.company)


@app.route('/scrum/create-board', methods=['GET', 'POST'])
@login_required
@module_required('scrum')
@admin_required
def create_scrum_board():
    """Crear nuevo tablero"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('El nombre del tablero es obligatorio', 'danger')
            return redirect(url_for('create_scrum_board'))
        
        # Crear tablero
        board = Board(
            name=name,
            description=description,
            company_id=current_user.company_id
        )
        db.session.add(board)
        db.session.flush()  # Get board ID
        
        # Crear columnas por defecto
        default_columns = [
            {'name': 'To Do', 'position': 0, 'color': '#dc3545'},
            {'name': 'In Progress', 'position': 1, 'color': '#ffc107'},
            {'name': 'Done', 'position': 2, 'color': '#28a745'}
        ]
        
        for col_data in default_columns:
            column = Column(
                name=col_data['name'],
                position=col_data['position'],
                color=col_data['color'],
                board_id=board.id,
                company_id=current_user.company_id
            )
            db.session.add(column)
        
        db.session.commit()
        flash(f'Tablero "{name}" creado exitosamente', 'success')
        return redirect(url_for('scrum_board', board_id=board.id))
    
    return render_template('modules/scrum/create_board.html', company=current_user.company)


@app.route('/scrum/task/create/<int:board_id>/<int:column_id>', methods=['POST'])
@login_required
@module_required('scrum')
def create_task(board_id, column_id):
    """Crear nueva tarea"""
    board = company_query(Board).filter_by(id=board_id).first_or_404()
    column = company_query(Column).filter_by(id=column_id, board_id=board_id).first_or_404()
    
    title = request.form.get('title')
    if not title:
        flash('El título de la tarea es obligatorio', 'danger')
        return redirect(url_for('scrum_board', board_id=board_id))
    
    # Calcular posición (última + 1)
    last_position = db.session.query(func.max(Task.position)).filter_by(
        column_id=column_id, company_id=current_user.company_id
    ).scalar() or 0
    
    task = Task(
        title=title,
        description=request.form.get('description', ''),
        board_id=board_id,
        column_id=column_id,
        position=last_position + 1,
        creator_id=current_user.id,
        assignee_id=current_user.id,  # Por defecto, asignar al creador
        company_id=current_user.company_id
    )
    
    db.session.add(task)
    db.session.commit()
    
    flash('Tarea creada exitosamente', 'success')
    return redirect(url_for('scrum_board', board_id=board_id))


@app.route('/scrum/task/move', methods=['POST'])
@login_required
@module_required('scrum')
def move_task():
    """Mover tarea entre columnas (AJAX)"""
    data = request.get_json()
    task_id = data.get('task_id')
    new_column_id = data.get('column_id')
    new_position = data.get('position', 0)
    
    task = company_query(Task).filter_by(id=task_id).first()
    if not task:
        return jsonify({'error': 'Tarea no encontrada'}), 404
    
    # Actualizar tarea
    task.column_id = new_column_id
    task.position = new_position
    
    # Actualizar status basado en la columna
    column = company_query(Column).filter_by(id=new_column_id).first()
    if column:
        if 'done' in column.name.lower() or 'terminado' in column.name.lower():
            task.status = 'done'
            from datetime import datetime
            task.completed_at = datetime.utcnow()
        elif 'progress' in column.name.lower() or 'progreso' in column.name.lower():
            task.status = 'in_progress'
        else:
            task.status = 'to_do'
    
    db.session.commit()
    
    return jsonify({'success': True})
