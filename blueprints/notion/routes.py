from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import json
from . import notion
from ..decorators import module_required
from models import NotionPage, NotionBlock, NotionPermission, NotionChecklist, NotionChecklistItem, ModuleLink
from forms import NotionPageForm, NotionBlockForm, NotionChecklistForm, NotionChecklistItemForm, NotionPageActionForm, NotionBlockActionForm, NotionDeletePageForm
from utils import company_query, log_audit
from app import db

@notion.route('/')
@login_required
@module_required('notion')
def dashboard():
    """Dashboard principal del módulo Notion"""
    company = current_user.company
    
    # Páginas principales (sin padre)
    main_pages = company_query(NotionPage).filter_by(parent_id=None).order_by(NotionPage.position).all()
    
    # Páginas recientes
    recent_pages = company_query(NotionPage).order_by(NotionPage.updated_at.desc()).limit(5).all()
    
    # Checklists activos
    active_checklists = company_query(NotionChecklist).join(NotionChecklistItem).filter(
        NotionChecklistItem.is_completed == False
    ).distinct().limit(3).all()
    
    return render_template('modules/notion/dashboard.html', 
                         main_pages=main_pages, 
                         recent_pages=recent_pages,
                         active_checklists=active_checklists,
                         company=company)

@notion.route('/page/new', methods=['GET', 'POST'])
@login_required
@module_required('notion')
def new_page():
    """Crear nueva página"""
    form = NotionPageForm(company_id=current_user.company_id)
    
    if form.validate_on_submit():
        # Generar slug único
        base_slug = (form.title.data or '').lower().replace(' ', '-').replace('_', '-')
        slug = base_slug
        counter = 1
        while company_query(NotionPage).filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        page = NotionPage(  # type: ignore
            title=form.title.data,
            slug=slug,
            icon=form.icon.data or '📄',
            is_public=form.is_public.data,
            is_template=form.is_template.data,
            parent_id=form.parent_id.data if form.parent_id.data != 0 else None,
            company_id=current_user.company_id,
            creator_id=current_user.id
        )
        
        db.session.add(page)
        db.session.commit()
        
        # Crear bloque inicial de texto
        initial_block = NotionBlock(  # type: ignore
            block_type='text',
            content='Comienza a escribir aquí...',
            position=0,
            page_id=page.id,
            company_id=current_user.company_id
        )
        db.session.add(initial_block)
        db.session.commit()
        
        log_audit('notion', f'Página creada: {page.title}', current_user.id, current_user.company_id)
        flash('Página creada exitosamente', 'success')
        return redirect(url_for('notion.page', slug=page.slug))
    
    return render_template('modules/notion/new_page.html', form=form, company=current_user.company)

@notion.route('/page/<slug>')
@login_required
@module_required('notion')
def page(slug):
    """Ver página específica"""
    page = company_query(NotionPage).filter_by(slug=slug).first_or_404()
    
    # Verificar permisos
    can_edit = (page.creator_id == current_user.id or 
               current_user.is_admin_empresa() or 
               current_user.is_admin_global() or
               page.is_public)
    
    # Obtener bloques ordenados
    blocks = company_query(NotionBlock).filter_by(page_id=page.id).order_by(NotionBlock.position).all()
    
    # Páginas hijas
    child_pages = company_query(NotionPage).filter_by(parent_id=page.id).order_by(NotionPage.position).all()
    
    # Formulario para acciones de página (duplicar, etc.)
    duplicate_form = NotionPageActionForm()
    duplicate_form.action.data = 'duplicate'
    
    return render_template('modules/notion/page.html', 
                         page=page, 
                         blocks=blocks,
                         child_pages=child_pages,
                         can_edit=can_edit,
                         duplicate_form=duplicate_form,
                         company=current_user.company)

@notion.route('/checklists')
@login_required
@module_required('notion')
def checklists():
    """Lista de checklists"""
    checklists = company_query(NotionChecklist).order_by(NotionChecklist.created_at.desc()).all()
    return render_template('modules/notion/checklists.html', checklists=checklists, company=current_user.company)

@notion.route('/checklist/new', methods=['GET', 'POST'])
@login_required
@module_required('notion')
def new_checklist():
    """Crear nuevo checklist"""
    form = NotionChecklistForm(company_id=current_user.company_id)
    
    if form.validate_on_submit():
        checklist = NotionChecklist(  # type: ignore
            title=form.title.data,
            description=form.description.data,
            checklist_type=form.checklist_type.data,
            page_id=form.page_id.data if form.page_id.data != 0 else None,
            company_id=current_user.company_id,
            creator_id=current_user.id
        )
        
        db.session.add(checklist)
        db.session.commit()
        
        log_audit('notion', f'Checklist creado: {checklist.title}', current_user.id, current_user.company_id)
        flash('Checklist creado exitosamente', 'success')
        return redirect(url_for('notion.checklist', checklist_id=checklist.id))
    
    return render_template('modules/notion/new_checklist.html', form=form, company=current_user.company)

