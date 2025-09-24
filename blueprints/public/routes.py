from flask import render_template, redirect, url_for, flash, request
from datetime import datetime
from . import public
from models import Company, Service, Appointment, User, PublicPage
from forms import PublicAppointmentForm
from app import db
import json

@public.route('/empresa/<company_code>')
def portfolio(company_code):
    """Página pública de presentación de empresa"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_portfolio:
        return render_template('errors/module_disabled.html'), 404
    
    # URL de reserva si tiene módulo de citas activo
    booking_url = None
    if company.module_appointments:
        booking_url = url_for('public.booking', company_code=company.code)
    
    return render_template('public/portfolio.html', company=company, booking_url=booking_url, current_year=datetime.now().year)

@public.route('/empresa/<company_code>/reservar', methods=['GET', 'POST'])
def booking(company_code):
    """Página pública para reservar citas"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    
    if not company.module_appointments:
        return render_template('errors/module_disabled.html'), 404
    
    form = PublicAppointmentForm()
    
    # Cargar servicios activos
    services = Service.query.filter_by(company_id=company.id, is_active=True).all()
    form.service_id.choices = [(s.id, f"{s.name} ({s.duration_minutes} min)") for s in services]
    
    if form.validate_on_submit():
        appointment = Appointment()
        appointment.client_name = form.client_name.data
        appointment.client_phone = form.client_phone.data
        appointment.client_email = form.client_email.data
        appointment.appointment_date = form.appointment_date.data
        appointment.service_id = form.service_id.data
        appointment.notes = form.notes.data
        appointment.is_public = True
        appointment.company_id = company.id
        appointment.status = 'pendiente'
        db.session.add(appointment)
        db.session.commit()
        
        flash('¡Reserva realizada exitosamente! Te contactaremos pronto para confirmar.', 'success')
        return redirect(url_for('public.booking_confirmation', company_code=company.code, appointment_id=appointment.id))
    
    return render_template('public/booking.html', company=company, form=form, services=services)

@public.route('/empresa/<company_code>/reserva/<int:appointment_id>/confirmacion')
def booking_confirmation(company_code, appointment_id):
    """Confirmación de reserva"""
    company = Company.query.filter_by(code=company_code, is_active=True).first_or_404()
    appointment = Appointment.query.filter_by(id=appointment_id, company_id=company.id).first_or_404()
    
    return render_template('public/booking_confirmation.html', 
                         company=company, appointment=appointment)

@public.route('/yanglee')
def yanglee_page():
    """Página pública personalizada de Yanglee"""
    # Buscar usuario Yanglee
    user = User.query.filter_by(email='yangprroo@gmail.com').first_or_404()
    
    # Buscar su página pública
    public_page = PublicPage.query.filter_by(user_id=user.id).first()
    
    if not public_page:
        # Si no existe, crear una página por defecto
        public_page = PublicPage()
        public_page.user_id = user.id
        public_page.title = "Página oficial de Yanglee"
        public_page.description = "Bienvenido a mi página personal. Aquí encontrarás contenido exclusivo y novedades."
        public_page.primary_color = "#ff6600"
        public_page.secondary_color = "#1a1a1a"
        public_page.background_type = "gradient"
        public_page.background_value = "linear-gradient(135deg, #1a1a1a 0%, #2c2c2c 100%)"
        public_page.social_links = json.dumps({
            "twitch": "https://twitch.tv/yanglee",
            "youtube": "https://youtube.com/@yanglee",
            "twitter": "https://twitter.com/yanglee",
            "instagram": "https://instagram.com/yanglee"
        })
        public_page.sections = json.dumps({
            "bio": True,
            "clips": True,
            "gallery": True,
            "contact": True
        })
        db.session.add(public_page)
        db.session.commit()
    
    # Procesar JSON para el template
    social_links = {}
    sections = {}
    
    try:
        if public_page.social_links:
            social_links = json.loads(public_page.social_links)
    except:
        social_links = {}
    
    try:
        if public_page.sections:
            sections = json.loads(public_page.sections)
    except:
        sections = {}
    
    return render_template('public/public_page.html', 
                         user=user, 
                         page=public_page,
                         social_links=social_links,
                         sections=sections)