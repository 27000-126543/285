async function loadDashboard() {
    try {
        const summary = await apiRequest('/api/dashboard/summary');
        const fxRates = await apiRequest('/api/dashboard/fx-rates');
        
        renderSummaryStats(summary);
        renderCurrencyCards(summary);
        renderFxRates(fxRates);
    } catch (error) {
        console.error('加载仪表盘失败:', error);
        showToast('加载仪表盘失败', 'error');
    }
}

function renderSummaryStats(summary) {
    const statsGrid = document.getElementById('stats-grid');
    statsGrid.innerHTML = `
        <div class="stat-card">
            <div class="stat-label">资金总规模</div>
            <div class="stat-value">${formatCurrency(summary.total_balance_base, summary.base_currency)}</div>
            <div class="stat-change positive">基于 ${summary.base_currency} 计算</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">活跃币种</div>
            <div class="stat-value">${summary.currencies.length}</div>
            <div class="stat-change positive">已全部对接</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">资金缺口</div>
            <div class="stat-value" style="color: ${summary.active_gaps > 0 ? '#c62828' : '#2e7d32'}">${summary.active_gaps}</div>
            <div class="stat-change ${summary.active_gaps > 0 ? 'warning' : 'positive'}">${summary.active_gaps > 0 ? '需及时处理' : '全部健康'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">风险预警</div>
            <div class="stat-value" style="color: ${summary.active_alerts > 0 ? '#ef6c00' : '#2e7d32'}">${summary.active_alerts}</div>
            <div class="stat-change ${summary.active_alerts > 0 ? 'warning' : 'positive'}">${summary.active_alerts > 0 ? '关注汇率波动' : '风险可控'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">待审批方案</div>
            <div class="stat-value" style="color: ${summary.pending_approvals > 0 ? '#f9a825' : '#2e7d32'}">${summary.pending_approvals}</div>
            <div class="stat-change ${summary.pending_approvals > 0 ? 'warning' : 'positive'}">${summary.pending_approvals > 0 ? '请及时审批' : '全部处理'}</div>
        </div>
    `;
}

function renderCurrencyCards(summary) {
    const container = document.getElementById('currency-cards');
    container.innerHTML = summary.currencies.map(curr => `
        <div class="currency-card ${curr.currency.toLowerCase()}">
            <h4>${curr.currency} · ${curr.accounts} 个账户</h4>
            <div class="balance">${formatCurrency(curr.balance, curr.currency)}</div>
            <div class="meta">
                可用: ${formatCurrency(curr.available, curr.currency)}<br>
                汇率: 1 ${curr.currency} = ${curr.rate_to_base} ${summary.base_currency}<br>
                7日波动: <span style="color: ${curr.volatility_7d > 2 ? '#ffeb3b' : 'inherit'}">${curr.volatility_7d}%</span>
            </div>
        </div>
    `).join('');
}

function renderFxRates(fxRates) {
    const tbody = document.getElementById('fx-rates-body');
    tbody.innerHTML = fxRates.rates.map(rate => `
        <tr>
            <td><strong>${rate.currency}</strong></td>
            <td>${formatNumber(rate.rate, 6)}</td>
            <td>
                <span class="${rate.change_7d >= 0 ? 'stat-change positive' : 'stat-change negative'}">
                    ${rate.change_7d >= 0 ? '↑' : '↓'} ${Math.abs(rate.change_7d)}%
                </span>
            </td>
            <td>
                <canvas id="mini-chart-${rate.currency}" width="100" height="30"></canvas>
            </td>
        </tr>
    `).join('');
    
    fxRates.rates.forEach(rate => {
        const canvas = document.getElementById(`mini-chart-${rate.currency}`);
        if (canvas && rate.history.length > 1) {
            drawMiniChart(canvas, rate.history.map(h => h.rate));
        }
    });
}

function drawMiniChart(canvas, data) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const padding = 2;
    
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    
    ctx.clearRect(0, 0, width, height);
    ctx.beginPath();
    ctx.strokeStyle = data[data.length - 1] >= data[0] ? '#2e7d32' : '#c62828';
    ctx.lineWidth = 2;
    
    data.forEach((value, index) => {
        const x = padding + (index / (data.length - 1)) * (width - 2 * padding);
        const y = height - padding - ((value - min) / range) * (height - 2 * padding);
        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.stroke();
}
