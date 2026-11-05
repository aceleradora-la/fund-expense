# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    fund_expense_bill_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura pendiente (Anexo I)",
        copy=False,
        readonly=True,
        index="btree_not_null",
        ondelete="set null",
        help="Borrador de factura al que corresponde este pago hecho antes de "
        "recibirla. Se concilia solo al confirmarla.",
    )
