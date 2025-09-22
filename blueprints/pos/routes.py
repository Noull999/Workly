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
                sale = Sale(
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
                        # Crear item de venta
                        sale_item = SaleItem(
                            quantity=cart_item['quantity'],
                            unit_price=cart_item['price'],
                            total_price=cart_item['price'] * cart_item['quantity'],
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
                payment_detail = PaymentDetail(
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