@notion.route('/checklist/<int:checklist_id>', methods=['GET', 'POST'])
@login_required
@module_required('notion')
def checklist(checklist_id):
    """Ver checklist específico"""
    checklist = company_query(NotionChecklist).filter_by(id=checklist_id).first_or_404()
    items = company_query(NotionChecklistItem).filter_by(checklist_id=checklist_id).order_by(NotionChecklistItem.position).all()
    
    # Formulario para agregar nuevos items
    form = NotionChecklistItemForm(company_id=current_user.company_id)
    
    if request.method == 'POST' and form.validate_on_submit():
        # Agregar nuevo item al checklist
        next_position = len(items)
        new_item = NotionChecklistItem(
            content=form.content.data,
            checklist_id=checklist.id,
            assignee_id=form.assignee_id.data if form.assignee_id.data != 0 else None,
            due_date=form.due_date.data,
            position=next_position,
            company_id=current_user.company_id
        )
        
        db.session.add(new_item)
        db.session.commit()
        
        log_audit('notion', f'Item agregado al checklist: {checklist.title}', current_user.id, current_user.company_id)
        flash('Tarea agregada exitosamente', 'success')
        return redirect(url_for('notion.checklist', checklist_id=checklist.id))
    
    return render_template('modules/notion/checklist.html', 
                         checklist=checklist, 
                         items=items,
                         form=form,
                         company=current_user.company)

@notion.route('/page/<slug>/edit', methods=['GET', 'POST'])
@login_required
@module_required('notion')
def edit_page(slug):
    """Editar página de Notion con funcionalidades completas"""
    page = company_query(NotionPage).filter_by(slug=slug).first_or_404()
    
    # Verificar permisos de edición
    can_edit = (page.creator_id == current_user.id or 
               current_user.is_admin_empresa() or 
               current_user.is_admin_global())
    
    if not can_edit:
        flash('No tienes permisos para editar esta página', 'danger')
        return redirect(url_for('notion.page', slug=slug))
    
    # Obtener bloques de la página
    blocks = company_query(NotionBlock).filter_by(page_id=page.id).order_by(NotionBlock.position).all()
    
    # Inicializar formularios
    page_form = NotionPageForm(company_id=current_user.company_id, obj=page)
    block_form = NotionBlockForm()
    block_action_form = NotionBlockActionForm()
    delete_form = NotionDeletePageForm()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_page' and page_form.validate_on_submit():
            # Actualizar configuración de página
            page.title = page_form.title.data
            page.icon = page_form.icon.data or '📄'
            page.parent_id = page_form.parent_id.data if page_form.parent_id.data != 0 else None
            page.is_public = page_form.is_public.data
            page.is_template = page_form.is_template.data
            page.updated_at = datetime.now()
            
            # Actualizar slug si cambió el título
            new_slug = (page.title or '').lower().replace(' ', '-')
            new_slug = ''.join(c for c in new_slug if c.isalnum() or c in '-_')
            if new_slug != page.slug:
                # Verificar que el nuevo slug no exista
                existing = company_query(NotionPage).filter_by(slug=new_slug).first()
                if not existing:
                    page.slug = new_slug
            
            db.session.commit()
            log_audit('notion', f'Página actualizada: {page.title}', current_user.id, current_user.company_id)
            flash('Página actualizada exitosamente', 'success')
            return redirect(url_for('notion.edit_page', slug=page.slug))
            
        elif action == 'add_block' and block_form.validate_on_submit():
            # Agregar nuevo bloque
            next_position = len(blocks)
            new_block = NotionBlock(
                page_id=page.id,
                block_type=block_form.block_type.data,
                content=block_form.content.data,
                position=next_position,
                company_id=current_user.company_id
            )
            db.session.add(new_block)
            db.session.commit()
            
            log_audit('notion', f'Bloque agregado a página: {page.title}', current_user.id, current_user.company_id)
            flash('Bloque agregado exitosamente', 'success')
            return redirect(url_for('notion.edit_page', slug=slug))
            
        elif action == 'update_block':
            # Actualizar bloque existente
            block_id = request.form.get('block_id')
            if block_id:
                block = company_query(NotionBlock).filter_by(id=block_id).first()
                if block:
                    block.block_type = request.form.get('block_type')
                    block.content = request.form.get('content')
                    db.session.commit()
                    flash('Bloque actualizado exitosamente', 'success')
                    return redirect(url_for('notion.edit_page', slug=slug))
                    
        elif action == 'delete_block':
            # Eliminar bloque
            block_id = request.form.get('block_id')
            if block_id:
                block = company_query(NotionBlock).filter_by(id=block_id).first()
                if block:
                    db.session.delete(block)
                    db.session.commit()
                    flash('Bloque eliminado exitosamente', 'success')
                    return redirect(url_for('notion.edit_page', slug=slug))
                    
        elif action == 'duplicate':
            # Duplicar página
            new_title = f"{page.title} (Copia)"
            new_slug = f"{page.slug}-copia"
            
            # Asegurar slug único
            counter = 1
            while company_query(NotionPage).filter_by(slug=new_slug).first():
                new_slug = f"{page.slug}-copia-{counter}"
                counter += 1
            
            new_page = NotionPage(
                title=new_title,
                slug=new_slug,
                icon=page.icon,
                is_public=page.is_public,
                is_template=page.is_template,
                parent_id=page.parent_id,
                creator_id=current_user.id,
                company_id=current_user.company_id
            )
            db.session.add(new_page)
            db.session.flush()  # Para obtener el ID
            
            # Duplicar bloques
            for block in blocks:
                new_block = NotionBlock(
                    page_id=new_page.id,
                    block_type=block.block_type,
                    content=block.content,
                    position=block.position,
                    company_id=current_user.company_id
                )
                db.session.add(new_block)
            
            db.session.commit()
            log_audit('notion', f'Página duplicada: {new_title}', current_user.id, current_user.company_id)
            flash(f'Página duplicada como "{new_title}"', 'success')
            return redirect(url_for('notion.edit_page', slug=new_slug))
    
    return render_template('modules/notion/edit_page.html',
                         page=page, 
                         blocks=blocks,
                         page_form=page_form,
                         block_form=block_form,
                         block_action_form=block_action_form,
                         delete_form=delete_form,
                         company=current_user.company)

