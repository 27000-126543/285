let accounts = [];

async function loadApprovals() {
    try {
        const [proposalsResult, accountsResult] = await Promise.all([
            apiRequest('/api/proposals'),
            apiRequest('/api/accounts')
        ]);
        
        accounts = accountsResult.accounts;
        renderProposalList(proposalsResult.proposals);
    } catch (error) {
        console.error('加载审批列表失败:', error);
        showToast('加载审批列表失败', 'error');
    }
}

function renderProposalList(proposals) {
    const tabs = `
        <div class="tabs">
            <button class="tab active" onclick="filterProposals('all')">全部 (${proposals.length})</button>
            <button class="tab" onclick="filterProposals('pending_approval')">待审批 (${proposals.filter(p => p.status === 'pending_approval').length})</button>
            <button class="tab" onclick="filterProposals('approved')">已通过 (${proposals.filter(p => p.status === 'approved').length})</button>
            <button class="tab" onclick="filterProposals('completed')">已执行 (${proposals.filter(p => p.status === 'completed').length})</button>
            <button class="tab" onclick="filterProposals('rejected')">已拒绝 (${proposals.filter(p => p.status === 'rejected').length})</button>
        </div>
    `;
    
    const container = document.getElementById('approvals-container');
    
    if (proposals.length === 0) {
        container.innerHTML = tabs + '<div class="loading">暂无换汇方案</div>';
        return;
    }
    
    container.innerHTML = tabs + proposals.map(prop => renderProposalCard(prop)).join('');
}

function filterProposals(status) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    
    apiRequest('/api/proposals' + (status === 'all' ? '' : `?status=${status}`)).then(result => {
        const container = document.getElementById('approvals-container');
        const cards = result.proposals.map(prop => renderProposalCard(prop)).join('');
        container.innerHTML = container.querySelector('.tabs').outerHTML + (cards || '<div class="loading">暂无数据</div>');
    });
}

function renderProposalCard(prop) {
    const amountUsd = estimateUsdAmount(prop.source_amount, prop.source_currency);
    const requiredLevel = calculateRequiredLevel(amountUsd);
    
    return `
        <div class="proposal-card">
            <div class="proposal-header">
                <div>
                    <strong>${prop.source_currency} → ${prop.target_currency}</strong>
                    <span style="margin-left: 10px;">${getStatusBadge(prop.status)}</span>
                    ${requiredLevel >= 3 ? '<span class="badge badge-high">需CFO审批</span>' : ''}
                </div>
                <small>方案编号: ${prop.proposal_id}</small>
            </div>
            <div class="proposal-info">
                <div>
                    <div class="label">卖出金额</div>
                    <div class="value">${formatCurrency(prop.source_amount, prop.source_currency)}</div>
                </div>
                <div>
                    <div class="label">买入金额</div>
                    <div class="value">${formatCurrency(prop.target_amount, prop.target_currency)}</div>
                </div>
                <div>
                    <div class="label">汇率</div>
                    <div class="value">${formatNumber(prop.exchange_rate, 6)}</div>
                </div>
                <div>
                    <div class="label">费用成本</div>
                    <div class="value">${formatCurrency(prop.total_cost, prop.target_currency)}</div>
                </div>
            </div>
            
            <div style="font-size: 12px; color: #666; margin-bottom: 12px;">
                <strong>最优路径:</strong> ${prop.execution_path ? prop.execution_path.join(' → ') : '-'}
                ${prop.cost_comparison && prop.cost_comparison.savings_vs_direct ? 
                    ` | <span style="color: #2e7d32;">节省 ${formatNumber(prop.cost_comparison.savings_vs_direct.savings_percent, 2)}%</span>` : ''}
            </div>
            
            <div class="approval-steps">
                ${renderApprovalSteps(prop.approvals, requiredLevel)}
            </div>
            
            <div style="margin-top: 15px; display: flex; gap: 10px; justify-content: flex-end;">
                <button class="btn btn-sm btn-outline" onclick="viewProposalDetail('${prop.proposal_id}')">查看详情</button>
                ${prop.status === 'pending_approval' ? `
                    <button class="btn btn-sm btn-success" onclick="approveProposal('${prop.proposal_id}', ${getNextPendingLevel(prop.approvals)})">通过</button>
                    <button class="btn btn-sm btn-danger" onclick="rejectProposal('${prop.proposal_id}', ${getNextPendingLevel(prop.approvals)})">拒绝</button>
                ` : ''}
                ${prop.status === 'approved' ? `
                    <button class="btn btn-sm btn-primary" onclick="executeProposal('${prop.proposal_id}', '${prop.source_currency}', '${prop.target_currency}')">执行换汇</button>
                ` : ''}
            </div>
        </div>
    `;
}

