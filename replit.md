# Inventario INTAC

## Descripción General

Sistema de gestión de inventario empresarial "Inventario INTAC" basado en web construido con Flask. Es una solución de pago para empresas que requiere contacto directo con el desarrollador para obtener acceso. La aplicación proporciona seguimiento integral del inventario multiempresa con características para gestión de artículos, categorización, monitoreo de niveles de stock, reportes, control de roles y branding personalizado. Sistema comercial sin registro público disponible.

## User Preferences

- Preferred communication style: Simple, everyday language
- Application must be fully localized in Spanish for Chilean company use
- Remove price/value fields from all models, forms, and templates as they are not needed
- Complete category system for organizing inventory items
- Application name changed to "Inventario INTAC" throughout the system
- Business model: Paid service - no public registration allowed, users must contact developer for access
- Professional access control: Only authorized users can access the system through provided credentials

## System Architecture

### Web Framework
- **Flask**: Python web framework chosen for its simplicity and flexibility
- **Flask-SQLAlchemy**: ORM for database operations, providing clean abstraction over raw SQL
- **Flask-Login**: User session management and authentication handling
- **Flask-WTF**: Form handling and CSRF protection with WTForms integration

### Database Architecture
- **SQLAlchemy ORM**: Database abstraction layer with declarative models
- **SQLite default**: Lightweight database for development, configurable via DATABASE_URL environment variable
- **Connection pooling**: Configured with pool recycling and pre-ping for reliability

### Data Models
- **User**: Authentication and ownership model with password hashing
- **Category**: Item categorization system with optional descriptions
- **InventoryItem**: Core inventory tracking with quantity, pricing, and stock alerts
- **Relationships**: One-to-many relationships between users/items and categories/items

### Authentication System
- **Flask-Login**: Session-based authentication with secure user loading
- **Werkzeug security**: Password hashing and verification using industry standards
- **User registration**: Email and username uniqueness validation
- **Login protection**: Route protection for authenticated access only

### Frontend Architecture
- **Jinja2 templating**: Server-side rendering with template inheritance
- **Bootstrap 5**: Responsive UI framework with dark theme
- **Font Awesome**: Icon library for enhanced visual interface
- **Progressive enhancement**: JavaScript layer for improved user experience

### Form Management
- **WTForms validation**: Server-side form validation with field-specific rules
- **CSRF protection**: Built-in cross-site request forgery protection
- **Dynamic choices**: Category dropdown population from database
- **Input sanitization**: Automatic data cleaning and validation

### Security Features
- **Session management**: Secure session handling with configurable secret keys
- **Password security**: Salted password hashing with Werkzeug
- **Input validation**: Comprehensive form validation and sanitization
- **User isolation**: Data segregation ensuring users only access their own inventory

## External Dependencies

### Core Framework Dependencies
- **Flask**: Web application framework
- **Flask-SQLAlchemy**: Database ORM integration
- **Flask-Login**: User authentication and session management
- **Flask-WTF**: Form handling and CSRF protection
- **WTForms**: Form field validation and rendering
- **Werkzeug**: WSGI utilities and security helpers

### Frontend Dependencies
- **Bootstrap 5**: CSS framework loaded via CDN (bootstrap-agent-dark-theme)
- **Font Awesome 6**: Icon library loaded via CDN
- **JavaScript**: Vanilla JS for enhanced interactivity

### Database Support
- **SQLite**: Default embedded database (configurable)
- **Database URL**: Environment variable configuration for production databases

### Deployment Infrastructure
- **ProxyFix**: WSGI middleware for handling proxy headers
- **Environment variables**: Configuration management for secrets and database URLs
- **Logging**: Python standard logging for debugging and monitoring

### Development Tools
- **Debug mode**: Flask development server with auto-reload
- **Template debugging**: Jinja2 error reporting and debugging
- **SQL logging**: SQLAlchemy query logging for development