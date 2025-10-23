from flask import render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, distinct
from decimal import Decimal
import csv
import io
import json

from . import reports
from app import db
from models import (
    Company, User, InventoryItem, Category, Warehouse, Sale, SaleItem,
    Service, Appointment, CashSession, CashExpense, PaymentDetail,
    Board, BoardColumn, Task, NotionPage
)
from blueprints.decorators import admin_required
from utils import company_query


@reports.route('/')
@login_required
def dashboard():
    """Dashboard principal de reportes con vista ejecutiva"""
    company = current_user.company
    
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    stats = {
        'modules_active': sum([
            company.module_inventory,
            company.module_pos,
            company.module_appointments,
            company.module_portfolio,
            company.module_scrum,
            company.module_notion
        ]),
        'users_count': User.query.filter_by(company_id=current_user.company_id).count()
    }
    
    if company.module_inventory:
        stats['inventory'] = {
            'total_items': company_query(InventoryItem).count(),
            'low_stock': company_query(InventoryItem).filter(
                InventoryItem.quantity <= InventoryItem.minimum_stock
            ).count(),
            'total_quantity': db.session.query(
                func.sum(InventoryItem.quantity)
            ).filter(InventoryItem.company_id == current_user.company_id).scalar() or 0
        }
    
    if company.module_pos:
        today_sales = company_query(Sale).filter(
            func.date(Sale.created_at) == today
        ).all()
        
        week_sales = company_query(Sale).filter(
            func.date(Sale.created_at) >= week_ago
        ).all()
        
        month_sales = company_query(Sale).filter(
            func.date(Sale.created_at) >= month_ago
        ).all()
        
        stats['pos'] = {
            'today_sales': sum(s.total_amount for s in today_sales),
            'today_count': len(today_sales),
            'week_sales': sum(s.total_amount for s in week_sales),
            'week_count': len(week_sales),
            'month_sales': sum(s.total_amount for s in month_sales),
            'month_count': len(month_sales)
        }
    
    if company.module_appointments:
        today_appointments = company_query(Appointment).filter(
            func.date(Appointment.appointment_date) == today
        ).all()
        
        pending_appointments = company_query(Appointment).filter(
            Appointment.status == 'pendiente',
            Appointment.appointment_date >= datetime.now()
        ).count()
        
        stats['appointments'] = {
            'today_count': len(today_appointments),
            'pending_count': pending_appointments,
            'services_active': company_query(Service).filter_by(is_active=True).count()
        }
    
    if company.module_scrum:
        stats['scrum'] = {
            'boards_count': company_query(Board).count(),
            'tasks_total': db.session.query(Task).join(BoardColumn).join(Board).filter(
                Board.company_id == current_user.company_id
            ).count(),
            'tasks_in_progress': db.session.query(Task).join(BoardColumn).join(Board).filter(
                Board.company_id == current_user.company_id,
                BoardColumn.name == 'En Progreso'
            ).count()
        }
    
    if company.module_notion:
        stats['notion'] = {
            'pages_count': company_query(NotionPage).count(),
            'recent_updates': company_query(NotionPage).filter(
                NotionPage.updated_at >= week_ago
            ).count()
        }
    
    return render_template('reports/dashboard.html', stats=stats, company=company)


@reports.route('/sales')
@login_required
def sales_report():
    """Reporte detallado de ventas con filtros"""
    if not current_user.company.module_pos:
        flash('El módulo POS no está activo para tu empresa', 'warning')
        return redirect(url_for('reports.dashboard'))
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    sales = company_query(Sale).filter(
        and_(
            func.date(Sale.created_at) >= start_date,
            func.date(Sale.created_at) <= end_date
        )
    ).order_by(Sale.created_at.desc()).all()
    
    total_amount = sum(s.total_amount for s in sales)
    avg_sale = total_amount / len(sales) if sales else 0
    
    daily_sales = db.session.query(
        func.date(Sale.created_at).label('date'),
        func.count(Sale.id).label('count'),
        func.sum(Sale.total_amount).label('total')
    ).filter(
        Sale.company_id == current_user.company_id,
        func.date(Sale.created_at) >= start_date,
        func.date(Sale.created_at) <= end_date
    ).group_by(func.date(Sale.created_at)).all()
    
    payment_methods = db.session.query(
        PaymentDetail.payment_method,
        func.count(PaymentDetail.id).label('count'),
        func.sum(PaymentDetail.amount).label('total')
    ).join(Sale).filter(
        Sale.company_id == current_user.company_id,
        func.date(Sale.created_at) >= start_date,
        func.date(Sale.created_at) <= end_date
    ).group_by(PaymentDetail.payment_method).all()
    
    top_products = db.session.query(
        InventoryItem.name,
        func.sum(SaleItem.quantity).label('total_quantity'),
        func.sum(SaleItem.total_price).label('total_revenue')
    ).join(SaleItem).join(Sale).filter(
        Sale.company_id == current_user.company_id,
        func.date(Sale.created_at) >= start_date,
        func.date(Sale.created_at) <= end_date
    ).group_by(InventoryItem.name).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(10).all()
    
    return render_template('reports/sales.html',
                         sales=sales,
                         total_amount=total_amount,
                         avg_sale=avg_sale,
                         start_date=start_date,
                         end_date=end_date,
                         daily_sales=daily_sales,
                         payment_methods=payment_methods,
                         top_products=top_products)