function renderApprovalSteps(approvals, requiredLevel) {
    const levels = [
        { level: 1, role: 'financial_manager', label: '财务经理' },
        { level: 2, role: 'finance_director', label: '财务总监' },
        { level: 3, role: 'cfo', label: 'CFO' },
    ];
    
    return levels.slice(0, requiredLevel).map(lvl => {
        const approval = approvals.find(a => a.level === lvl.level);
        let status = 'pending';
        if (approval) {
            status = approval.status === 'approved' ? 'approved' : 
                     approval.status === 'rejected' ? 'rejected' : 'pending';
        }
        return `
            <div class="approval-step ${status}">
                ${lvl.label}<br>
                ${status === 'approved' ? '✓ 已通过' : status === 'rejected' ? '✗ 已拒绝' : '待审批'}
                ${approval && approval.approver ? `<br><small>${approval.approver}</small>` : ''}
            </div>
        `;
    }).join('');
}

function getNextPendingLevel(approvals) {
    if (!approvals || approvals.length === 0) return 1;
    const pending = approvals.find(a => a.status === 'pending');
    return pending ? pending.level : 1;
}

function estimateUsdAmount(amount, currency) {
    const rates = { 'USD': 1, 'CNY': 0.14, 'EUR': 1.09, 'GBP': 1.27, 'HKD': 0.128, 'JPY': 0.0067 };
    return amount * (rates[currency] || 1);
}

function calculateRequiredLevel(amountUsd) {
    if (amountUsd >= 500000) return 3;
    if (amountUsd >= 200000) return 2;
    if (amountUsd >= 50000) return 1;
    return 1;
}

function viewProposalDetail(proposalId) {
    showToast(`查看方案详情: ${proposalId}`, 'success');
}

async function approveProposal(proposalId, level) {
    const approver = prompt('请输入审批人姓名:');
    if (!approver) return;
    
    const comments = prompt('审批意见（可选）:');
    
    try {
        await apiRequest(`/api/proposals/${proposalId}/approve?level=${level}&approver=${encodeURIComponent(approver)}${comments ? '&comments=' + encodeURIComponent(comments) : ''}`, 'POST');
        showToast('审批成功', 'success');
        loadApprovals();
    } catch (error) {
        showToast('审批失败: ' + error.message, 'error');
    }
}

async function rejectProposal(proposalId, level) {
    const approver = prompt('请输入审批人姓名:');
    if (!approver) return;
    
    const comments = prompt('拒绝原因:');
    
    try {
        await apiRequest(`/api/proposals/${proposalId}/reject?level=${level}&approver=${encodeURIComponent(approver)}${comments ? '&comments=' + encodeURIComponent(comments) : ''}`, 'POST');
        showToast('已拒绝', 'success');
        loadApprovals();
    } catch (error) {
        showToast('操作失败: ' + error.message, 'error');
    }
}

async function executeProposal(proposalId, sourceCurrency, targetCurrency) {
    const sourceAccounts = accounts.filter(a => a.currency === sourceCurrency);
    const targetAccounts = accounts.filter(a => a.currency === targetCurrency);
    
    if (sourceAccounts.length === 0 || targetAccounts.length === 0) {
        showToast('找不到对应币种的账户', 'error');
        return;
    }
    
    const sourceAccount = sourceAccounts[0].id;
    const targetAccount = targetAccounts[0].id;
    
    if (!confirm(`确认执行换汇？\n从账户 ${sourceAccount} 到 ${targetAccount}`)) return;
    
    try {
        const result = await apiRequest(`/api/proposals/${proposalId}/execute?source_account=${sourceAccount}&target_account=${targetAccount}`, 'POST');
        showToast(`换汇执行成功: ${result.execution.execution_id}`, 'success');
        loadApprovals();
    } catch (error) {
        showToast('执行失败: ' + error.message, 'error');
    }
}
