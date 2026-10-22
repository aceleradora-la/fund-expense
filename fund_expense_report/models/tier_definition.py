# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class TierDefinition(models.Model):
    _inherit = "tier.definition"

    # Qué firma del Anexo I representa cada nivel: el PDF la completa con
    # quien aprobó ese nivel. Así no depende del orden ni del nombre.
    fund_expense_signature = fields.Selection(
        selection=[
            ("area", "2. Responsable del área"),
            ("afm", "3. Gerencia Adm. y Fin."),
        ],
        string="Firma en el Anexo I",
        help="En las rendiciones de fondos (hojas de gastos), la firma del "
        "Anexo I que corresponde a este nivel.",
    )