@reports.route('/inventory')
@login_required
def inventory_report():
    """Reporte avanzado de inventario"""
    if not current_user.company.module_inventory:
        flash('El módulo Inventario no está activo para tu empresa', 'warning')
        return redirect(url_for('reports.dashboard'))
    
    items = company_query(InventoryItem).all()
    total_items = len(items)
    low_stock_items = [item for item in items if item.is_low_stock]
    
    category_stats = db.session.query(
        Category.name,
        func.count(InventoryItem.id).label('item_count'),
        func.sum(InventoryItem.quantity).label('total_quantity')
    ).join(InventoryItem, Category.id == InventoryItem.category_id)\
     .filter(InventoryItem.company_id == current_user.company_id)\
     .group_by(Category.name).all()
    
    warehouse_stats = db.session.query(
        Warehouse.name,
        func.count(InventoryItem.id).label('item_count'),
        func.sum(InventoryItem.quantity).label('total_quantity')
    ).join(InventoryItem, Warehouse.id == InventoryItem.warehouse_id)\
     .filter(InventoryItem.company_id == current_user.company_id)\
     .group_by(Warehouse.name).all()
    
    uncategorized_count = company_query(InventoryItem).filter_by(category_id=None).count()
    uncategorized_quantity = db.session.query(
        func.sum(InventoryItem.quantity)
    ).filter(InventoryItem.company_id == current_user.company_id,
             InventoryItem.category_id.is_(None)).scalar() or 0
    
    movement_stats = None
    if current_user.company.module_pos:
        last_30_days = date.today() - timedelta(days=30)
        movement_stats = db.session.query(
            InventoryItem.name,
            func.sum(SaleItem.quantity).label('units_sold')
        ).join(SaleItem).join(Sale).filter(
            Sale.company_id == current_user.company_id,
            func.date(Sale.created_at) >= last_30_days
        ).group_by(InventoryItem.name).order_by(
            func.sum(SaleItem.quantity).desc()
        ).limit(10).all()
    
    return render_template('reports/inventory.html',
                         total_items=total_items,
                         items=items,
                         low_stock_items=low_stock_items,
                         category_stats=category_stats,
                         warehouse_stats=warehouse_stats,
                         uncategorized_count=uncategorized_count,
                         uncategorized_quantity=uncategorized_quantity,
                         movement_stats=movement_stats)


@reports.route('/appointments')
@login_required
def appointments_report():
    """Reporte de citas y servicios"""
    if not current_user.company.module_appointments:
        flash('El módulo Citas no está activo para tu empresa', 'warning')
        return redirect(url_for('reports.dashboard'))
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    appointments = company_query(Appointment).filter(
        and_(
            func.date(Appointment.appointment_date) >= start_date,
            func.date(Appointment.appointment_date) <= end_date
        )
    ).all()
    
    status_breakdown = db.session.query(
        Appointment.status,
        func.count(Appointment.id).label('count')
    ).filter(
        Appointment.company_id == current_user.company_id,
        func.date(Appointment.appointment_date) >= start_date,
        func.date(Appointment.appointment_date) <= end_date
    ).group_by(Appointment.status).all()
    
    service_stats = db.session.query(
        Service.name,
        func.count(Appointment.id).label('appointment_count')
    ).join(Appointment).filter(
        Appointment.company_id == current_user.company_id,
        func.date(Appointment.appointment_date) >= start_date,
        func.date(Appointment.appointment_date) <= end_date
    ).group_by(Service.name).all()
    
    daily_appointments = db.session.query(
        func.date(Appointment.appointment_date).label('date'),
        func.count(Appointment.id).label('count')
    ).filter(
        Appointment.company_id == current_user.company_id,
        func.date(Appointment.appointment_date) >= start_date,
        func.date(Appointment.appointment_date) <= end_date
    ).group_by(func.date(Appointment.appointment_date)).all()
    
    return render_template('reports/appointments.html',
                         appointments=appointments,
                         status_breakdown=status_breakdown,
                         service_stats=service_stats,
                         daily_appointments=daily_appointments,
                         start_date=start_date,
                         end_date=end_date)


