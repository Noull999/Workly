import os
import mercadopago
from flask import render_template, redirect, url_for, request, jsonify, flash, session
from flask_login import login_required, current_user
from app import db
from models import Company, PaymentDetail
from . import mercadopago_bp
from datetime import datetime, timedelta
import hmac
import hashlib
import json
import secrets

@mercadopago_bp.route('/setup')
@login_required
def setup():
    """Página de configuración de Mercado Pago"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    company = current_user.company
    
    # Verificar si POS está activado
    if not company.module_pos:
        flash('El módulo POS debe estar activado para configurar Mercado Pago.', 'warning')
        return redirect(url_for('dashboard'))
    
    return render_template('mercadopago/setup.html', company=company)

@mercadopago_bp.route('/connect')
@login_required
def connect():
    """Iniciar flujo OAuth de Mercado Pago"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        return jsonify({'error': 'No autorizado'}), 403
    
    # Generar state aleatorio y seguro
    oauth_state = secrets.token_urlsafe(32)
    
    # Guardar state en sesión junto con company_id para validación posterior
    session['mp_oauth_state'] = oauth_state
    session['mp_oauth_company_id'] = current_user.company_id
    session['mp_oauth_user_id'] = current_user.id
    
    # Construir URL de autorización de Mercado Pago
    client_id = os.environ.get('MP_CLIENT_ID')
    redirect_uri = request.url_root.rstrip('/') + url_for('mercadopago.callback')
    
    auth_url = f"https://auth.mercadopago.cl/authorization?client_id={client_id}&response_type=code&platform_id=mp&redirect_uri={redirect_uri}&state={oauth_state}"
    
    return redirect(auth_url)

def _clear_oauth_session():
    """Helper para limpiar datos de sesión OAuth de forma segura"""
    session.pop('mp_oauth_state', None)
    session.pop('mp_oauth_company_id', None)
    session.pop('mp_oauth_user_id', None)

