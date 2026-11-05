# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    fund_expense_sheet_id = fields.Many2one(
        comodel_name="hr.expense.sheet",
        string="Anexo I",
        copy=False,
        readonly=True,
        index="btree_not_null",
        ondelete="set null",
        help="Solicitud aprobada que originó esta factura de proveedor.",
    )
    fund_expense_payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="fund_expense_bill_id",
        string="Pagos sin factura",
        help="Pagos hechos antes de que llegara la factura. Se concilian solos al "
        "confirmarla.",
    )

    def action_register_payment(self):
        action = super().action_register_payment()
        journal = self.fund_expense_sheet_id.fund_journal_id
        if len(journal) == 1 and isinstance(action, dict):
            action["context"] = dict(
                action.get("context") or {}, default_journal_id=journal.id
            )
        return action

    def action_fund_expense_pay_without_bill(self):
        """Pagar al proveedor antes de que llegue la factura.

        Abre el pago habitual con los datos del borrador, sin confirmarlo: las
        retenciones y el medio de pago los define Administración.
        """
        self.ensure_one()
        if self.state != "draft" or not self.fund_expense_sheet_id:
            raise UserError(
                self.env._(
                    "Solo se paga sin factura el borrador que viene de un Anexo I."
                )
            )
        context = {
            "default_payment_type": "outbound",
            "default_partner_type": "supplier",
            "default_partner_id": self.commercial_partner_id.id,
            "default_amount": self.amount_total,
            "default_to_pay_amount": self.amount_total,
            "default_currency_id": self.currency_id.id,
            "default_company_id": self.company_id.id,
            "default_memo": self.invoice_origin,
            "default_fund_expense_bill_id": self.id,
        }
        journal = self.fund_expense_sheet_id.fund_journal_id
        if journal:
            context["default_journal_id"] = journal.id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Pago sin factura"),
            "res_model": "account.payment",
            "view_mode": "form",
            "views": [(False, "form")],
            "context": context,
        }

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._fund_expense_reconcile_payments()
        return posted

    def _fund_expense_reconcile_payments(self):
        """Al confirmar la factura, aplicarle el pago hecho antes.

        Si está bloqueada por otra aprobación se deja para después: la concilia
        Administración desde los créditos pendientes de la factura.
        """
        bills = self.sudo().filtered(
            lambda bill: bill.fund_expense_payment_ids
            and bill.payment_state != "blocked"
        )
        for bill in bills:
            payments = bill.fund_expense_payment_ids.filtered(
                lambda payment: payment.state in ("in_process", "paid")
            )
            payable = bill.line_ids.filtered(
                lambda line: line.account_id.account_type == "liability_payable"
                and not line.reconciled
            )
            paid_lines = payments.move_id.line_ids.filtered(
                lambda line: line.account_id in payable.account_id
                and not line.reconciled
            )
            if paid_lines:
                (payable | paid_lines).reconcile()
            # Sin cuenta transitoria el pago no tiene asiento hasta conciliar el
            # banco: se vincula como hace el núcleo.
            unposted = payments.filtered(lambda payment: not payment.move_id)
            if unposted:
                bill.matched_payment_ids = [
                    Command.link(payment.id) for payment in unposted
                ]
