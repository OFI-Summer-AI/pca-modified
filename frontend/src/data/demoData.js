const standardFlow = [
  'create purchase order item',
  'approve purchase order',
  'send to vendor',
  'goods receipt',
  'invoice receipt',
  'payment processed',
];

const criticalSteps = ['approve purchase order', 'goods receipt', 'invoice receipt'];

const customers = [
  'Siemens AG', 'Bosch GmbH', 'BASF SE', 'BMW Group', 'Volkswagen AG',
  'Deutsche Bank', 'Allianz SE', 'Bayer AG', 'SAP SE', 'Daimler AG',
  'ThyssenKrupp', 'Continental AG',
];

const rcaBank = [
  {
    root_cause: 'Goods receipt step was entirely skipped, likely due to direct invoice processing without physical delivery confirmation.',
    business_risk: 'Cannot confirm physical delivery of goods. Payment made without GR creates financial exposure and audit risk.',
    recommendation: 'Mandatory GR confirmation required before invoice processing. Enable GR-based invoice verification in SAP MM.',
    sap_transactions: ['MIGO', 'ME23N', 'MIR7'],
    immediate_fix: 'Place payment on hold pending physical goods receipt confirmation.',
  },
  {
    root_cause: 'Purchase order was approved after goods receipt, indicating retroactive approval. Approval workflow may have been bypassed.',
    business_risk: 'Retroactive approvals undermine internal controls and create compliance violations in SOX-regulated environments.',
    recommendation: 'Enforce approval gates in SAP workflow. Configure system to prevent GR posting without prior PO approval.',
    sap_transactions: ['ME29N', 'SWI5', 'SWIA'],
    immediate_fix: 'Escalate to procurement manager for retroactive approval documentation.',
  },
  {
    root_cause: 'Net price modification detected post-approval. Price change after approval indicates unauthorized modification or vendor negotiation outside standard process.',
    business_risk: 'Unapproved price changes can lead to budget overruns and potential fraud. Creates discrepancy between approved and actual amounts.',
    recommendation: 'Implement price change approval workflow. Configure price tolerance checks in SAP with automatic re-approval trigger.',
    sap_transactions: ['ME22N', 'ME23N', 'ME9F'],
    immediate_fix: 'Flag for immediate procurement review and obtain written approval for price change.',
  },
  {
    root_cause: 'Multiple process steps appear out of expected sequence. This typically indicates manual intervention or emergency bypass of standard workflow.',
    business_risk: 'Out-of-sequence processing creates audit trails that are difficult to reconcile and may indicate control failures.',
    recommendation: 'Review workflow configuration in SAP to enforce sequential processing. Implement process controls to prevent out-of-order execution.',
    sap_transactions: ['ME23N', 'MIRO', 'F-53'],
    immediate_fix: 'Document reason for sequence deviation and obtain retrospective approval from department head.',
  },
  {
    root_cause: 'Purchase order deletion occurred mid-process, suggesting either vendor cancellation or internal procurement change without proper documentation.',
    business_risk: 'Deleted POs with partial fulfillment create liability exposure and may result in disputed invoices from vendors.',
    recommendation: 'Implement PO deletion approval workflow. Require business justification before system allows deletion of active POs.',
    sap_transactions: ['ME22N', 'ME9F', 'ME2M'],
    immediate_fix: 'Verify with vendor if goods/services were already partially delivered before PO deletion.',
  },
  {
    root_cause: 'Quantity change detected after initial order confirmation. May indicate demand fluctuation or unauthorized modification.',
    business_risk: 'Uncontrolled quantity changes affect budget planning and vendor relationship management.',
    recommendation: 'Configure quantity change tolerance thresholds in SAP. Changes beyond threshold should trigger re-approval workflow.',
    sap_transactions: ['ME22N', 'ME23N', 'MB51'],
    immediate_fix: 'Verify quantity change was authorized and update budget allocation accordingly.',
  },
];

