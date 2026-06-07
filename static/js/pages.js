async function loadAdjustments() {
    try {
        const result = await apiRequest('/api/manual-adjustments');
        renderAdjustments(result.adjustments);
    } catch (error) {
        console.error('加载手动调整失败:', error);
        showToast('加载手动调整失败', 'error');
    }
}

function renderAdjustments(adjustments) {
    const tbody = document.getElementById('adjustments-body');
    
    if (adjustments.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading">暂无手动调整记录</td></tr>`;
        return;
    }
    
    tbody.innerHTML = adjustments.map(adj => `
        <tr>
            <td>${formatDate(adj.effective_date)}</td>
            <td><strong>${adj.currency}</strong></td>
            <td><span class="badge badge-${adj.adjustment_type === 'inflow' ? 'success' : 'warning'}">${adj.adjustment_type === 'inflow' ? '流入' : '流出'}</span></td>
            <td>${formatCurrency(adj.amount, adj.currency)}</td>
            <td>${adj.description}</td>
            <td>${adj.created_by}</td>
        </tr>
    `).join('');
}

async function submitAdjustment() {
    const currency = document.getElementById('adj-currency').value;
    const adjustmentType = document.getElementById('adj-type').value;
    const amount = parseFloat(document.getElementById('adj-amount').value);
    const effectiveDate = document.getElementById('adj-date').value;
    const description = document.getElementById('adj-description').value;
    const counterparty = document.getElementById('adj-counterparty').value;
    const category = document.getElementById('adj-category').value;
    
    if (!currency || !adjustmentType || !amount || !effectiveDate || !description) {
        showToast('请填写必填项', 'error');
        return;
    }
    
    try {
        const data = {
            currency,
            adjustment_type: adjustmentType,
            amount,
            effective_date: effectiveDate,
            description,
            counterparty: counterparty || '',
            category: category || '',
            created_by: 'web_user'
        };
        
        await apiRequest('/api/manual-adjustments', 'POST', data);
        showToast('添加成功，预测已自动更新', 'success');
        closeModal('adjustment-modal');
        document.getElementById('adjustment-form').reset();
        loadAdjustments();
    } catch (error) {
        showToast('添加失败: ' + error.message, 'error');
    }
}

async function loadRiskAlerts() {
    try {
        const [alertsResult, exposuresResult] = await Promise.all([
            apiRequest('/api/risk/alerts'),
            apiRequest('/api/risk/exposures')
        ]);
        
        renderRiskAlerts(alertsResult.alerts);
        renderExposures(exposuresResult.exposures);
    } catch (error) {
        console.error('加载风险预警失败:', error);
        showToast('加载风险预警失败', 'error');
    }
}

function renderRiskAlerts(alerts) {
    const container = document.getElementById('risk-alerts');
    
    if (alerts.length === 0) {
        container.innerHTML = '<div class="loading">暂无风险预警，各币种汇率稳定</div>';
        return;
    }
    
    container.innerHTML = alerts.map(alert => `
        <div class="alert-item ${alert.severity}">
            <div class="alert-header">
                <div>
                    <strong class="alert-title">${alert.currency} - ${getAlertTypeLabel(alert.alert_type)}</strong>
                    ${getSeverityBadge(alert.severity)}
                </div>
                <span class="alert-time">${formatDateTime(alert.created_at)}</span>
            </div>
            <div class="alert-message">${alert.message}</div>
            ${alert.hedge_recommendation ? `
                <div class="alert-recommendations">
                    <strong>对冲建议:</strong>
                    <ul style="margin: 8px 0 0 20px; padding: 0;">
                        ${alert.hedge_recommendation.recommendations ? 
                            alert.hedge_recommendation.recommendations.map(r => `<li>${r}</li>`).join('') : ''}
                    </ul>
                    ${alert.hedge_recommendation.suggested_hedge_ratio ? 
                        `<div style="margin-top: 8px;">建议对冲比例: ${(alert.hedge_recommendation.suggested_hedge_ratio * 100).toFixed(0)}%</div>` : ''}
                    ${alert.hedge_recommendation.suggested_instruments ? 
                        `<div>建议工具: ${alert.hedge_recommendation.suggested_instruments.join(', ')}</div>` : ''}
                </div>
            ` : ''}
        </div>
    `).join('');
}

function getAlertTypeLabel(type) {
    const labels = {
        'volatility': '汇率波动预警',
        'exposure_concentration': '敞口集中预警',
        'gap': '资金缺口预警'
    };
    return labels[type] || type;
}

function renderExposures(exposures) {
    const tbody = document.getElementById('exposures-body');
    
    if (exposures.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading">暂无敞口数据</td></tr>`;
        return;
    }
    
    tbody.innerHTML = exposures.map(exp => `
        <tr>
            <td><strong>${exp.currency}</strong></td>
            <td>${formatCurrency(exp.net_position, exp.currency)}</td>
            <td>${formatCurrency(exp.exposure_amount, exp.base_currency)}</td>
            <td>
                <span class="${exp.volatility_3d * 100 > 2 ? 'stat-change negative' : 'stat-change positive'}">
                    ${(exp.volatility_3d * 100).toFixed(2)}%
                </span>
            </td>
            <td>${formatCurrency(exp.var_95, exp.base_currency)}</td>
            <td>${formatDate(exp.exposure_date)}</td>
        </tr>
    `).join('');
}

async function loadReports() {
    try {
        const result = await apiRequest('/api/reports');
        renderReports(result.reports);
    } catch (error) {
        console.error('加载报告列表失败:', error);
        showToast('加载报告列表失败', 'error');
    }
}

function renderReports(reports) {
    const container = document.getElementById('reports-list');
    
    if (reports.length === 0) {
        container.innerHTML = '<div class="loading">暂无月度报告，请先运行系统生成</div>';
        return;
    }
    
    container.innerHTML = reports.map(report => `
        <div class="report-card">
            <div class="report-info">
                <h4>📊 ${report.report_month} 资金池分析报告</h4>
                <p>生成时间: ${formatDateTime(report.created_at)}</p>
            </div>
            <div class="report-actions">
                <button class="btn btn-sm btn-primary" onclick="downloadReport('${report.report_id}', 'pdf')">
                    📄 下载 PDF
                </button>
                <button class="btn btn-sm btn-success" onclick="downloadReport('${report.report_id}', 'excel')">
                    📊 下载 Excel
                </button>
            </div>
        </div>
    `).join('');
}

function downloadReport(reportId, format) {
    window.open(`/api/reports/${reportId}/download?format=${format}`, '_blank');
}

async function generateNewReport() {
    if (!confirm('确认生成本月报告？这可能需要一点时间。')) return;
    
    try {
        await apiRequest('/api/system/run-daily', 'POST');
        showToast('报告生成任务已启动', 'success');
        setTimeout(() => loadReports(), 3000);
    } catch (error) {
        showToast('生成失败: ' + error.message, 'error');
    }
}
