"""Bank account model"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Date, Text, ForeignKey, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from accounting.db.database import Base


class BankAccount(Base):
    """Bank account model"""
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    account_name = Column(String(255), nullable=False)
    account_number = Column(String(50), nullable=True)
    account_type = Column(String(50), nullable=True)  # checking, savings, credit_card, etc.
    institution_name = Column(String(255), nullable=True)
    routing_number = Column(String(20), nullable=True)
    gl_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    opening_balance = Column(Numeric(15, 2), nullable=True)
    current_balance = Column(Numeric(15, 2), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)

    # Sync configuration
    sync_method = Column(String(20), nullable=False, default="manual")  # manual, plaid, api
    auto_sync_enabled = Column(Boolean, nullable=False, default=False)
    last_sync_date = Column(DateTime, nullable=True)

    # Plaid integration fields
    plaid_access_token = Column(Text, nullable=True)  # Should be encrypted
    plaid_item_id = Column(String(255), nullable=True)
    plaid_account_id = Column(String(255), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    area = relationship("Area", back_populates="bank_accounts")
    gl_account = relationship("Account")
    transactions = relationship("BankTransaction", back_populates="bank_account", cascade="all, delete-orphan")
    imports = relationship("BankStatementImport", back_populates="bank_account", cascade="all, delete-orphan")
    reconciliations = relationship("BankReconciliation", back_populates="bank_account", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bank_account")
    check_batches = relationship("CheckBatch", back_populates="bank_account")
    ach_batches = relationship("ACHBatch", back_populates="bank_account")
    matching_rules = relationship("BankMatchingRule", back_populates="bank_account", cascade="all, delete-orphan")
    statements = relationship("BankStatement", cascade="all, delete-orphan")


class BankStatementImport(Base):
    """Bank statement import model"""
    __tablename__ = "bank_statement_imports"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    import_date = Column(DateTime, nullable=False, server_default=func.current_timestamp(), index=True)
    file_name = Column(String(255), nullable=True)
    file_format = Column(String(20), nullable=True)  # csv, ofx, qfx, qbo
    import_method = Column(String(20), nullable=False, default="manual")  # manual, plaid, scheduled
    statement_date = Column(Date, nullable=True)
    beginning_balance = Column(Numeric(15, 2), nullable=True)
    ending_balance = Column(Numeric(15, 2), nullable=True)
    transaction_count = Column(Integer, nullable=True)
    imported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    bank_account = relationship("BankAccount", back_populates="imports")
    transactions = relationship("BankTransaction", back_populates="import_record")


class BankTransaction(Base):
    """Bank transaction model"""
    __tablename__ = "bank_transactions"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    import_id = Column(Integer, ForeignKey("bank_statement_imports.id", ondelete="SET NULL"), nullable=True)
    transaction_date = Column(Date, nullable=False, index=True)
    post_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    payee = Column(String(255), nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)
    transaction_type = Column(String(50), nullable=True)  # debit, credit, check, atm, etc.
    check_number = Column(String(50), nullable=True)
    reference_number = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    memo = Column(Text, nullable=True)

    # Reconciliation status
    status = Column(String(20), nullable=False, default="unreconciled", index=True)
    reconciled_date = Column(Date, nullable=True)

    # Matching information
    matched_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    matched_journal_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="SET NULL"), nullable=True)
    match_type = Column(String(50), nullable=True)  # exact, fuzzy, manual, auto
    match_confidence = Column(Numeric(5, 2), nullable=True)  # 0.00 to 100.00

    # Plaid-specific fields
    plaid_transaction_id = Column(String(255), nullable=True, index=True)
    plaid_category = Column(ARRAY(String), nullable=True)
    plaid_pending = Column(Boolean, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Statement relationship (added in migration 20251020_0200)
    statement_id = Column(Integer, ForeignKey("bank_statements.id", ondelete="SET NULL"), nullable=True, index=True)

    # Suggestion fields (added in migration 20251020_0200)
    suggested_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    suggested_by_rule_id = Column(Integer, ForeignKey("bank_matching_rules_v2.id", ondelete="SET NULL"), nullable=True)
    suggestion_confidence = Column(Numeric(5, 2), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # Composite matching (added in migration 20251020_2200)
    is_composite_match = Column(Boolean, nullable=False, server_default='false')

    # Relationships
    bank_account = relationship("BankAccount", back_populates="transactions")
    import_record = relationship("BankStatementImport", back_populates="transactions")
    matched_journal_entry = relationship("JournalEntry", foreign_keys=[matched_journal_entry_id])
    matched_journal_line = relationship("JournalEntryLine", foreign_keys=[matched_journal_line_id])
    suggested_account = relationship("Account", foreign_keys=[suggested_account_id])
    statement = relationship("BankStatement", back_populates="transactions")
    composite_matches = relationship("BankTransactionCompositeMatch", back_populates="bank_transaction", cascade="all, delete-orphan")


class BankReconciliation(Base):
    """Bank reconciliation model"""
    __tablename__ = "bank_reconciliations"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    reconciliation_date = Column(Date, nullable=False, index=True)
    statement_date = Column(Date, nullable=False)
    beginning_balance = Column(Numeric(15, 2), nullable=False)
    ending_balance = Column(Numeric(15, 2), nullable=False)
    cleared_balance = Column(Numeric(15, 2), nullable=True)
    book_balance = Column(Numeric(15, 2), nullable=True)
    difference = Column(Numeric(15, 2), nullable=True)
    status = Column(String(20), nullable=False, default="in_progress", index=True)
    reconciled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reconciled_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())

    # Relationships
    bank_account = relationship("BankAccount", back_populates="reconciliations")
    items = relationship("BankReconciliationItem", back_populates="reconciliation", cascade="all, delete-orphan")


class BankReconciliationItem(Base):
    """Bank reconciliation item model"""
    __tablename__ = "bank_reconciliation_items"

    id = Column(Integer, primary_key=True, index=True)
    reconciliation_id = Column(Integer, ForeignKey("bank_reconciliations.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=True)
    journal_entry_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="CASCADE"), nullable=True)
    cleared_date = Column(Date, nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)
    item_type = Column(String(50), nullable=True)  # bank_transaction, journal_entry, adjustment
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())

    # Relationships
    reconciliation = relationship("BankReconciliation", back_populates="items")
    bank_transaction = relationship("BankTransaction")
    journal_line = relationship("JournalEntryLine")


class BankMatchingRule(Base):
    """Bank matching rule model for auto-categorization"""
    __tablename__ = "bank_matching_rules"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    rule_name = Column(String(255), nullable=False)
    match_field = Column(String(50), nullable=False)  # description, payee, amount, check_number
    match_operator = Column(String(20), nullable=False)  # contains, equals, starts_with, ends_with, regex
    match_value = Column(Text, nullable=False)
    target_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    target_payee = Column(String(255), nullable=True)
    auto_apply = Column(Boolean, nullable=False, default=False)
    priority = Column(Integer, nullable=False, default=0, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    times_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    bank_account = relationship("BankAccount", back_populates="matching_rules")
    target_account = relationship("Account")


class BankStatement(Base):
    """Bank statement model - monthly periods with reconciliation workflow"""
    __tablename__ = "bank_statements"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    statement_period_start = Column(Date, nullable=False, index=True)
    statement_period_end = Column(Date, nullable=False, index=True)
    statement_date = Column(Date, nullable=False)
    opening_balance = Column(Numeric(15, 2), nullable=False)
    closing_balance = Column(Numeric(15, 2), nullable=False)

    # Workflow status
    status = Column(String(20), nullable=False, default="draft", index=True)  # draft, in_progress, balanced, locked
    gl_balance = Column(Numeric(15, 2), nullable=True)
    cleared_balance = Column(Numeric(15, 2), nullable=True)  # Added in migration 20251020_2200
    difference = Column(Numeric(15, 2), nullable=True)

    # Reconciliation tracking
    reconciliation_date = Column(Date, nullable=True)  # Added in migration 20251020_2200
    reconciled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reconciled_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    locked_reason = Column(Text, nullable=True)

    # Audit trail
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    bank_account = relationship("BankAccount")
    transactions = relationship("BankTransaction", back_populates="statement")
    snapshots = relationship("BankStatementSnapshot", back_populates="statement", cascade="all, delete-orphan")


class BankTransactionMatch(Base):
    """Audit trail for bank transaction matches"""
    __tablename__ = "bank_transaction_matches"

    id = Column(Integer, primary_key=True, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    journal_entry_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="SET NULL"), nullable=True, index=True)

    # Match metadata
    match_type = Column(String(50), nullable=False)  # exact, fuzzy, composite, manual, rule_based
    confidence_score = Column(Numeric(5, 2), nullable=True)
    match_reason = Column(Text, nullable=True)
    amount_difference = Column(Numeric(15, 2), nullable=True)
    date_difference = Column(Integer, nullable=True)

    # Rule and confirmation
    matched_by_rule_id = Column(Integer, ForeignKey("bank_matching_rules_v2.id", ondelete="SET NULL"), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # Clearing journal entries
    clearing_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    adjustment_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)

    # Status
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, confirmed, cleared, rejected

    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    bank_transaction = relationship("BankTransaction")
    journal_entry_line = relationship("JournalEntryLine")
    matched_by_rule = relationship("BankMatchingRuleV2")
    clearing_journal_entry = relationship("JournalEntry", foreign_keys=[clearing_journal_entry_id])
    adjustment_journal_entry = relationship("JournalEntry", foreign_keys=[adjustment_journal_entry_id])


class BankCompositeMatch(Base):
    """Composite matches for many-to-one or one-to-many scenarios (OLD - from Phase 1A)"""
    __tablename__ = "bank_composite_matches"

    id = Column(Integer, primary_key=True, index=True)
    match_group_id = Column(String(50), nullable=False, index=True)  # UUID to group related matches
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=True, index=True)
    journal_entry_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="CASCADE"), nullable=True, index=True)
    match_amount = Column(Numeric(15, 2), nullable=False)
    composite_type = Column(String(50), nullable=False)  # many_to_one, one_to_many

    confirmed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")

    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())

    # Relationships
    bank_transaction = relationship("BankTransaction")
    journal_entry_line = relationship("JournalEntryLine")


class BankTransactionCompositeMatch(Base):
    """
    Phase 1B composite matching - links one bank transaction to multiple journal entry lines
    Used for matching batch deposits to multiple DSS entries (e.g., 3 days CC sales → 1 deposit)
    """
    __tablename__ = "bank_transaction_composite_matches"

    id = Column(Integer, primary_key=True, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    journal_entry_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    match_type = Column(String(50), nullable=True)  # composite, partial, full
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    bank_transaction = relationship("BankTransaction", back_populates="composite_matches")
    journal_entry_line = relationship("JournalEntryLine")
    created_by_user = relationship("User")


class BankMatchingRuleV2(Base):
    """Enhanced matching rules with JSON conditions and flexible actions"""
    __tablename__ = "bank_matching_rules_v2"

    id = Column(Integer, primary_key=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_name = Column(String(255), nullable=False)
    rule_type = Column(String(50), nullable=False, index=True)  # recurring_deposit, recurring_expense, vendor_match, composite_match
    priority = Column(Integer, nullable=False, default=0, index=True)

    # Conditions (flexible JSON structure)
    conditions = Column(JSONB, nullable=False)

    # Actions
    action_type = Column(String(50), nullable=False)  # suggest_gl_account, auto_match, create_expense
    target_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    requires_confirmation = Column(Boolean, nullable=False, default=True)

    # Fee/adjustment handling
    fee_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    fee_calculation = Column(String(50), nullable=True)  # fixed_amount, percentage, difference
    fee_amount = Column(Numeric(15, 2), nullable=True)
    fee_percentage = Column(Numeric(5, 2), nullable=True)

    # Statistics
    active = Column(Boolean, nullable=False, default=True, index=True)
    times_suggested = Column(Integer, nullable=False, default=0)
    times_confirmed = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    bank_account = relationship("BankAccount")
    area = relationship("Area")
    target_account = relationship("Account", foreign_keys=[target_account_id])
    fee_account = relationship("Account", foreign_keys=[fee_account_id])


class BankStatementSnapshot(Base):
    """Immutable snapshots of statement state for audit trail"""
    __tablename__ = "bank_statement_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    statement_id = Column(Integer, ForeignKey("bank_statements.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_type = Column(String(50), nullable=False, index=True)  # reconciled, locked, unlocked, edited
    snapshot_data = Column(JSONB, nullable=False)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    reason = Column(Text, nullable=True)

    # Relationships
    statement = relationship("BankStatement", back_populates="snapshots")
