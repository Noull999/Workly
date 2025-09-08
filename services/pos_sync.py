"""
Servicio de sincronización POS Offline
Inventario INTAC - Sistema multiempresa
"""

from datetime import datetime
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app import db
from models import Sale, SaleItem, PaymentDetail, InventoryItem, CashSession, Company, User, OfflineSync


class POSSyncService:
    """Servicio para gestionar sincronización de ventas offline"""
    
    @staticmethod
    def validate_sale_data(sale_data, company_id, user_id):
        """Validar datos de venta antes de procesar"""
        required_fields = ['cart_items', 'payment_methods']
        
        for field in required_fields:
            if field not in sale_data:
                raise ValueError(f"Campo requerido faltante: {field}")
        
        if not sale_data['cart_items']:
            raise ValueError("La venta debe contener al menos un item")
        
        if not sale_data['payment_methods']:
            raise ValueError("La venta debe tener al menos un método de pago")
        
        # Validar que la empresa y usuario existan
        company = Company.query.get(company_id)
        if not company or not company.is_active:
            raise ValueError("Empresa no válida o inactiva")
        
        user = User.query.get(user_id)
        if not user or user.company_id != company_id:
            raise ValueError("Usuario no válido para esta empresa")
        
        return True

    @staticmethod
    def check_stock_availability(cart_items, company_id):
        """Verificar disponibilidad de stock para los items"""
        stock_issues = []
        
        for item in cart_items:
            inventory_item = InventoryItem.query.filter_by(
                id=item['id'],
                company_id=company_id
            ).first()
            
            if not inventory_item:
                stock_issues.append(f"Item {item.get('name', 'desconocido')} no encontrado")
                continue
            
            if inventory_item.quantity < item['quantity']:
                stock_issues.append(
                    f"Stock insuficiente para {inventory_item.name}. "
                    f"Disponible: {inventory_item.quantity}, Solicitado: {item['quantity']}"
                )
        
        return stock_issues

    @staticmethod
    def validate_payment_totals(cart_items, payment_methods):
        """Validar que los totales de pago coincidan"""
        # Calcular total del carrito
        cart_total = sum([item['price'] * item['quantity'] for item in cart_items])
        tax_amount = cart_total * 0.19
        total_with_tax = cart_total + tax_amount
        
        # Calcular total de pagos
        payment_total = sum([float(p['amount']) for p in payment_methods])
        
        # Tolerancia de centavos
        if abs(total_with_tax - payment_total) > 0.01:
            raise ValueError(
                f"El total de pagos (${payment_total:.2f}) no coincide con el total de la venta (${total_with_tax:.2f})"
            )
        
        return total_with_tax, tax_amount

    @staticmethod
    def get_current_cash_session(company_id):
        """Obtener sesión de caja actual si existe"""
        today = datetime.utcnow().date()
        return CashSession.query.filter_by(
            company_id=company_id,
            session_date=today,
            status='open'
        ).first()

    @staticmethod
    def process_offline_sale(sale_uuid, sale_data, company_id, user_id, timestamp):
        """
        Procesar una venta offline y sincronizarla con la base de datos
        
        Args:
            sale_uuid (str): UUID único de la venta offline
            sale_data (dict): Datos de la venta
            company_id (int): ID de la empresa
            user_id (int): ID del usuario
            timestamp (str): Timestamp de cuando se creó la venta offline
        
        Returns:
            dict: Resultado del procesamiento
        """
        try:
            # 1. Validar datos de entrada
            POSSyncService.validate_sale_data(sale_data, company_id, user_id)
            
            # 2. Verificar stock disponible
            stock_issues = POSSyncService.check_stock_availability(sale_data['cart_items'], company_id)
            if stock_issues:
                return {
                    'success': False,
                    'error': f"Problemas de stock: {'; '.join(stock_issues)}",
                    'type': 'stock_error'
                }
            
            # 3. Validar totales de pago
            total_amount, tax_amount = POSSyncService.validate_payment_totals(
                sale_data['cart_items'], 
                sale_data['payment_methods']
            )
            
            # 4. Verificar si ya existe una venta con este UUID
            existing_sale = Sale.query.filter_by(offline_uuid=sale_uuid).first()
            if existing_sale:
                return {
                    'success': True,
                    'sale_number': existing_sale.sale_number,
                    'message': f'Venta ya sincronizada: {existing_sale.sale_number}',
                    'duplicate': True
                }
            
            # 5. Crear venta
            sale = Sale(
                sale_number=Sale.generate_sale_number(company_id),
                total_amount=total_amount,
                tax_amount=tax_amount,
                company_id=company_id,
                user_id=user_id,
                status='completada',
                notes=sale_data.get('notes', '') + f" [Sincronizada desde offline: {sale_uuid[:8]}...]",
                offline_uuid=sale_uuid,
                offline_timestamp=datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            )
            
            # 6. Agregar items de venta
            for cart_item in sale_data['cart_items']:
                inventory_item = InventoryItem.query.filter_by(
                    id=cart_item['id'],
                    company_id=company_id
                ).first()
                
                if inventory_item:
                    sale_item = SaleItem(
                        quantity=cart_item['quantity'],
                        unit_price=cart_item['price'],
                        total_price=cart_item['price'] * cart_item['quantity'],
                        inventory_item_id=inventory_item.id
                    )
                    sale.items.append(sale_item)
                    
                    # Actualizar inventario
                    inventory_item.quantity -= cart_item['quantity']
            
            # 7. Agregar detalles de pago
            for payment in sale_data['payment_methods']:
                payment_detail = PaymentDetail(
                    payment_method=payment['method'],
                    amount=payment['amount'],
                    reference=payment.get('reference', ''),
                    notes=payment.get('notes', '')
                )
                sale.payment_details.append(payment_detail)
            
            # 8. Asociar a sesión de caja si está abierta
            current_session = POSSyncService.get_current_cash_session(company_id)
            if current_session:
                sale.cash_session_id = current_session.id
                current_session.total_sales += float(sale.total_amount)
            
            # 9. Guardar en base de datos
            db.session.add(sale)
            db.session.commit()
            
            current_app.logger.info(f"Venta offline sincronizada: {sale.sale_number} (UUID: {sale_uuid})")
            
            return {
                'success': True,
                'sale_number': sale.sale_number,
                'total': float(sale.total_amount),
                'message': f'Venta {sale.sale_number} sincronizada exitosamente',
                'duplicate': False
            }
            
        except ValueError as e:
            current_app.logger.warning(f"Error de validación en venta offline {sale_uuid}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'type': 'validation_error'
            }
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error de base de datos sincronizando venta offline {sale_uuid}: {str(e)}")
            return {
                'success': False,
                'error': 'Error de base de datos. Reintente más tarde.',
                'type': 'database_error'
            }
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error general sincronizando venta offline {sale_uuid}: {str(e)}")
            return {
                'success': False,
                'error': f'Error interno del servidor: {str(e)}',
                'type': 'internal_error'
            }

    @staticmethod
    def create_offline_sync_record(sale_data, company_id, user_id):
        """Crear registro de sincronización offline para backup"""
        try:
            offline_sync = OfflineSync(
                sale_data=sale_data,
                company_id=company_id,
                user_id=user_id,
                sync_status='pending'
            )
            db.session.add(offline_sync)
            db.session.commit()
            
            return offline_sync.id
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creando registro offline sync: {str(e)}")
            return None

    @staticmethod
    def get_pending_offline_syncs(company_id):
        """Obtener sincronizaciones pendientes para una empresa"""
        return OfflineSync.query.filter_by(
            company_id=company_id,
            sync_status='pending'
        ).order_by(OfflineSync.created_at.asc()).all()

    @staticmethod
    def mark_offline_sync_completed(sync_id, sale_number):
        """Marcar sincronización offline como completada"""
        try:
            offline_sync = OfflineSync.query.get(sync_id)
            if offline_sync:
                offline_sync.sync_status = 'synced'
                offline_sync.synced_at = datetime.utcnow()
                offline_sync.sale_data['sale_number'] = sale_number  # Agregar número de venta
                db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error marcando sync como completado: {str(e)}")