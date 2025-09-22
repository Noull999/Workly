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