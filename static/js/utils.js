const API_BASE = '';

async function apiRequest(url, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        } else if (data && method === 'GET') {
            const params = new URLSearchParams(data);
            url += '?' + params.toString();
        }
        
        const response = await fetch(API_BASE + url, options);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = type === 'success' ? 'success-toast' : 'error-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined) return '-';
    return parseFloat(num).toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function formatCurrency(amount, currency = 'CNY') {
    const symbols = {
        'CNY': '¥',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'HKD': 'HK$'
    };
    const symbol = symbols[currency] || currency;
    return symbol + ' ' + formatNumber(amount);
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN');
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

function closeModalOnBackdrop(event, modalId) {
    if (event.target.id === modalId) {
        closeModal(modalId);
    }
}

function getSeverityBadge(severity) {
    const badges = {
        'high': '<span class="badge badge-high">高</span>',
        'medium': '<span class="badge badge-medium">中</span>',
        'low': '<span class="badge badge-low">低</span>',
    };
    return badges[severity] || severity;
}

function getStatusBadge(status) {
    const badges = {
        'approved': '<span class="badge badge-success">已通过</span>',
        'pending': '<span class="badge badge-pending">待审批</span>',
        'pending_approval': '<span class="badge badge-pending">待审批</span>',
        'rejected': '<span class="badge badge-rejected">已拒绝</span>',
        'completed': '<span class="badge badge-success">已完成</span>',
        'executing': '<span class="badge badge-pending">执行中</span>',
        'active': '<span class="badge badge-pending">活跃</span>',
        'resolved': '<span class="badge badge-success">已解决</span>',
        'open': '<span class="badge badge-pending">待处理</span>',
    };
    return badges[status] || status;
}

function navigateTo(page) {
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelector(`[data-page="${page}"]`).classList.add('active');
    
    document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }
    
    if (page === 'dashboard') loadDashboard();
    if (page === 'transactions') loadTransactions();
    if (page === 'forecast') {
        loadForecast();
        setTimeout(() => {
            if (forecastData) {
                Object.keys(forecastData.forecasts).forEach(currency => {
                    const canvas = document.getElementById(`forecast-chart-${currency}`);
                    if (canvas) {
                        drawForecastChart(currency, forecastData.forecasts[currency], forecastData.gaps.filter(g => g.currency === currency));
                    }
                });
            }
        }, 50);
    }
    if (page === 'approvals') loadApprovals();
    if (page === 'adjustments') loadAdjustments();
    if (page === 'risk') loadRiskAlerts();
    if (page === 'reports') loadReports();
}

async function exportTransactions(format) {
    const startDate = document.getElementById('filter-start-date').value;
    const endDate = document.getElementById('filter-end-date').value;
    const currencies = document.getElementById('filter-currency').value;
    
    let url = `/api/transactions/export?format=${format}`;
    if (startDate) url += `&start_date=${startDate}`;
    if (endDate) url += `&end_date=${endDate}`;
    if (currencies) url += `&currencies=${currencies}`;
    
    window.open(url, '_blank');
}
