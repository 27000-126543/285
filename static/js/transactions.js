let currentTransactionsPage = 1;
const transactionsPageSize = 20;

document.addEventListener('DOMContentLoaded', function() {
    const filterInputs = [
        'filter-start-date', 'filter-end-date', 'filter-currency',
        'filter-type', 'filter-min-amount', 'filter-max-amount', 'filter-counterparty'
    ];
    
    filterInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    currentTransactionsPage = 1;
                    loadTransactions();
                }
            });
        }
    });
});

async function loadTransactions() {
    try {
        const startDate = document.getElementById('filter-start-date').value;
        const endDate = document.getElementById('filter-end-date').value;
        const currencies = document.getElementById('filter-currency').value;
        const txnType = document.getElementById('filter-type').value;
        const minAmount = document.getElementById('filter-min-amount').value;
        const maxAmount = document.getElementById('filter-max-amount').value;
        const counterparty = document.getElementById('filter-counterparty').value;
        
        const params = {
            page: currentTransactionsPage,
            page_size: transactionsPageSize,
        };
        
        if (startDate) params.start_date = startDate;
        if (endDate) params.end_date = endDate;
        if (currencies) params.currencies = currencies;
        if (txnType) params.txn_type = txnType;
        if (minAmount) params.min_amount = minAmount;
        if (maxAmount) params.max_amount = maxAmount;
        if (counterparty) params.counterparty = counterparty;
        
        const result = await apiRequest('/api/transactions', 'GET', params);
        renderTransactions(result);
    } catch (error) {
        console.error('加载交易流水失败:', error);
        showToast('加载交易流水失败', 'error');
    }
}

function renderTransactions(result) {
    const tbody = document.getElementById('transactions-body');
    
    if (result.data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading">暂无交易数据</td></tr>`;
        document.getElementById('transactions-pagination').innerHTML = '';
        return;
    }
    
    tbody.innerHTML = result.data.map(txn => `
        <tr>
            <td>${formatDate(txn.txn_date)}</td>
            <td><span class="badge badge-${txn.txn_type === 'in' ? 'success' : 'warning'}">${txn.txn_type === 'in' ? '收入' : '支出'}</span></td>
            <td><strong>${txn.currency}</strong></td>
            <td style="color: ${txn.amount >= 0 ? '#2e7d32' : '#c62828'}">
                ${formatCurrency(txn.amount, txn.currency)}
            </td>
            <td>${txn.account_id}</td>
            <td>${txn.counterparty || '-'}</td>
            <td>${txn.category || '-'}</td>
            <td>${txn.description || '-'}</td>
        </tr>
    `).join('');
    
    renderPagination(result.total_count, result.total_pages, result.page, 'transactions');
}

function renderPagination(totalCount, totalPages, currentPage, prefix) {
    const container = document.getElementById(`${prefix}-pagination`);
    if (totalPages <= 1) {
        container.innerHTML = `<div style="text-align: center; color: #999; font-size: 13px;">共 ${totalCount} 条记录</div>`;
        return;
    }
    
    let html = `<div class="pagination">`;
    html += `<span style="color: #666; font-size: 13px;">共 ${totalCount} 条记录</span>`;
    html += `<button onclick="changePage(${prefix}, 1)" ${currentPage === 1 ? 'disabled' : ''}>首页</button>`;
    html += `<button onclick="changePage(${prefix}, ${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>上一页</button>`;
    
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="${i === currentPage ? 'current' : ''}" onclick="changePage(${prefix}, ${i})">${i}</button>`;
    }
    
    html += `<button onclick="changePage(${prefix}, ${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>下一页</button>`;
    html += `<button onclick="changePage(${prefix}, ${totalPages})" ${currentPage === totalPages ? 'disabled' : ''}>末页</button>`;
    html += `</div>`;
    
    container.innerHTML = html;
}

function changePage(prefix, page) {
    if (prefix === 'transactions') {
        currentTransactionsPage = page;
        loadTransactions();
    }
}

function resetFilters() {
    document.getElementById('filter-start-date').value = '';
    document.getElementById('filter-end-date').value = '';
    document.getElementById('filter-currency').value = '';
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-min-amount').value = '';
    document.getElementById('filter-max-amount').value = '';
    document.getElementById('filter-counterparty').value = '';
    currentTransactionsPage = 1;
    loadTransactions();
}
