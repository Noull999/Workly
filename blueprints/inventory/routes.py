from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from . import inventory
from ..decorators import module_required
from models import InventoryItem, Category, Warehouse
from forms import InventoryItemForm, CategoryForm, WarehouseForm
from utils import company_query, log_audit
from app import db

@inventory.route('/')
@login_required
@module_required('inventory')
def index():
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    warehouse_filter = request.args.get('warehouse', '')
    sort_by = request.args.get('sort', 'name')
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Items por página
    
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
    
    # Paginación para mejorar performance
    pagination = query.paginate(
        page=page, 
        per_page=per_page,
        error_out=False
    )
    items = pagination.items
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
                         pagination=pagination,
                         total_items=pagination.total,
                         low_stock_count=len(low_stock_items))

@inventory.route('/add', methods=['GET', 'POST'])
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
            price=form.price.data if form.price.data else None,
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
        return redirect(url_for('inventory.index'))
    
    return render_template('add_item.html', form=form)

@inventory.route('/edit/<int:item_id>', methods=['GET', 'POST'])
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
        'sku': item.sku,
        'price': item.price
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
        item.price = form.price.data if form.price.data else None
        item.category_id = form.category_id.data if form.category_id.data != 0 else None
        item.warehouse_id = form.warehouse_id.data
        
        db.session.commit()
        
        # Log the audit
        new_values = {
            'name': item.name,
            'quantity': item.quantity,
            'warehouse_id': item.warehouse_id,
            'barcode': item.barcode,
            'sku': item.sku,
            'price': item.price
        }
        log_audit('inventory_item', item.id, 'UPDATE', original_values, new_values)
        
        flash('¡Artículo actualizado exitosamente!', 'success')
        return redirect(url_for('inventory.index'))
    
    return render_template('edit_item.html', form=form, item=item)

@inventory.route('/delete/<int:item_id>', methods=['POST'])
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
    return redirect(url_for('inventory.index'))

@inventory.route('/reports')
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

@inventory.route('/categories', methods=['GET', 'POST'])
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
            return redirect(url_for('inventory.categories'))
    
    categories = company_query(Category).all()
    return render_template('categories.html', form=form, categories=categories)

@inventory.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
@module_required('inventory')
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
    return redirect(url_for('inventory.categories'))

@inventory.route('/warehouses', methods=['GET', 'POST'])
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
            return redirect(url_for('inventory.warehouses'))
    
    warehouses = company_query(Warehouse).filter_by(is_active=True).all()
    return render_template('warehouses.html', form=form, warehouses=warehouses)

@inventory.route('/delete_warehouse/<int:warehouse_id>', methods=['POST'])
@login_required
@module_required('inventory')
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
    return redirect(url_for('inventory.warehouses'))