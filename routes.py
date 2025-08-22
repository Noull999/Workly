from flask import render_template, redirect, url_for, flash, request, jsonify, g
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from models import User, InventoryItem, Category, Company, Warehouse, AuditLog
from forms import LoginForm, RegisterForm, InventoryItemForm, CategoryForm, WarehouseForm, CompanyForm, UserManagementForm, ProfileForm, CompanySettingsForm
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

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('inventory'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('inventory'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'¡Bienvenido de nuevo, {user.username}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('inventory'))
        flash('Usuario o contraseña inválidos', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('inventory'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        # Setup new company and default warehouse
        try:
            company, warehouse = setup_new_company(form.company_name.data)
            
            # Create user for the new company
            user = User(
                username=form.username.data, 
                email=form.email.data,
                company_id=company.id
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            
            flash(f'¡Registro exitoso! Empresa "{company.name}" creada. Por favor inicia sesión.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error al crear la cuenta. Por favor inténtalo de nuevo.', 'danger')
    
    return render_template('register.html', form=form)

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

@app.route('/inventory')
@login_required
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
        
        flash(f'¡Empresa "{company.name}" creada exitosamente! Admin: {admin_user.username}, contraseña: empresa123. Usa el botón "Editar" para personalizar logo y colores.', 'success')
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
