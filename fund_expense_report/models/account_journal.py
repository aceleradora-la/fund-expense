# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models

FUND_SOURCES = [
    ("fondo_fijo", "Fondo fijo"),
    ("caja_chica", "Caja chica"),
    ("tarjeta", "Tarjeta de crédito"),
]
DEFAULT_FUND_SOURCE_BY_TYPE = {
    "bank": "fondo_fijo",
    "cash": "caja_chica",
    "credit": "tarjeta",
}


class AccountJournal(models.Model):
    _inherit = "account.journal"

    fund_expense_source = fields.Selection(
        selection=FUND_SOURCES,
        string="Fondo del Anexo I",
        compute="_compute_fund_expense_source",
        store=True,
        readonly=False,
        help="Qué casilla del recuadro Fondos del Anexo I marca un pago hecho desde "
        "este diario. Se propone según el tipo (banco: fondo fijo, efectivo: caja "
        "chica, tarjeta: tarjeta de crédito); vacío si el diario no es un fondo.",
    )

    @api.depends("type")
    def _compute_fund_expense_source(self):
        for journal in self:
            journal.fund_expense_source = DEFAULT_FUND_SOURCE_BY_TYPE.get(
                journal.type, False
            )