@reports.route('/integration')
@login_required
def integration_report():
    """Reporte de integración entre módulos"""
    company = current_user.company
    
    report_data = {}
    
    if company.module_pos and company.module_inventory:
        last_30_days = date.today() - timedelta(days=30)
        
        top_selling = db.session.query(
            InventoryItem.name,
            InventoryItem.quantity.label('current_stock'),
            InventoryItem.minimum_stock,
            func.sum(SaleItem.quantity).label('sold_units'),
            func.sum(SaleItem.total_price).label('revenue')
        ).join(SaleItem).join(Sale).filter(
            Sale.company_id == current_user.company_id,
            func.date(Sale.created_at) >= last_30_days
        ).group_by(
            InventoryItem.id, InventoryItem.name, 
            InventoryItem.quantity, InventoryItem.minimum_stock
        ).order_by(func.sum(SaleItem.quantity).desc()).limit(15).all()
        
        report_data['sales_inventory'] = top_selling
        
        restock_needed = [item for item in top_selling 
                         if item.current_stock <= item.minimum_stock]
        report_data['restock_needed'] = restock_needed
    
    if company.module_appointments and company.module_pos:
        services_revenue = db.session.query(
            Service.name,
            func.count(Appointment.id).label('appointments_count')
        ).join(Appointment).filter(
            Appointment.company_id == current_user.company_id,
            Appointment.status == 'completada'
        ).group_by(Service.name).all()
        
        report_data['services_performance'] = services_revenue
    
    return render_template('reports/integration.html', 
                         report_data=report_data,
                         company=company)


@reports.route('/export/<report_type>')
@login_required
def export_report(report_type):
    """Exportar reportes a CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type == 'sales':
        if not current_user.company.module_pos:
            flash('El módulo POS no está activo', 'warning')
            return redirect(url_for('reports.dashboard'))
        
        start_date = request.args.get('start_date', date.today() - timedelta(days=30))
        end_date = request.args.get('end_date', date.today())
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        sales = company_query(Sale).filter(
            and_(
                func.date(Sale.created_at) >= start_date,
                func.date(Sale.created_at) <= end_date
            )
        ).all()
        
        writer.writerow(['Número de Venta', 'Fecha', 'Total', 'Estado', 'Usuario', 'Items'])
        for sale in sales:
            writer.writerow([
                sale.sale_number,
                sale.created_at.strftime('%Y-%m-%d %H:%M'),
                float(sale.total_amount),
                sale.status,
                sale.user.username,
                len(sale.items)
            ])
    
    elif report_type == 'inventory':
        items = company_query(InventoryItem).all()
        
        writer.writerow(['Nombre', 'SKU', 'Cantidad', 'Stock Mínimo', 'Categoría', 'Almacén'])
        for item in items:
            writer.writerow([
                item.name,
                item.sku or '',
                item.quantity,
                item.minimum_stock,
                item.category.name if item.category else 'Sin Categoría',
                item.warehouse.name
            ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{report_type}_report_{date.today()}.csv'
    )


@reports.route('/api/chart-data/<chart_type>')
@login_required
def chart_data(chart_type):
    """API para datos de gráficos"""
    
    if chart_type == 'sales_trend':
        if not current_user.company.module_pos:
            return jsonify({'error': 'Módulo no activo'}), 403
        
        days = int(request.args.get('days', 7))
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        daily_sales = db.session.query(
            func.date(Sale.created_at).label('date'),
            func.sum(Sale.total_amount).label('total')
        ).filter(
            Sale.company_id == current_user.company_id,
            func.date(Sale.created_at) >= start_date,
            func.date(Sale.created_at) <= end_date
        ).group_by(func.date(Sale.created_at)).all()
        
        labels = [(start_date + timedelta(days=i)).strftime('%d/%m') for i in range(days + 1)]
        data = [0] * (days + 1)
        
        for sale_date, total in daily_sales:
            day_index = (sale_date - start_date).days
            if 0 <= day_index <= days:
                data[day_index] = float(total)
        
        return jsonify({
            'labels': labels,
            'data': data
        })
    
    elif chart_type == 'inventory_status':
        if not current_user.company.module_inventory:
            return jsonify({'error': 'Módulo no activo'}), 403
        
        total = company_query(InventoryItem).count()
        low_stock = company_query(InventoryItem).filter(
            InventoryItem.quantity <= InventoryItem.minimum_stock
        ).count()
        normal_stock = total - low_stock
        
        return jsonify({
            'labels': ['Stock Normal', 'Stock Bajo'],
            'data': [normal_stock, low_stock]
        })
    
    elif chart_type == 'appointments_status':
        if not current_user.company.module_appointments:
            return jsonify({'error': 'Módulo no activo'}), 403
        
        status_data = db.session.query(
            Appointment.status,
            func.count(Appointment.id)
        ).filter(
            Appointment.company_id == current_user.company_id
        ).group_by(Appointment.status).all()
        
        status_labels = {
            'pendiente': 'Pendiente',
            'confirmada': 'Confirmada',
            'completada': 'Completada',
            'cancelada': 'Cancelada'
        }
        
        labels = [status_labels.get(s, s) for s, _ in status_data]
        data = [c for _, c in status_data]
        
        return jsonify({
            'labels': labels,
            'data': data
        })
    
    return jsonify({'error': 'Tipo de gráfico no válido'}), 400
