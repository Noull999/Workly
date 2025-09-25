from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from . import notion
from ..decorators import module_required
from models import NotionPage, NotionBlock, NotionPermission, NotionChecklist, NotionChecklistItem, ModuleLink
from forms import NotionPageForm, NotionBlockForm, NotionChecklistForm, NotionChecklistItemForm, NotionPageActionForm
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

@notion.route('/checklist/<int:checklist_id>')
@login_required
@module_required('notion')
def checklist(checklist_id):
    """Ver checklist específico"""
    checklist = company_query(NotionChecklist).filter_by(id=checklist_id).first_or_404()
    items = company_query(NotionChecklistItem).filter_by(checklist_id=checklist_id).order_by(NotionChecklistItem.position).all()
    
    return render_template('modules/notion/checklist.html', 
                         checklist=checklist, 
                         items=items,
                         company=current_user.company)

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