# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, api, fields, models


# Gastos / Todos los aprobadores (lo tiene Administración): carga lo que paga
# la empresa.
FUND_ADMIN_GROUP = "hr_expense.group_hr_expense_user"


class HrExpense(models.Model):
    _inherit = "hr.expense"

    def _default_payment_mode(self):
        # El anticipo es siempre al empleado (lo exige hr_expense_advance_clearing).
        if self.env.context.get("default_advance"):
            return "own_account"
        # Renglón nuevo en un Anexo que ya tiene renglones: el mismo pagador
        # (el núcleo no deja mezclar).
        sheet_payment_mode = self.env.context.get("fund_sheet_payment_mode")
        if sheet_payment_mode:
            return sheet_payment_mode
        # Administración carga lo que paga la empresa; el empleado que sube sus
        # tickets (también desde el celular), lo que pagó él.
        if self.env.user.has_group(FUND_ADMIN_GROUP):
            return "company_account"
        return "own_account"

    payment_mode = fields.Selection(default=_default_payment_mode)
    fund_event = fields.Char(
        string="Viaje o evento",
        help="Para juntar en un mismo Anexo los gastos de un viaje o un evento. "
        "Si todos los gastos de un reporte tienen el mismo, es su concepto.",
    )
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

    def _get_default_expense_sheet_values(self):
        # Si los gastos elegidos mezclan pagadores, el núcleo arma dos Anexos:
        # se los distingue en el concepto.
        values = super()._get_default_expense_sheet_values()
        if len(values) > 1:
            labels = {
                "company_account": self.env._("Paga la empresa"),
                "own_account": self.env._("Reintegro"),
            }
            for vals in values:
                expense_ids = vals["expense_line_ids"][0][2]
                payment_mode = self.browse(expense_ids[:1]).payment_mode
                if vals.get("name") and payment_mode in labels:
                    vals["name"] = f"{vals['name']} - {labels[payment_mode]}"
        return values

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
