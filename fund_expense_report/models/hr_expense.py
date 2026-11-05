# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, api, fields, models


class HrExpense(models.Model):
    _inherit = "hr.expense"

    def _default_payment_mode(self):
        # Casi siempre paga la empresa. El anticipo, en cambio, es siempre al
        # empleado (lo exige hr_expense_advance_clearing).
        if self.env.context.get("default_advance"):
            return "own_account"
        return "company_account"

    payment_mode = fields.Selection(default=_default_payment_mode)
    receipt_number = fields.Char(
        string="N° de comprobante",
        copy=False,
        help="Número del comprobante (factura, ticket o recibo) que respalda el gasto.",
    )
    # vendor_id ya existe en el núcleo; en las rendiciones se usa siempre,
    # no solo cuando paga la empresa.
    vendor_vat = fields.Char(
        string="CUIT del proveedor",
        related="vendor_id.vat",
    )

    @api.depends("sheet_id.fund_bill_ids")
    def _compute_state(self):
        # El núcleo marca "hecho" solo si la hoja tiene asientos propios.
        res = super()._compute_state()
        for expense in self:
            sheet = expense.sheet_id
            if sheet.state == "done" and sheet.fund_bill_ids:
                expense.state = "done"
        return res

    @api.onchange("advance")
    def onchange_advance(self):
        res = super().onchange_advance()
        if self.advance:
            self.payment_mode = "own_account"
        return res

    def _fund_expense_prepare_bill_line_vals(self):
        """Renglón de la factura del proveedor.

        Sin expense_id: con ese campo el núcleo toma el precio como impuesto
        incluido, y Administración tiene que poder corregir precio e impuestos
        como en cualquier factura. Por eso va el importe sin impuestos.
        """
        self.ensure_one()
        return {
            "name": self.name,
            "product_id": self.product_id.id,
            "account_id": self._get_base_account().id,
            "quantity": 1,
            "price_unit": self.untaxed_amount_currency,
            "tax_ids": [Command.set(self.tax_ids.ids)],
            "analytic_distribution": self.analytic_distribution,
        }
