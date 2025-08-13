// Main JavaScript file for Inventory Management System

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-hide flash messages after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Search functionality with debounce
    const searchInput = document.getElementById('search');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {
                // Auto-submit search form after 500ms of no typing
                if (searchInput.value.length >= 3 || searchInput.value.length === 0) {
                    searchInput.closest('form').submit();
                }
            }, 500);
        });
    }

    // Form validation enhancement
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Number input validation
    const numberInputs = document.querySelectorAll('input[type="number"]');
    numberInputs.forEach(function(input) {
        input.addEventListener('input', function() {
            if (this.value < 0) {
                this.value = 0;
            }
        });
    });

    // SKU input formatting (uppercase)
    const skuInput = document.getElementById('sku');
    if (skuInput) {
        skuInput.addEventListener('input', function() {
            this.value = this.value.toUpperCase().replace(/[^A-Z0-9-]/g, '');
        });
    }

    // Price input formatting
    const priceInputs = document.querySelectorAll('input[type="number"][step="0.01"]');
    priceInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            if (this.value) {
                this.value = parseFloat(this.value).toFixed(2);
            }
        });
    });

    // Confirm navigation away from forms with unsaved changes
    let formChanged = false;
    const formInputs = document.querySelectorAll('form input, form textarea, form select');
    formInputs.forEach(function(input) {
        const originalValue = input.value;
        input.addEventListener('input', function() {
            formChanged = (this.value !== originalValue);
        });
    });

    window.addEventListener('beforeunload', function(e) {
        if (formChanged) {
            const confirmationMessage = 'You have unsaved changes. Are you sure you want to leave?';
            e.returnValue = confirmationMessage;
            return confirmationMessage;
        }
    });

    // Reset form changed flag on form submission
    forms.forEach(function(form) {
        form.addEventListener('submit', function() {
            formChanged = false;
        });
    });

    // Category management functionality
    const categorySelect = document.getElementById('category_id');
    if (categorySelect) {
        // Highlight when "No Category" is selected
        categorySelect.addEventListener('change', function() {
            if (this.value === '0') {
                this.classList.add('text-muted');
            } else {
                this.classList.remove('text-muted');
            }
        });
        
        // Initial state
        if (categorySelect.value === '0') {
            categorySelect.classList.add('text-muted');
        }
    }

    // Low stock highlighting
    const quantityInputs = document.querySelectorAll('input[name="quantity"]');
    const minStockInputs = document.querySelectorAll('input[name="minimum_stock"]');
    
    function checkLowStock() {
        const quantity = parseInt(document.querySelector('input[name="quantity"]')?.value) || 0;
        const minStock = parseInt(document.querySelector('input[name="minimum_stock"]')?.value) || 0;
        
        const quantityInput = document.querySelector('input[name="quantity"]');
        if (quantityInput) {
            if (quantity <= minStock && minStock > 0) {
                quantityInput.classList.add('border-warning');
                quantityInput.title = 'Warning: Quantity is at or below minimum stock level';
            } else {
                quantityInput.classList.remove('border-warning');
                quantityInput.title = '';
            }
        }
    }

    quantityInputs.forEach(function(input) {
        input.addEventListener('input', checkLowStock);
    });
    
    minStockInputs.forEach(function(input) {
        input.addEventListener('input', checkLowStock);
    });

    // Initial low stock check
    checkLowStock();
});

// Global utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function formatNumber(number) {
    return new Intl.NumberFormat('en-US').format(number);
}

// Confirmation dialogs
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Loading states
function showLoading(element) {
    element.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    element.disabled = true;
}

function hideLoading(element, originalText) {
    element.innerHTML = originalText;
    element.disabled = false;
}

// Error handling
function showError(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alertDiv);
            bsAlert.close();
        }, 5000);
    }
}

function showSuccess(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-success alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 3 seconds
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alertDiv);
            bsAlert.close();
        }, 3000);
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+S to save forms
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.click();
        }
    }
    
    // Escape to cancel modals
    if (e.key === 'Escape') {
        const openModals = document.querySelectorAll('.modal.show');
        openModals.forEach(function(modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
        });
    }
});
