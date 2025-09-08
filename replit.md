# Inventario INTAC

## Descripción General

Sistema de gestión empresarial modular "Inventario INTAC" basado en web construido con Flask. Es una solución de pago para empresas que requiere contacto directo con el desarrollador para obtener acceso. La aplicación proporciona un sistema integral multiempresa con inventario base y módulos opcionales: POS (Punto de Venta), Sistema de Citas/Reservas (con página pública), y Página de Presentación personalizable. Incluye control de roles, branding personalizado por empresa, y activación modular según necesidades del cliente. Sistema comercial sin registro público disponible.

## User Preferences

- Preferred communication style: Simple, everyday language
- Application must be fully localized in Spanish for Chilean company use
- Remove price/value fields from all models, forms, and templates as they are not needed
- Complete category system for organizing inventory items
- Application name changed to "Inventario INTAC" throughout the system
- Business model: Paid service - no public registration allowed, users must contact developer for access
- Professional access control: Only authorized users can access the system through provided credentials
- Modular system: Inventory base + optional POS, Appointments, and Portfolio modules per company
- Public pages: Company portfolio and booking system accessible without login when modules are active

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

### Modular System Architecture
- **Company-based modules**: Each enterprise can activate specific business modules
- **Module control**: Super admin can enable/disable modules per company
- **Dynamic navigation**: UI adapts to show only active modules for each company
- **Public pages**: External-facing portfolio and booking pages when modules are active

#### Available Modules
- **POS Module**: Point-of-sale system integrated with inventory for retail operations
- **Appointments Module**: Service management with public booking pages for clients
- **Portfolio Module**: Public-facing company presentation pages with contact forms

### Database Support
- **SQLite**: Default embedded database (configurable)
- **Database URL**: Environment variable configuration for production databases
- **Multi-tenant isolation**: Company-based data segregation across all modules
- **Extended models**: Service, Sale, Appointment, SaleItem tables for module functionality

### Advanced POS System (Recently Completed)
- **Cash Management**: Daily cash session control with opening/closing procedures
- **Multiple Payment Methods**: Support for mixed payments (cash, card, transfer, vouchers)
- **Barcode Scanning**: Frontend barcode reader integration for quick product lookup
- **Offline Mode**: Local storage with automatic synchronization when connection restored
- **Advanced Models**: CashSession, PaymentDetail, CashExpense, OfflineSync for comprehensive POS operations
- **Daily Reporting**: Automated daily reports with performance metrics and recommendations
- **Real-time Updates**: Live connection status and offline queue management

### Deployment Infrastructure
- **ProxyFix**: WSGI middleware for handling proxy headers
- **Environment variables**: Configuration management for secrets and database URLs
- **Logging**: Python standard logging for debugging and monitoring
- **Public routing**: External access for portfolio and booking pages

### Development Tools
- **Debug mode**: Flask development server with auto-reload
- **Template debugging**: Jinja2 error reporting and debugging
- **SQL logging**: SQLAlchemy query logging for development