export function buildDemoData() {
  const orders = [];
  const now = new Date();

  for (let i = 0; i < 40; i++) {
    const orderNum = `45${(100000 + i).toString()}`;
    const customer = customers[i % customers.length];
    const daysAgo = Math.floor(Math.random() * 90);
    const orderDate = new Date(now - daysAgo * 86400000).toISOString().split('T')[0];
    const rca = rcaBank[i % rcaBank.length];

    let processStatus, riskLevel, deviations, actualFlow;

    if (i < 8) {
      // BLOCKED
      processStatus = 'BLOCKED';
      riskLevel = 'CRITICAL';
      const missingStep = criticalSteps[i % criticalSteps.length];
      actualFlow = standardFlow.filter((s) => s !== missingStep);
      deviations = [
        {
          type: 'MISSING_CRITICAL_STEP',
          severity: 'CRITICAL',
          detail: `Critical step '${missingStep}' not found in actual flow`,
        },
      ];
      if (i % 2 === 0) {
        deviations.push({
          type: 'OUT_OF_SEQUENCE',
          severity: 'HIGH',
          detail: 'Steps appear out of standard order',
        });
        riskLevel = 'CRITICAL';
      }
    } else if (i < 22) {
      // ALERT
      processStatus = 'ALERT';
      riskLevel = 'HIGH';
      actualFlow = [...standardFlow];
      deviations = [];
      if (i % 3 === 0) {
        deviations.push({
          type: 'PRICE_CHANGE',
          severity: 'MEDIUM',
          detail: 'Net price was changed after approval',
        });
        riskLevel = 'MEDIUM';
      }
      if (i % 4 === 0) {
        deviations.push({
          type: 'LATE_APPROVAL',
          severity: 'HIGH',
          detail: "'approve purchase order' appears after 'goods receipt'",
        });
        riskLevel = 'HIGH';
      }
      if (i % 5 === 0) {
        deviations.push({
          type: 'QUANTITY_CHANGE',
          severity: 'MEDIUM',
          detail: 'Order quantity was changed',
        });
      }
      if (deviations.length === 0) {
        deviations.push({
          type: 'UNAUTHORIZED_CHANGE',
          severity: 'HIGH',
          detail: "Unauthorized change steps detected: ['change delivery date']",
        });
      }
    } else {
      // PASS
      processStatus = 'PASS';
      riskLevel = 'LOW';
      actualFlow = [...standardFlow];
      deviations = [];
    }

    const devScore =
      deviations.reduce((acc, d) => {
        const w = { CRITICAL: 40, HIGH: 25, MEDIUM: 10, LOW: 5 };
        return acc + (w[d.severity] || 0);
      }, 0);

    orders.push({
      Order_Number: orderNum,
      Customer: customer,
      Order_Date: orderDate,
      Process_Status: processStatus,
      Risk_Level: riskLevel,
      Deviation_Score: devScore,
      Deviation_Count: deviations.length,
      Deviation_Types: deviations.map((d) => d.type).join(', '),
      Deviations: deviations,
      Standard_Flow: standardFlow,
      Actual_Flow: actualFlow,
      Critical_Steps: criticalSteps,
      TAT_Hours: parseFloat((Math.random() * 96 + 2).toFixed(1)),
      ...rca,
    });
  }

  const blocked = orders.filter((o) => o.Process_Status === 'BLOCKED');
  const alert = orders.filter((o) => o.Process_Status === 'ALERT');
  const pass = orders.filter((o) => o.Process_Status === 'PASS');

  return {
    status: 'success',
    totalOrders: orders.length,
    heatmap: {
      CRITICAL: orders.filter((o) => o.Risk_Level === 'CRITICAL').length,
      HIGH: orders.filter((o) => o.Risk_Level === 'HIGH').length,
      MEDIUM: orders.filter((o) => o.Risk_Level === 'MEDIUM').length,
      LOW: orders.filter((o) => o.Risk_Level === 'LOW').length,
    },
    statusSummary: {
      BLOCKED: blocked.length,
      ALERT: alert.length,
      PASS: pass.length,
    },
    insights: [...blocked, ...alert].sort((a, b) => b.Deviation_Score - a.Deviation_Score).slice(0, 10),
    orders,
    summary: {
      total_orders: orders.length,
      blocked: blocked.length,
      alert: alert.length,
      pass: pass.length,
      high_risk: blocked.length + alert.length,
      avg_deviation_score: parseFloat(
        (orders.reduce((a, o) => a + o.Deviation_Score, 0) / orders.length).toFixed(2)
      ),
    },
    blocked_orders: blocked,
    high_risk_orders: [...blocked, ...alert],
  };
}