@notion.route('/block/<int:block_id>/checklist-item', methods=['POST'])
@login_required
@module_required('notion')
def update_checklist_item(block_id):
    """Actualizar estado de item de checklist via AJAX"""
    try:
        # Obtener el bloque
        block = company_query(NotionBlock).filter_by(id=block_id).first_or_404()
        
        # Verificar que es un checklist
        if block.block_type != 'checklist':
            return jsonify({'success': False, 'message': 'Block is not a checklist'})
        
        # Obtener datos del request
        data = request.get_json()
        item_index = data.get('item_index')
        is_checked = data.get('is_checked')
        
        if item_index is None or is_checked is None:
            return jsonify({'success': False, 'message': 'Missing required parameters'})
        
        # Obtener o crear properties
        if block.properties:
            properties = json.loads(block.properties)
        else:
            properties = {}
        
        # Obtener lista de items marcados
        checked_items = properties.get('checked_items', [])
        
        # Actualizar estado
        if is_checked:
            if item_index not in checked_items:
                checked_items.append(item_index)
        else:
            if item_index in checked_items:
                checked_items.remove(item_index)
        
        # Guardar cambios
        properties['checked_items'] = checked_items
        block.properties = json.dumps(properties)
        block.updated_at = datetime.now()
        
        db.session.commit()
        
        # Log audit
        log_audit('notion', f'Checklist item updated in block {block_id}', current_user.id, current_user.company_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@notion.route('/checklist/<int:checklist_id>/edit', methods=['GET', 'POST'])
@login_required
@module_required('notion')
def edit_checklist(checklist_id):
    """Editar checklist"""
    checklist = company_query(NotionChecklist).filter_by(id=checklist_id).first_or_404()
    form = NotionChecklistForm(company_id=current_user.company_id, obj=checklist)
    
    if form.validate_on_submit():
        checklist.title = form.title.data
        checklist.description = form.description.data
        checklist.checklist_type = form.checklist_type.data
        checklist.page_id = form.page_id.data if form.page_id.data != 0 else None
        checklist.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        log_audit('notion', f'Checklist editado: {checklist.title}', current_user.id, current_user.company_id)
        flash('Checklist actualizado exitosamente', 'success')
        return redirect(url_for('notion.checklist', checklist_id=checklist.id))
    
    return redirect(url_for('notion.checklist', checklist_id=checklist.id))