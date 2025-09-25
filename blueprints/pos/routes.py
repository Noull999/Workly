from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
from . import pos
from ..decorators import module_required
from models import Sale, SaleItem, InventoryItem, CashSession, PaymentDetail, CashExpense, OfflineSync
from forms import SaleForm, CashSessionForm, CashSessionCloseForm, CashExpenseForm, MultiPaymentForm
from utils import company_query, log_audit
from app import db

@pos.route('/', methods=['GET', 'POST'])
@login_required
@module_required('pos')
def sales():
    """Punto de venta"""
    # Verificar si hay sesión de caja abierta
    today = date.today()
    current_session = CashSession.query.filter_by(
        company_id=current_user.company_id,
        session_date=today,
        status='open'
    ).first()
    
    # Mostrar advertencia si no hay caja abierta
    if not current_session:
        flash('Advertencia: No hay una sesión de caja abierta hoy. Las ventas no se asociarán a caja.', 'warning')
    
    form = SaleForm()
    
    if form.validate_on_submit():
        # Procesar venta desde datos del carrito
        cart_data = request.form.get('cart_data')
        
        if cart_data:
            try:
                cart_items = json.loads(cart_data)
                
                # Crear venta
                sale = Sale(  # type: ignore
                    sale_number=Sale.generate_sale_number(current_user.company_id),
                    company_id=current_user.company_id,
                    user_id=current_user.id,
                    cash_session_id=current_session.id if current_session else None,
                    status='completada',
                    notes=form.notes.data
                )
                
                total_amount = 0
                
                # Agregar items a la venta
                for cart_item in cart_items:
                    inventory_item = company_query(InventoryItem).filter_by(id=cart_item['id']).first()
                    if inventory_item and inventory_item.quantity >= cart_item['quantity']:
                        # SEGURIDAD: Usar precio del servidor, no del cliente
                        server_unit_price = inventory_item.price or Decimal('0')
                        server_total_price = server_unit_price * Decimal(str(cart_item['quantity']))
                        
                        # Crear item de venta con precios del servidor
                        sale_item = SaleItem(  # type: ignore
                            quantity=cart_item['quantity'],
                            unit_price=server_unit_price,
                            total_price=server_total_price,
                            inventory_item_id=inventory_item.id
                        )
                        sale.items.append(sale_item)
                        total_amount += sale_item.total_price
                        
                        # Actualizar inventario
                        inventory_item.quantity -= cart_item['quantity']
                    else:
                        flash(f'Stock insuficiente para {inventory_item.name if inventory_item else "item desconocido"}', 'error')
                        return redirect(url_for('pos.sales'))
                
                # Calcular impuestos y total
                sale.tax_amount = total_amount * Decimal('0.19')
                sale.total_amount = total_amount + sale.tax_amount
                
                # Crear detalle de pago (método único por ahora)
                payment_detail = PaymentDetail(  # type: ignore
                    payment_method=form.payment_method.data,
                    amount=sale.total_amount,
                    notes=f"Pago completo por {form.payment_method.data}"
                )
                sale.payment_details.append(payment_detail)
                
                # Actualizar totales de sesión de caja si existe
                if current_session:
                    current_session.total_sales += sale.total_amount
                
                db.session.add(sale)
                db.session.commit()
                
                flash(f'Venta {sale.sale_number} procesada exitosamente por ${sale.total_amount}', 'success')
                return redirect(url_for('pos.sale_receipt', sale_id=sale.id))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error procesando la venta: {str(e)}', 'error')
                return redirect(url_for('pos.sales'))
    
    # Obtener items de inventario con stock
    items = company_query(InventoryItem).filter(InventoryItem.quantity > 0).all()
    
    return render_template('modules/pos.html', form=form, items=items, current_session=current_session)

@pos.route('/receipt/<int:sale_id>')
@login_required
@module_required('pos')
def sale_receipt(sale_id):
    """Mostrar comprobante de venta"""
    # Buscar la venta
    sale = Sale.query.filter_by(
        id=sale_id,
        company_id=current_user.company_id
    ).first()
    
    if not sale:
        flash('Venta no encontrada.', 'error')
        return redirect(url_for('pos.sales'))
    
    return render_template('modules/receipt.html', sale=sale)

@pos.route('/cash-management')
@login_required
@module_required('pos')
def cash_management():
    """Gestión de caja - Dashboard"""
    today = date.today()
    current_session = CashSession.query.filter_by(
        company_id=current_user.company_id,
        session_date=today,
        status='open'
    ).first()
    
    # Obtener sesiones recientes
    recent_sessions = CashSession.query.filter_by(
        company_id=current_user.company_id
    ).order_by(CashSession.session_date.desc()).limit(10).all()
    
    # Estadísticas de la sesión actual
    session_stats = {}
    if current_session:
        session_stats = {
            'total_sales': current_session.total_sales,
            'total_expenses': current_session.total_expenses,
            'expected_amount': current_session.calculate_expected_amount()
        }
    
    return render_template('modules/cash_management.html', 
                         current_session=current_session,
                         recent_sessions=recent_sessions,
                         session_stats=session_stats)

