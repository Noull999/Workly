# Workly

## Descripción General

Sistema de gestión empresarial modular "Workly" basado en web construido con Flask. Es una plataforma integral de productividad empresarial que combina gestión de inventario, punto de venta, sistema de citas, workspace colaborativo estilo Notion, gestión ágil de proyectos y páginas de presentación. La aplicación proporciona un sistema multiempresa completo con módulos activables según las necesidades específicas de cada organización. Incluye control avanzado de roles, colaboración en tiempo real, y personalización completa por empresa.

## User Preferences

- Preferred communication style: Simple, everyday language
- Application must be fully localized in Spanish for Chilean company use
- Remove price/value fields from all models, forms, and templates as they are not needed
- Complete category system for organizing inventory items
- Application name changed to "Workly" throughout the system
- Business model: Enterprise productivity platform with modular activation
- Professional access control: Multi-tenant system with comprehensive role management
- Modular system: 6 core modules - Inventory, POS, Appointments, Notion Workspace, Scrum Agile, and Portfolio
- Advanced features: Real-time collaboration, rich text editing, file management, kanban boards, project tracking
- Public pages: Company portfolio and booking system accessible without login when modules are active
- Color scheme: Purple background with orange text for modern, professional appearance

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
- **Flask-Migrate**: Database migration management for PostgreSQL
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
  - **Dynamic User Profiles**: JSON-driven profile system with `/perfil/<email>` route for streamer/creator pages
  - **Modern Gaming Design**: Tailwind CSS + GSAP animations for professional gaming/streaming profiles
  - **Customizable Branding**: Per-user colors, metrics, schedules, and social media links from JSON
  - **File**: `user_data.json` contains array of users with email, name, photo, social links, viewer metrics, schedules
  - **Featured Clips System**: Database-driven clip destacado with custom thumbnails (is_featured, featured_thumbnail_url fields in Clip model)
  - **Contact Integration**: WhatsApp business contact button (more reliable than mailto links in iframe environments)
  - **Casino/Sponsor Links**: Support for casino URLs in user JSON for sponsor/affiliate buttons
  - **Visual Consistency**: Orange-purple gradient theme throughout profile pages (logo border, text gradients)

### Database Support
- **PostgreSQL**: Primary database system with Flask-Migrate for schema management
- **Database migrations**: Automatic schema updates using Flask-Migrate and Alembic
- **Database URL**: Environment variable configuration for production databases
- **Multi-tenant isolation**: Company-based data segregation across all modules
- **Extended models**: Service, Sale, Appointment, SaleItem tables for module functionality
- **Migration commands**: `flask db migrate` and `flask db upgrade` for schema changes

### Advanced POS System (Recently Completed)
- **Cash Management**: Daily cash session control with opening/closing procedures
- **Multiple Payment Methods**: Support for mixed payments (cash, card, transfer, vouchers)
- **Barcode Scanning**: Frontend barcode reader integration for quick product lookup
- **Offline Mode**: Local storage with automatic synchronization when connection restored
- **Advanced Models**: CashSession, PaymentDetail, CashExpense, OfflineSync for comprehensive POS operations
- **Daily Reporting**: Automated daily reports with performance metrics and recommendations
- **Real-time Updates**: Live connection status and offline queue management

### Dashboard Analytics (October 2025)
- **Chart.js Integration**: Added Chart.js library for data visualization
- **Sales Trends Graph**: Line chart showing daily sales for the last 7 days with purple/orange theme
- **Low Stock Alert Chart**: Bar chart displaying top 5 products with low inventory levels
- **Task Distribution Chart**: Doughnut chart showing task breakdown by status (To Do, In Progress, Done)
- **Dynamic Data**: Backend queries provide real-time data for all charts
- **Responsive Design**: All charts adapt to screen size with proper color theming

### Stripe Connect Integration (October 2025)
- **Multi-tenant Payment Processing**: Each company connects its own Stripe Express account
- **Zero fees when inactive**: Only charged when processing transactions ($2/month when active)
- **Secure Webhook Validation**: All webhook events validated with signature verification
- **Payment Intent API**: Endpoint for creating payment intents with idempotency support
- **Database Fields**: Company model tracks stripe_account_id, onboarding status, charges/payouts enabled
- **PaymentDetail Enhancement**: Tracks stripe_payment_intent_id and stripe_charge_id for reconciliation
- **Onboarding Flow**: Automated Account Link generation for Express account setup
- **Dashboard Access**: Direct login links to Stripe Express dashboard for account management
- **Event Handling**: Webhooks process account.updated, payment_intent.succeeded, charge.succeeded events
- **Security**: STRIPE_WEBHOOK_SECRET required for production webhook validation

### Deployment Infrastructure
- **ProxyFix**: WSGI middleware for handling proxy headers
- **Environment variables**: Configuration management for secrets and database URLs
- **Logging**: Python standard logging for debugging and monitoring
- **Public routing**: External access for portfolio and booking pages

### Development Tools
- **Debug mode**: Flask development server with auto-reload
- **Template debugging**: Jinja2 error reporting and debugging
- **SQL logging**: SQLAlchemy query logging for development