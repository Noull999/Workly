from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from . import appointments
from ..decorators import module_required, admin_required
from models import Service, Appointment, Company
from forms import ServiceForm, AppointmentForm, PortfolioForm
from utils import company_query, log_audit
from app import db

@appointments.route('/services', methods=['GET', 'POST'])
@login_required
@module_required('appointments')
def manage_services():
    """Gestionar servicios para citas"""
    form = ServiceForm()
    if form.validate_on_submit():
        service = Service(
            name=form.name.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            price=form.price.data,
            is_active=form.is_active.data,
            company_id=current_user.company_id
        )
        db.session.add(service)
        db.session.commit()
        flash(f'Servicio "{service.name}" agregado exitosamente!', 'success')
        return redirect(url_for('appointments.manage_services'))
    
    services = company_query(Service).all()
    return render_template('modules/services.html', form=form, services=services)

@appointments.route('/', methods=['GET', 'POST'])
@login_required
@module_required('appointments')
def manage_appointments():
    """Gestionar citas"""
    form = AppointmentForm()
    if form.validate_on_submit():
        appointment = Appointment(
            client_name=form.client_name.data,
            client_phone=form.client_phone.data,
            client_email=form.client_email.data,
            appointment_date=form.appointment_date.data,
            service_id=form.service_id.data,
            status=form.status.data,
            notes=form.notes.data,
            is_public=False,
            company_id=current_user.company_id,
            user_id=current_user.id
        )
        db.session.add(appointment)
        db.session.commit()
        flash(f'Cita para {appointment.client_name} agendada exitosamente!', 'success')
        return redirect(url_for('appointments.manage_appointments'))
    
    appointments_list = company_query(Appointment).order_by(Appointment.appointment_date.desc()).all()
    
    # URL de la página pública de reservas
    booking_url = url_for('public.booking', company_code=current_user.company.code, _external=True)
    
    return render_template('modules/appointments.html', 
                         form=form, appointments=appointments_list, booking_url=booking_url)

@appointments.route('/service/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
@module_required('appointments')
def edit_service(service_id):
    """Editar servicio"""
    service = company_query(Service).filter_by(id=service_id).first_or_404()
    form = ServiceForm(obj=service)
    
    if form.validate_on_submit():
        service.name = form.name.data
        service.description = form.description.data
        service.duration_minutes = form.duration_minutes.data
        service.price = form.price.data
        service.is_active = form.is_active.data
        
        db.session.commit()
        log_audit('appointments', f'Servicio editado: {service.name}', current_user.id, current_user.company_id)
        flash(f'Servicio "{service.name}" actualizado exitosamente!', 'success')
        return redirect(url_for('appointments.manage_services'))
    
    services = company_query(Service).all()
    return render_template('modules/services.html', form=form, services=services, edit_service=service)

@appointments.route('/service/delete/<int:service_id>', methods=['POST'])
@login_required
@module_required('appointments')
@admin_required
def delete_service(service_id):
    """Eliminar servicio"""
    service = company_query(Service).filter_by(id=service_id).first_or_404()
    service_name = service.name
    
    db.session.delete(service)
    db.session.commit()
    
    log_audit('appointments', f'Servicio eliminado: {service_name}', current_user.id, current_user.company_id)
    flash(f'Servicio "{service_name}" eliminado exitosamente!', 'success')
    return redirect(url_for('appointments.manage_services'))