@pos.route('/open-cash-session', methods=['GET', 'POST'])
@login_required
@module_required('pos')
def open_cash_session():
    """Abrir sesión de caja"""
    today = date.today()
    
    # Verificar si ya hay una sesión abierta hoy
    existing_session = CashSession.query.filter_by(
        company_id=current_user.company_id,
        session_date=today,
        status='open'
    ).first()
    
    if existing_session:
        flash('Ya hay una sesión de caja abierta para hoy.', 'warning')
        return redirect(url_for('pos.cash_management'))
    
    form = CashSessionForm()
    
    if form.validate_on_submit():
        session = CashSession(  # type: ignore
            opening_amount=form.opening_amount.data,
            notes=form.notes.data,
            company_id=current_user.company_id,
            opened_by_id=current_user.id,
            session_date=today
        )
        
        db.session.add(session)
        db.session.commit()
        
        log_audit('pos', f'Sesión de caja abierta con ${form.opening_amount.data}', current_user.id, current_user.company_id)
        flash(f'Sesión de caja abierta exitosamente con ${form.opening_amount.data}', 'success')
        return redirect(url_for('pos.cash_management'))
    
    return render_template('modules/open_cash_session.html', form=form)

@pos.route('/close-cash-session', methods=['GET', 'POST'])
@login_required
@module_required('pos')
def close_cash_session():
    """Cerrar sesión de caja"""
    today = date.today()
    current_session = CashSession.query.filter_by(
        company_id=current_user.company_id,
        session_date=today,
        status='open'
    ).first()
    
    if not current_session:
        flash('No hay una sesión de caja abierta para cerrar.', 'warning')
        return redirect(url_for('pos.cash_management'))
    
    form = CashSessionCloseForm()
    
    if form.validate_on_submit():
        current_session.closing_amount = form.closing_amount.data
        current_session.notes = (current_session.notes or '') + f'\n[CIERRE] {form.notes.data}'
        current_session.status = 'closed'
        current_session.closed_by_id = current_user.id
        current_session.closed_at = datetime.utcnow()
        
        # Calcular diferencia
        expected_amount = current_session.calculate_expected_amount()
        current_session.expected_amount = expected_amount
        current_session.difference_amount = float(form.closing_amount.data) - float(expected_amount)  # type: ignore
        
        db.session.commit()
        
        log_audit('pos', f'Sesión de caja cerrada. Diferencia: ${current_session.difference_amount}', current_user.id, current_user.company_id)
        flash(f'Sesión de caja cerrada. Diferencia: ${current_session.difference_amount:.2f}', 'success')
        return redirect(url_for('pos.cash_management'))
    
    # Calcular monto esperado para mostrar en el formulario
    expected_amount = current_session.calculate_expected_amount()
    
    return render_template('modules/close_cash_session.html', 
                         form=form, 
                         session=current_session, 
                         expected_amount=expected_amount)

@pos.route('/cash-expenses', methods=['GET', 'POST'])
@login_required
@module_required('pos')
def cash_expenses():
    """Manejar egresos de caja"""
    today = date.today()
    current_session = CashSession.query.filter_by(
        company_id=current_user.company_id,
        session_date=today,
        status='open'
    ).first()
    
    if not current_session:
        flash('Debe abrir una sesión de caja antes de registrar egresos.', 'warning')
        return redirect(url_for('pos.open_cash_session'))
    
    form = CashExpenseForm()
    
    if form.validate_on_submit():
        expense = CashExpense(  # type: ignore
            description=form.description.data,
            amount=form.amount.data,
            category=form.category.data,
            receipt_number=form.receipt_number.data,
            cash_session_id=current_session.id,
            company_id=current_user.company_id,
            user_id=current_user.id
        )
        
        # Actualizar total de egresos en la sesión
        current_session.total_expenses += form.amount.data
        
        db.session.add(expense)
        db.session.commit()
        
        log_audit('pos', f'Egreso registrado: ${form.amount.data} - {form.description.data}', current_user.id, current_user.company_id)
        flash(f'Egreso registrado exitosamente: ${form.amount.data}', 'success')
        return redirect(url_for('pos.cash_expenses'))
    
    # Obtener egresos de la sesión actual
    expenses = CashExpense.query.filter_by(cash_session_id=current_session.id).order_by(CashExpense.created_at.desc()).all()
    
    return render_template('modules/cash_expenses.html', 
                         form=form, 
                         expenses=expenses, 
                         session=current_session)