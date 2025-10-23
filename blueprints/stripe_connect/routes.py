import os
import stripe
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from models import Company
from . import stripe_bp

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

@stripe_bp.route('/setup')
@login_required
def setup():
    """Página de configuración de Stripe Connect"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    if not current_user.company.module_pos:
        flash('El módulo POS debe estar activo para usar Stripe.', 'warning')
        return redirect(url_for('dashboard'))
    
    company = current_user.company
    
    # Verificar si ya tiene cuenta conectada
    if company.stripe_account_id:
        try:
            # Obtener información actualizada de la cuenta
            account = stripe.Account.retrieve(company.stripe_account_id)
            
            # Actualizar estado en BD
            company.stripe_charges_enabled = account.charges_enabled
            company.stripe_payouts_enabled = account.payouts_enabled
            company.stripe_details_submitted = account.details_submitted
            company.stripe_onboarding_complete = (
                account.charges_enabled and 
                account.payouts_enabled and 
                account.details_submitted
            )
            db.session.commit()
            
            return render_template('stripe/setup.html', 
                                 company=company, 
                                 account=account)
        except stripe.error.StripeError as e:
            flash(f'Error al conectar con Stripe: {str(e)}', 'danger')
            return render_template('stripe/setup.html', company=company, account=None)
    
    return render_template('stripe/setup.html', company=company, account=None)

@stripe_bp.route('/connect', methods=['POST'])
@login_required
def connect():
    """Crear cuenta de Stripe Connect Express y redirigir al onboarding"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        flash('No tienes permisos para esta acción.', 'danger')
        return redirect(url_for('stripe.setup'))
    
    company = current_user.company
    
    try:
        # Crear cuenta Express si no existe
        if not company.stripe_account_id:
            account = stripe.Account.create(
                type='express',
                country='CL',  # Chile
                email=company.contact_email or company.company_email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                },
                business_type='company',
                metadata={
                    'company_id': str(company.id),
                    'company_name': company.name,
                }
            )
            
            company.stripe_account_id = account.id
            db.session.commit()
        
        # Crear Account Link para onboarding
        domain = os.environ.get('REPLIT_DEV_DOMAIN', 'localhost:5000')
        if os.environ.get('REPLIT_DEPLOYMENT') == '1':
            base_url = f'https://{domain}'
        else:
            base_url = f'https://{domain}'
        
        account_link = stripe.AccountLink.create(
            account=company.stripe_account_id,
            refresh_url=f'{base_url}/stripe/setup',
            return_url=f'{base_url}/stripe/setup',
            type='account_onboarding',
        )
        
        return redirect(account_link.url)
        
    except stripe.error.StripeError as e:
        flash(f'Error al conectar con Stripe: {str(e)}', 'danger')
        return redirect(url_for('stripe.setup'))

@stripe_bp.route('/dashboard')
@login_required
def dashboard():
    """Generar link al dashboard de Stripe Express"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        flash('No tienes permisos para esta acción.', 'danger')
        return redirect(url_for('stripe.setup'))
    
    company = current_user.company
    
    if not company.stripe_account_id:
        flash('Primero debes conectar tu cuenta de Stripe.', 'warning')
        return redirect(url_for('stripe.setup'))
    
    try:
        # Crear login link para el dashboard Express
        login_link = stripe.Account.create_login_link(company.stripe_account_id)
        return redirect(login_link.url)
        
    except stripe.error.StripeError as e:
        flash(f'Error al acceder al dashboard: {str(e)}', 'danger')
        return redirect(url_for('stripe.setup'))

@stripe_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Desconectar cuenta de Stripe"""
    if not current_user.is_admin_empresa() and not current_user.is_admin_global():
        flash('No tienes permisos para esta acción.', 'danger')
        return redirect(url_for('stripe.setup'))
    
    company = current_user.company
    
    if not company.stripe_account_id:
        flash('No hay cuenta conectada para desconectar.', 'warning')
        return redirect(url_for('stripe.setup'))
    
    try:
        # Eliminar la cuenta (esto NO elimina la cuenta de Stripe, solo la desconecta)
        # Para eliminar completamente usar: stripe.Account.delete(company.stripe_account_id)
        
        # Solo desconectamos limpiando los datos locales
        company.stripe_account_id = None
        company.stripe_onboarding_complete = False
        company.stripe_charges_enabled = False
        company.stripe_payouts_enabled = False
        company.stripe_details_submitted = False
        db.session.commit()
        
        flash('Cuenta de Stripe desconectada exitosamente.', 'success')
        
    except Exception as e:
        flash(f'Error al desconectar: {str(e)}', 'danger')
    
    return redirect(url_for('stripe.setup'))

@stripe_bp.route('/webhook', methods=['POST'])
def webhook():
    """Webhook para recibir eventos de Stripe"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    # En producción, debes configurar STRIPE_WEBHOOK_SECRET
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            # Modo desarrollo sin verificación (NO usar en producción)
            event = stripe.Event.construct_from(
                request.get_json(), stripe.api_key
            )
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Manejar eventos
    if event['type'] == 'account.updated':
        account = event['data']['object']
        
        # Buscar empresa por stripe_account_id
        company = Company.query.filter_by(stripe_account_id=account['id']).first()
        if company:
            company.stripe_charges_enabled = account.get('charges_enabled', False)
            company.stripe_payouts_enabled = account.get('payouts_enabled', False)
            company.stripe_details_submitted = account.get('details_submitted', False)
            company.stripe_onboarding_complete = (
                account.get('charges_enabled', False) and 
                account.get('payouts_enabled', False) and 
                account.get('details_submitted', False)
            )
            db.session.commit()
    
    elif event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        # Aquí puedes actualizar el estado de la venta si es necesario
        # Los metadatos deben incluir sale_id para vincular
        pass
    
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        # Manejar pago fallido
        pass
    
    return jsonify({'status': 'success'}), 200
