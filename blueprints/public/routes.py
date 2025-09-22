from flask import render_template, redirect, url_for, flash, request
from datetime import datetime
from . import public
from models import Company, Service, Appointment
from forms import PublicAppointmentForm
from app import db

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
        appointment = Appointment(
            client_name=form.client_name.data,
            client_phone=form.client_phone.data,
            client_email=form.client_email.data,
            appointment_date=form.appointment_date.data,
            service_id=form.service_id.data,
            notes=form.notes.data,
            is_public=True,
            company_id=company.id,
            status='pendiente'
        )
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