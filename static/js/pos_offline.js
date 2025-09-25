/**
 * POS Offline Manager - Gestión de ventas sin conexión
 * Workly - Sistema multiempresa
 */

class POSOfflineManager {
    constructor() {
        this.dbName = 'pos_offline_db';
        this.dbVersion = 1;
        this.storeName = 'offline_sales';
        this.db = null;
        this.isOnline = navigator.onLine;
        this.syncInProgress = false;
        this.pendingSales = [];
        
        this.init();
    }

    async init() {
        await this.initIndexedDB();
        this.setupEventListeners();
        this.updateConnectionStatus();
        await this.loadPendingSales();
        
        // Intentar sincronizar al inicializar si hay conexión
        if (this.isOnline && this.pendingSales.length > 0) {
            this.syncPendingSales();
        }
    }

    async initIndexedDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                if (!db.objectStoreNames.contains(this.storeName)) {
                    const store = db.createObjectStore(this.storeName, { keyPath: 'uuid' });
                    store.createIndex('company_id', 'company_id', { unique: false });
                    store.createIndex('user_id', 'user_id', { unique: false });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                    store.createIndex('sync_status', 'sync_status', { unique: false });
                }
            };
        });
    }

    setupEventListeners() {
        // Detectar cambios de conexión
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.updateConnectionStatus();
            this.showNotification('Conexión restaurada. Sincronizando ventas...', 'success');
            this.syncPendingSales();
        });

        window.addEventListener('offline', () => {
            this.isOnline = false;
            this.updateConnectionStatus();
            this.showNotification('Sin conexión. Las ventas se guardarán localmente.', 'warning');
        });

        // Sincronizar cada 30 segundos si hay conexión
        setInterval(() => {
            if (this.isOnline && this.pendingSales.length > 0 && !this.syncInProgress) {
                this.syncPendingSales();
            }
        }, 30000);
    }

    updateConnectionStatus() {
        const statusElement = document.getElementById('connectionStatus');
        const pendingBanner = document.getElementById('pendingSalesBanner');
        
        if (statusElement) {
            if (this.isOnline) {
                statusElement.innerHTML = '<i class="fas fa-wifi text-success"></i> En línea';
                statusElement.className = 'connection-status online';
            } else {
                statusElement.innerHTML = '<i class="fas fa-wifi-slash text-danger"></i> Sin conexión (Modo offline)';
                statusElement.className = 'connection-status offline';
            }
        }

        // Mostrar banner de ventas pendientes
        if (pendingBanner) {
            if (this.pendingSales.length > 0) {
                pendingBanner.style.display = 'block';
                pendingBanner.innerHTML = `
                    <div class="alert alert-info alert-dismissible">
                        <i class="fas fa-sync-alt"></i> 
                        Hay ${this.pendingSales.length} venta(s) pendiente(s) de sincronizar.
                        ${this.isOnline && !this.syncInProgress ? 
                            '<button class="btn btn-sm btn-primary ms-2" onclick="posOfflineManager.syncPendingSales()">Sincronizar Ahora</button>' : 
                            ''
                        }
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                `;
            } else {
                pendingBanner.style.display = 'none';
            }
        }
    }

    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    async saveOfflineSale(saleData) {
        try {
            // Obtener datos del usuario actual desde el DOM o variables globales
            const userDataElement = document.getElementById('currentUserData');
            const userData = userDataElement ? JSON.parse(userDataElement.textContent) : null;
            
            if (!userData) {
                throw new Error('No se encontraron datos del usuario actual');
            }

            const offlineSale = {
                uuid: this.generateUUID(),
                company_id: userData.company_id,
                user_id: userData.user_id,
                timestamp: new Date().toISOString(),
                sync_status: 'pending',
                sale_data: saleData,
                created_at: new Date().toISOString(),
                attempts: 0,
                error_message: null
            };

            await this.addToIndexedDB(offlineSale);
            await this.loadPendingSales();
            this.updateConnectionStatus();

            this.showNotification(
                `Venta guardada offline (${offlineSale.uuid.substring(0, 8)}...). Se sincronizará automáticamente.`, 
                'info'
            );

            return offlineSale.uuid;
        } catch (error) {
            console.error('Error guardando venta offline:', error);
            this.showNotification('Error guardando venta offline: ' + error.message, 'error');
            throw error;
        }
    }

    async addToIndexedDB(saleData) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);
            const request = store.add(saleData);
            
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async loadPendingSales() {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readonly');
            const store = transaction.objectStore(this.storeName);
            const index = store.index('sync_status');
            const request = index.getAll('pending');
            
            request.onsuccess = () => {
                this.pendingSales = request.result || [];
                resolve(this.pendingSales);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async syncPendingSales() {
        if (this.syncInProgress || !this.isOnline || this.pendingSales.length === 0) {
            return;
        }

        this.syncInProgress = true;
        let successCount = 0;
        let errorCount = 0;

        try {
            // Obtener CSRF token
            const csrfToken = document.querySelector('[name="csrf_token"]').value;
            
            for (const sale of this.pendingSales) {
                try {
                    const response = await fetch('/pos/sync', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({
                            uuid: sale.uuid,
                            sale_data: sale.sale_data,
                            company_id: sale.company_id,
                            user_id: sale.user_id,
                            timestamp: sale.timestamp
                        })
                    });

                    const result = await response.json();

                    if (result.success) {
                        await this.markAsSynced(sale.uuid, result.sale_number);
                        successCount++;
                    } else {
                        await this.markAsError(sale.uuid, result.error);
                        errorCount++;
                    }
                } catch (error) {
                    console.error('Error sincronizando venta:', sale.uuid, error);
                    await this.markAsError(sale.uuid, error.message);
                    errorCount++;
                }
            }

            await this.loadPendingSales();
            this.updateConnectionStatus();

            if (successCount > 0) {
                this.showNotification(
                    `${successCount} venta(s) sincronizada(s) exitosamente.${errorCount > 0 ? ` ${errorCount} error(es).` : ''}`, 
                    'success'
                );
            }

            if (errorCount > 0 && successCount === 0) {
                this.showNotification(`Error sincronizando ${errorCount} venta(s). Se reintentará automáticamente.`, 'error');
            }

        } catch (error) {
            console.error('Error general en sincronización:', error);
            this.showNotification('Error en sincronización: ' + error.message, 'error');
        } finally {
            this.syncInProgress = false;
        }
    }

    async markAsSynced(uuid, saleNumber) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);
            const request = store.delete(uuid);
            
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async markAsError(uuid, errorMessage) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);
            const getRequest = store.get(uuid);
            
            getRequest.onsuccess = () => {
                const sale = getRequest.result;
                if (sale) {
                    sale.sync_status = 'error';
                    sale.error_message = errorMessage;
                    sale.attempts = (sale.attempts || 0) + 1;
                    sale.last_attempt = new Date().toISOString();
                    
                    const putRequest = store.put(sale);
                    putRequest.onsuccess = () => resolve();
                    putRequest.onerror = () => reject(putRequest.error);
                } else {
                    resolve();
                }
            };
            
            getRequest.onerror = () => reject(getRequest.error);
        });
    }

    showNotification(message, type = 'info') {
        // Crear notificación toast
        const toastHtml = `
            <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        
        // Agregar al contenedor de toasts
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }
        
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        // Mostrar toast
        const toastElement = toastContainer.lastElementChild;
        const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
        toast.show();
        
        // Remover después de ocultar
        toastElement.addEventListener('hidden.bs.toast', function() {
            toastElement.remove();
        });
    }

    // Método público para que otros scripts guarden ventas offline
    async processSaleOffline(saleData) {
        return await this.saveOfflineSale(saleData);
    }

    // Verificar estado de conexión
    isConnectionOnline() {
        return this.isOnline;
    }

    // Obtener número de ventas pendientes
    getPendingSalesCount() {
        return this.pendingSales.length;
    }
}

// Inicializar manager cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    window.posOfflineManager = new POSOfflineManager();
});

// Exportar para uso en otros scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = POSOfflineManager;
}