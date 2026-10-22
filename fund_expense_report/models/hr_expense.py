# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class HrExpense(models.Model):
    _inherit = "hr.expense"

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
