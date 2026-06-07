let forecastData = null;

async function loadForecast() {
    try {
        const result = await apiRequest('/api/forecast');
        forecastData = result;
        renderForecastCharts(result);
        renderGapList(result.gaps);
    } catch (error) {
        console.error('加载预测数据失败:', error);
        showToast('加载预测数据失败', 'error');
    }
}

function renderForecastCharts(result) {
    const container = document.getElementById('forecast-charts');
    const currencies = Object.keys(result.forecasts);
    
    if (currencies.length === 0) {
        container.innerHTML = '<div class="loading">暂无预测数据，请先运行每日任务</div>';
        return;
    }
    
    container.innerHTML = currencies.map(currency => `
        <div class="card">
            <div class="card-header">
                <h3>${currency} 7日资金预测</h3>
                <span class="badge badge-low">预测日期: ${formatDate(result.forecast_date)}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <canvas id="forecast-chart-${currency}" height="250"></canvas>
            </div>
        </div>
    `).join('');
    
    currencies.forEach(currency => {
        drawForecastChart(currency, result.forecasts[currency], result.gaps.filter(g => g.currency === currency));
    });
}

function drawForecastChart(currency, forecasts, gaps) {
    const canvas = document.getElementById(`forecast-chart-${currency}`);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.offsetWidth || 800;
    const height = canvas.height = 250;
    
    const padding = { top: 30, right: 20, bottom: 50, left: 80 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    
    if (chartWidth <= 0 || chartHeight <= 0) {
        setTimeout(() => drawForecastChart(currency, forecasts, gaps), 100);
        return;
    }
    
    const allBalances = forecasts.map(f => f.projected_balance);
    const allInflows = forecasts.map(f => f.inflow);
    const allOutflows = forecasts.map(f => f.outflow);
    
    const maxVal = Math.max(...allBalances, ...allInflows, ...allOutflows);
    const minVal = Math.min(...allBalances, 0);
    const range = maxVal - minVal || 1;
    
    ctx.clearRect(0, 0, width, height);
    
    ctx.strokeStyle = '#f0f0f0';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
        const y = padding.top + (i / 5) * chartHeight;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
        
        const value = maxVal - (i / 5) * range;
        ctx.fillStyle = '#999';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(formatNumber(value, 0), padding.left - 10, y + 4);
    }
    
    const gapDates = gaps.map(g => g.gap_date);
    forecasts.forEach((fc, i) => {
        const x = padding.left + (i / (forecasts.length - 1)) * chartWidth;
        
        if (gapDates.includes(fc.target_date)) {
            ctx.fillStyle = 'rgba(255, 0, 0, 0.1)';
            const barWidth = chartWidth / forecasts.length;
            ctx.fillRect(x - barWidth / 2, padding.top, barWidth, chartHeight);
        }
    });
    
    ctx.beginPath();
    ctx.strokeStyle = '#667eea';
    ctx.lineWidth = 3;
    forecasts.forEach((fc, i) => {
        const x = padding.left + (i / (forecasts.length - 1)) * chartWidth;
        const y = padding.top + ((maxVal - fc.projected_balance) / range) * chartHeight;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    forecasts.forEach((fc, i) => {
        const x = padding.left + (i / (forecasts.length - 1)) * chartWidth;
        const y = padding.top + ((maxVal - fc.projected_balance) / range) * chartHeight;
        
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = gapDates.includes(fc.target_date) ? '#c62828' : '#667eea';
        ctx.fill();
        
        ctx.fillStyle = '#666';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(fc.target_date.slice(5), x, height - 20);
        
        ctx.fillStyle = '#333';
        ctx.font = 'bold 10px sans-serif';
        ctx.fillText(formatNumber(fc.projected_balance, 0), x, y - 10);
    });
    
    ctx.fillStyle = '#333';
    ctx.font = 'bold 12px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('预计余额', padding.left, 20);
    ctx.fillStyle = '#667eea';
    ctx.fillRect(padding.left + 70, 12, 20, 3);
    
    if (gaps.length > 0) {
        ctx.fillStyle = '#c62828';
        ctx.fillRect(padding.left + 140, 12, 20, 3);
        ctx.fillStyle = '#c62828';
        ctx.fillText('资金缺口', padding.left + 170, 20);
    }
}

function renderGapList(gaps) {
    const tbody = document.getElementById('gaps-body');
    
    if (gaps.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading">暂无资金缺口，各币种资金状况良好</td></tr>`;
        return;
    }
    
    tbody.innerHTML = gaps.map(gap => `
        <tr style="cursor: pointer;" onclick="showGapProposals(${gap.id}, '${gap.currency}', ${gap.gap_amount})">
            <td>${formatDate(gap.gap_date)}</td>
            <td><strong>${gap.currency}</strong></td>
            <td style="color: #c62828"><strong>${formatCurrency(gap.gap_amount, gap.currency)}</strong></td>
            <td>${formatCurrency(gap.projected_balance, gap.currency)}</td>
            <td>${formatCurrency(gap.threshold, gap.currency)}</td>
            <td>${getSeverityBadge(gap.severity)}</td>
        </tr>
    `).join('');
}

async function showGapProposals(gapId, currency, gapAmount) {
    try {
        const result = await apiRequest(`/api/gaps/${gapId}/proposals`);
        
        document.getElementById('gap-proposal-title').textContent = 
            `${currency} 缺口 ${formatCurrency(gapAmount, currency)} - 换汇方案`;
        
        const container = document.getElementById('gap-proposals-content');
        
        if (result.proposals.length === 0) {
            container.innerHTML = '<div class="loading">暂无换汇方案，系统将自动生成</div>';
        } else {
            container.innerHTML = result.proposals.map(prop => `
                <div class="proposal-card">
                    <div class="proposal-header">
                        <div>
                            <strong>方案 ${prop.proposal_id}</strong>
                            ${getStatusBadge(prop.status)}
                        </div>
                        <small>${formatDateTime(prop.created_at)}</small>
                    </div>
                    <div class="proposal-info">
                        <div>
                            <div class="label">卖出</div>
                            <div class="value">${formatCurrency(prop.source_amount, prop.source_currency)}</div>
                        </div>
                        <div>
                            <div class="label">买入</div>
                            <div class="value">${formatCurrency(prop.target_amount, prop.target_currency)}</div>
                        </div>
                        <div>
                            <div class="label">汇率</div>
                            <div class="value">${formatNumber(prop.exchange_rate, 6)}</div>
                        </div>
                        <div>
                            <div class="label">费用</div>
                            <div class="value">${formatCurrency(prop.fee_amount, prop.target_currency)}</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #666; margin-bottom: 10px;">
                        <strong>执行路径:</strong> ${prop.execution_path ? prop.execution_path.join(' → ') : '-'}
                    </div>
                    ${prop.status === 'pending_approval' ? `
                        <div class="approval-steps">
                            ${prop.approvals.map(a => `
                                <div class="approval-step ${a.status}">
                                    第${a.level}级<br>${a.role}<br>${a.status === 'approved' ? '已通过' : a.status === 'rejected' ? '已拒绝' : '待审批'}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }
        
        openModal('gap-proposals-modal');
    } catch (error) {
        console.error('获取换汇方案失败:', error);
        showToast('获取换汇方案失败', 'error');
    }
}
