from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
from . import scrum
from ..decorators import module_required, admin_required
from models import Board, Sprint, Task, Column, TaskComment
from utils import company_query, log_audit
from app import db

@scrum.route('/')
@login_required
@module_required('scrum')
def dashboard():
    """Dashboard principal de Scrum Lite"""
    company = current_user.company
    boards = company_query(Board).filter_by(is_active=True).all()
    
    # Estadísticas rápidas
    my_tasks = company_query(Task).filter_by(assignee_id=current_user.id).filter(
        Task.status != 'done'
    ).all()
    
    return render_template('modules/scrum/dashboard.html', boards=boards, my_tasks=my_tasks, company=company)

@scrum.route('/board/<int:board_id>')
@login_required
@module_required('scrum')
def board(board_id):
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

@scrum.route('/create-board', methods=['GET', 'POST'])
@login_required
@module_required('scrum')
@admin_required
def create_board():
    """Crear nuevo tablero"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('El nombre del tablero es obligatorio', 'danger')
            return redirect(url_for('scrum.create_board'))
        
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
        return redirect(url_for('scrum.board', board_id=board.id))
    
    return render_template('modules/scrum/create_board.html', company=current_user.company)

@scrum.route('/create-task/<int:board_id>/<int:column_id>', methods=['POST'])
@login_required
@module_required('scrum')
def create_task(board_id, column_id):
    """Crear nueva tarea"""
    board = company_query(Board).filter_by(id=board_id, is_active=True).first_or_404()
    column = company_query(Column).filter_by(id=column_id, board_id=board_id).first_or_404()
    
    title = request.form.get('title')
    description = request.form.get('description', '')
    priority = request.form.get('priority', 'medium')
    
    if not title:
        flash('El título es obligatorio', 'danger')
        return redirect(url_for('scrum.board', board_id=board_id))
    
    # Obtener siguiente posición
    max_position = db.session.query(func.max(Task.position)).filter_by(column_id=column_id).scalar() or 0
    
    task = Task(
        title=title,
        description=description,
        priority=priority,
        status='pending',
        position=max_position + 1,
        column_id=column_id,
        board_id=board_id,
        assignee_id=current_user.id,
        creator_id=current_user.id,
        company_id=current_user.company_id
    )
    
    db.session.add(task)
    db.session.commit()
    
    log_audit('scrum', f'Tarea creada: {task.title}', current_user.id, current_user.company_id)
    flash('Tarea creada exitosamente', 'success')
    return redirect(url_for('scrum.board', board_id=board_id))

@scrum.route('/edit-task/<int:task_id>', methods=['GET', 'POST'])
@login_required
@module_required('scrum')
def edit_task(task_id):
    """Editar tarea"""
    task = company_query(Task).filter_by(id=task_id).first_or_404()
    
    if request.method == 'POST':
        task.title = request.form.get('title', task.title)
        task.description = request.form.get('description', task.description)
        task.priority = request.form.get('priority', task.priority)
        
        db.session.commit()
        log_audit('scrum', f'Tarea editada: {task.title}', current_user.id, current_user.company_id)
        flash('Tarea actualizada exitosamente', 'success')
        return redirect(url_for('scrum.board', board_id=task.board_id))
    
    return redirect(url_for('scrum.board', board_id=task.board_id))

@scrum.route('/delete-task/<int:task_id>', methods=['POST'])
@login_required
@module_required('scrum')
def delete_task(task_id):
    """Eliminar tarea"""
    task = company_query(Task).filter_by(id=task_id).first_or_404()
    board_id = task.board_id
    
    db.session.delete(task)
    db.session.commit()
    
    log_audit('scrum', f'Tarea eliminada: {task.title}', current_user.id, current_user.company_id)
    flash('Tarea eliminada exitosamente', 'success')
    return redirect(url_for('scrum.board', board_id=board_id))

@scrum.route('/task/move', methods=['POST'])
@login_required
@module_required('scrum')
def move_task():
    """Mover tarea entre columnas (AJAX)"""
    from flask import jsonify
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
    
    task_id = data.get('task_id')
    column_id = data.get('column_id')
    position = data.get('position', 0)
    
    if not task_id or not column_id:
        return jsonify({'success': False, 'error': 'task_id y column_id son requeridos'}), 400
    
    # Buscar la tarea
    task = company_query(Task).filter_by(id=task_id).first()
    if not task:
        return jsonify({'success': False, 'error': 'Tarea no encontrada'}), 404
    
    # Buscar la nueva columna
    new_column = company_query(Column).filter_by(id=column_id).first()
    if not new_column:
        return jsonify({'success': False, 'error': 'Columna no encontrada'}), 404
    
    # Verificar que la columna pertenece a la misma empresa
    if new_column.board.company_id != current_user.company_id:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    # Obtener contadores antes del cambio
    old_column_id = task.column_id
    old_count = company_query(Task).filter_by(column_id=old_column_id).count() - 1
    new_count = company_query(Task).filter_by(column_id=column_id).count() + 1
    
    # Actualizar la tarea
    task.column_id = column_id
    task.position = position
    
    try:
        db.session.commit()
        
        # Log de auditoría
        log_audit('scrum', f'Tarea "{task.title}" movida a columna "{new_column.name}"', 
                 current_user.id, current_user.company_id)
        
        return jsonify({
            'success': True,
            'old_column_id': old_column_id,
            'new_column_id': column_id,
            'old_count': old_count,
            'new_count': new_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al mover la tarea: {str(e)}'}), 500