@mercadopago_bp.route('/callback')
@login_required
def callback():
    """Callback OAuth de Mercado Pago - SEGURO con validación de state"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            flash(f'Error al conectar con Mercado Pago: {error}', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        if not code or not state:
            flash('Parámetros inválidos en la respuesta de Mercado Pago.', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        # SEGURIDAD: Validar state contra el guardado en sesión
        saved_state = session.get('mp_oauth_state')
        saved_company_id = session.get('mp_oauth_company_id')
        saved_user_id = session.get('mp_oauth_user_id')
        
        if not saved_state or state != saved_state:
            flash('Estado de OAuth inválido. Por seguridad, intenta conectar nuevamente.', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        # Verificar que el usuario actual coincide con quien inició el flujo
        if current_user.id != saved_user_id:
            flash('No autorizado. Debes ser el mismo usuario que inició la conexión.', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        # Verificar que el usuario puede modificar la empresa
        if current_user.company_id != saved_company_id:
            flash('No autorizado para esta empresa.', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        company = current_user.company
        
        if not company:
            flash('Empresa no encontrada.', 'danger')
            return redirect(url_for('mercadopago.setup'))
        
        # Preparar datos para intercambio de token (FORM-ENCODED, no JSON)
        token_data = {
            'client_id': os.environ.get('MP_CLIENT_ID'),
            'client_secret': os.environ.get('MP_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': request.url_root.rstrip('/') + url_for('mercadopago.callback')
        }
        
        # Realizar solicitud para obtener token con Content-Type correcto
        import requests
        response = requests.post(
            'https://api.mercadopago.com/oauth/token',
            data=token_data,  # usar 'data' en lugar de 'json' para form-encoded
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code == 200:
            token_response = response.json()
            
            # Guardar tokens en la empresa
            company.mp_access_token = token_response.get('access_token')
            company.mp_refresh_token = token_response.get('refresh_token')
            company.mp_public_key = token_response.get('public_key')
            company.mp_user_id = token_response.get('user_id')
            company.mp_onboarding_complete = True
            
            # Calcular fecha de expiración
            expires_in = token_response.get('expires_in', 15552000)  # Default 180 días
            company.mp_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            db.session.commit()
            
            flash('¡Mercado Pago conectado exitosamente!', 'success')
        else:
            error_msg = response.text
            try:
                error_json = response.json()
                error_msg = error_json.get('message', error_msg)
            except:
                pass
            flash(f'Error al obtener token de Mercado Pago: {error_msg}', 'danger')
    
    except Exception as e:
        flash(f'Error al procesar callback de Mercado Pago: {str(e)}', 'danger')
    
    finally:
        # CRÍTICO: Limpiar sesión OAuth en TODOS los casos (éxito, error, excepción)
        _clear_oauth_session()
    
    return redirect(url_for('mercadopago.setup'))

@mercadopago_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Desconectar cuenta de Mercado Pago"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        return jsonify({'error': 'No autorizado'}), 403
    
    company = current_user.company
    
    # Limpiar credenciales de Mercado Pago
    company.mp_access_token = None
    company.mp_refresh_token = None
    company.mp_public_key = None
    company.mp_user_id = None
    company.mp_onboarding_complete = False
    company.mp_token_expires_at = None
    
    db.session.commit()
    
    flash('Cuenta de Mercado Pago desconectada.', 'info')
    return redirect(url_for('mercadopago.setup'))

@mercadopago_bp.route('/create-payment-preference', methods=['POST'])
@login_required
def create_payment_preference():
    """Crear preferencia de pago para Checkout Pro"""
    try:
        data = request.get_json()
        
        company = current_user.company
        
        if not company.mp_access_token:
            return jsonify({'error': 'Mercado Pago no está configurado'}), 400
        
        # Inicializar SDK con token de la empresa
        sdk = mercadopago.SDK(company.mp_access_token)
        
        # Crear preferencia de pago
        preference_data = {
            "items": data.get('items', []),
            "payer": {
                "email": data.get('payer_email', company.company_email)
            },
            "back_urls": {
                "success": request.url_root.rstrip('/') + url_for('pos.index'),
                "failure": request.url_root.rstrip('/') + url_for('pos.index'),
                "pending": request.url_root.rstrip('/') + url_for('pos.index')
            },
            "notification_url": request.url_root.rstrip('/') + url_for('mercadopago.webhook'),
            "external_reference": data.get('sale_id', ''),
            "metadata": {
                "company_id": company.id,
                "sale_id": data.get('sale_id', '')
            }
        }
        
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        return jsonify({
            'preference_id': preference['id'],
            'init_point': preference['init_point'],
            'sandbox_init_point': preference.get('sandbox_init_point', '')
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@mercadopago_bp.route('/webhook', methods=['POST'])
def webhook():
    """Webhook para notificaciones de Mercado Pago"""
    try:
        # Obtener datos del webhook
        data = request.get_json()
        
        # Log para debugging
        print(f"Mercado Pago Webhook received: {json.dumps(data, indent=2)}")
        
        # Validar firma del webhook (si Mercado Pago la proporciona)
        # Nota: Mercado Pago usa un enfoque diferente a Stripe para validación
        
        notification_type = data.get('type')
        
        if notification_type == 'payment':
            payment_id = data.get('data', {}).get('id')
            
            if payment_id:
                # Aquí procesarías el pago
                # Por ahora solo logueamos
                print(f"Payment notification received: {payment_id}")
        
        return jsonify({'status': 'ok'}), 200
    
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@mercadopago_bp.route('/payment-status/<payment_id>')
@login_required
def payment_status(payment_id):
    """Consultar estado de un pago"""
    try:
        company = current_user.company
        
        if not company.mp_access_token:
            return jsonify({'error': 'Mercado Pago no configurado'}), 400
        
        sdk = mercadopago.SDK(company.mp_access_token)
        payment_response = sdk.payment().get(payment_id)
        payment = payment_response["response"]
        
        return jsonify({
            'status': payment.get('status'),
            'status_detail': payment.get('status_detail'),
            'transaction_amount': payment.get('transaction_amount'),
            'payment_method_id': payment.get('payment_method_id')
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
