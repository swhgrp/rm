"""
Import all models to ensure they are registered with SQLAlchemy
Import order matters to avoid circular dependencies
"""
# Base models first
from accounting.models.area import Area
from accounting.models.permission import Permission
from accounting.models.role import Role
from accounting.models.user import User, UserSession

# Then other models
from accounting.models.account import Account, AccountType, CashFlowClass
from accounting.models.account_group import AccountGroup, ReportSection
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus
from accounting.models.account_balance import AccountBalance
from accounting.models.sync_log import InventorySyncLog, SyncStatus
from accounting.models.cogs import COGSTransaction, TransactionType
from accounting.models.vendor import Vendor
from accounting.models.vendor_alias import VendorAlias
from accounting.models.vendor_bill import VendorBill, VendorBillLine, BillPayment, BillStatus, PaymentMethod
from accounting.models.customer import Customer
from accounting.models.customer_invoice import CustomerInvoice, CustomerInvoiceLine, InvoicePayment, InvoiceStatus
from accounting.models.recurring_invoice import RecurringInvoice, RecurringInvoiceLineItem
from accounting.models.daily_sales_summary import DailySalesSummary
from accounting.models.bank_account import (
    BankAccount,
    BankStatementImport,
    BankTransaction,
    BankReconciliation,
    BankReconciliationItem,
    BankMatchingRule,
    BankStatement,
    BankTransactionMatch,
    BankCompositeMatch,
    BankTransactionCompositeMatch,
    BankMatchingRuleV2,
    BankStatementSnapshot
)
from accounting.models.gl_learning import VendorGLMapping, DescriptionPatternMapping, RecurringTransactionPattern
from accounting.models.banking_dashboard import (
    DailyCashPosition,
    CashFlowTransaction,
    BankingAlert,
    ReconciliationHealthMetric,
    LocationCashFlowSummary,
    CashFlowCategory,
    AlertSeverity,
    AlertType
)
from accounting.models.general_dashboard import (
    DailyFinancialSnapshot,
    MonthlyPerformanceSummary,
    DashboardAlert,
    ExpenseCategorySummary,
    DashboardAlertType
)
from accounting.models.payment import (
    Payment,
    PaymentApplication,
    CheckBatch,
    ACHBatch,
    CheckNumberRegistry,
    PaymentSchedule,
    PaymentApproval,
    PaymentDiscount
)
from accounting.models.budget import (
    Budget,
    BudgetPeriod,
    BudgetLine,
    BudgetTemplate,
    BudgetTemplateLine,
    BudgetRevision,
    BudgetAlert,
    BudgetStatus,
    BudgetPeriodType
)
from accounting.models.pos import (
    POSConfiguration,
    POSDailySalesCache,
    POSCategoryGLMapping
)
from accounting.models.system_setting import SystemSetting
from accounting.models.safe_transaction import SafeTransaction
from accounting.gl_review.models import GLAnomalyFlag, GLAccountBaseline

__all__ = [
    "Area",
    "Permission",
    "Role",
    "User",
    "UserSession",
    "Account",
    "AccountType",
    "CashFlowClass",
    "AccountGroup",
    "ReportSection",
    "JournalEntry",
    "JournalEntryLine",
    "JournalEntryStatus",
    "FiscalPeriod",
    "FiscalPeriodStatus",
    "AccountBalance",
    "InventorySyncLog",
    "SyncStatus",
    "COGSTransaction",
    "TransactionType",
    "Vendor",
    "VendorAlias",
    "VendorBill",
    "VendorBillLine",
    "BillPayment",
    "BillStatus",
    "PaymentMethod",
    "Customer",
    "CustomerInvoice",
    "CustomerInvoiceLine",
    "InvoicePayment",
    "InvoiceStatus",
    "RecurringInvoice",
    "RecurringInvoiceLineItem",
    "DailySalesSummary",
    "BankAccount",
    "BankStatementImport",
    "BankTransaction",
    "BankReconciliation",
    "BankReconciliationItem",
    "BankMatchingRule",
    "BankStatement",
    "BankTransactionMatch",
    "BankCompositeMatch",
    "BankTransactionCompositeMatch",
    "BankMatchingRuleV2",
    "BankStatementSnapshot",
    "VendorGLMapping",
    "DescriptionPatternMapping",
    "RecurringTransactionPattern",
    "DailyCashPosition",
    "CashFlowTransaction",
    "BankingAlert",
    "ReconciliationHealthMetric",
    "LocationCashFlowSummary",
    "CashFlowCategory",
    "AlertSeverity",
    "AlertType",
    "DailyFinancialSnapshot",
    "MonthlyPerformanceSummary",
    "DashboardAlert",
    "ExpenseCategorySummary",
    "DashboardAlertType",
    "Payment",
    "PaymentApplication",
    "CheckBatch",
    "ACHBatch",
    "CheckNumberRegistry",
    "PaymentSchedule",
    "PaymentApproval",
    "PaymentDiscount",
    "Budget",
    "BudgetPeriod",
    "BudgetLine",
    "BudgetTemplate",
    "BudgetTemplateLine",
    "BudgetRevision",
    "BudgetAlert",
    "BudgetStatus",
    "BudgetPeriodType",
    "POSConfiguration",
    "POSDailySalesCache",
    "POSCategoryGLMapping",
    "SystemSetting",
    "SafeTransaction",
    "GLAnomalyFlag",
    "GLAccountBaseline",
]
