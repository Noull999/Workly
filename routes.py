from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import app, db
from models import User, InventoryItem, Category
from forms import LoginForm, RegisterForm, InventoryItemForm, CategoryForm
from sqlalchemy import or_, func

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
        # Check if username or email already exists
        existing_user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.email.data)
        ).first()
        
        if existing_user:
            if existing_user.username == form.username.data:
                flash('El nombre de usuario ya existe', 'danger')
            else:
                flash('El correo electrónico ya está registrado', 'danger')
        else:
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('¡Registro exitoso! Por favor inicia sesión.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('index'))

@app.route('/inventory')
@login_required
def inventory():
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    sort_by = request.args.get('sort', 'name')
    
    query = InventoryItem.query.filter_by(user_id=current_user.id)
    
    # Apply search filter
    if search:
        query = query.filter(or_(
            InventoryItem.name.contains(search),
            InventoryItem.description.contains(search),
            InventoryItem.sku.contains(search)
        ))
    
    # Apply category filter
    if category_filter and category_filter != 'all':
        if category_filter == 'none':
            query = query.filter(InventoryItem.category_id.is_(None))
        else:
            query = query.filter(InventoryItem.category_id == int(category_filter))
    
    # Apply sorting
    if sort_by == 'name':
        query = query.order_by(InventoryItem.name)
    elif sort_by == 'quantity':
        query = query.order_by(InventoryItem.quantity.desc())
    elif sort_by == 'created_at':
        query = query.order_by(InventoryItem.created_at.desc())
    
    items = query.all()
    categories = Category.query.all()
    
    # Calculate statistics
    total_items = len(items)
    low_stock_items = [item for item in items if item.is_low_stock]
    
    return render_template('inventory.html', 
                         items=items, 
                         categories=categories,
                         search=search,
                         category_filter=category_filter,
                         sort_by=sort_by,
                         total_items=total_items,
                         low_stock_count=len(low_stock_items))

@app.route('/add_item', methods=['GET', 'POST'])
@login_required
def add_item():
    form = InventoryItemForm()
    if form.validate_on_submit():
        # Check for duplicate SKU if provided
        if form.sku.data:
            existing_item = InventoryItem.query.filter_by(sku=form.sku.data).first()
            if existing_item:
                flash('El SKU ya existe', 'danger')
                return render_template('add_item.html', form=form)
        
        item = InventoryItem(
            name=form.name.data,
            description=form.description.data,
            quantity=form.quantity.data,
            minimum_stock=form.minimum_stock.data,
            sku=form.sku.data if form.sku.data else None,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            user_id=current_user.id
        )
        db.session.add(item)
        db.session.commit()
        flash('¡Artículo agregado exitosamente!', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('add_item.html', form=form)

@app.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    item = InventoryItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    form = InventoryItemForm(obj=item)
    
    if form.validate_on_submit():
        # Check for duplicate SKU if changed
        if form.sku.data and form.sku.data != item.sku:
            existing_item = InventoryItem.query.filter_by(sku=form.sku.data).first()
            if existing_item:
                flash('El SKU ya existe', 'danger')
                return render_template('edit_item.html', form=form, item=item)
        
        item.name = form.name.data
        item.description = form.description.data
        item.quantity = form.quantity.data
        item.minimum_stock = form.minimum_stock.data
        item.sku = form.sku.data if form.sku.data else None
        item.category_id = form.category_id.data if form.category_id.data != 0 else None
        
        db.session.commit()
        flash('¡Artículo actualizado exitosamente!', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('edit_item.html', form=form, item=item)

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    item = InventoryItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('¡Artículo eliminado exitosamente!', 'success')
    return redirect(url_for('inventory'))

@app.route('/reports')
@login_required
def reports():
    # Calculate comprehensive statistics
    items = InventoryItem.query.filter_by(user_id=current_user.id).all()
    
    total_items = len(items)
    low_stock_items = [item for item in items if item.is_low_stock]
    
    # Category breakdown
    category_stats = db.session.query(
        Category.name,
        func.count(InventoryItem.id).label('item_count'),
        func.sum(InventoryItem.quantity).label('total_quantity')
    ).join(InventoryItem, Category.id == InventoryItem.category_id)\
     .filter(InventoryItem.user_id == current_user.id)\
     .group_by(Category.name).all()
    
    # Items without category
    uncategorized_count = InventoryItem.query.filter_by(
        user_id=current_user.id, 
        category_id=None
    ).count()
    
    uncategorized_quantity = db.session.query(
        func.sum(InventoryItem.quantity)
    ).filter(InventoryItem.user_id == current_user.id,
             InventoryItem.category_id.is_(None)).scalar() or 0
    
    return render_template('reports.html',
                         total_items=total_items,
                         items=items,
                         low_stock_items=low_stock_items,
                         category_stats=category_stats,
                         uncategorized_count=uncategorized_count,
                         uncategorized_quantity=uncategorized_quantity)

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        existing_category = Category.query.filter_by(name=form.name.data).first()
        if existing_category:
            flash('La categoría ya existe', 'danger')
        else:
            category = Category(name=form.name.data, description=form.description.data)
            db.session.add(category)
            db.session.commit()
            flash('¡Categoría creada exitosamente!', 'success')
            return redirect(url_for('categories'))
    
    categories = Category.query.all()
    return render_template('categories.html', form=form, categories=categories)

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    # Check if category has items
    item_count = InventoryItem.query.filter_by(category_id=category_id).count()
    if item_count > 0:
        flash(f'No se puede eliminar la categoría. Contiene {item_count} artículos.', 'danger')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('¡Categoría eliminada exitosamente!', 'success')
    return redirect(url_for('categories'))
