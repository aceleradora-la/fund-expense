# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class FundExpenseBatchObserve(models.TransientModel):
    _name = "fund.expense.batch.observe"
    _description = "Observar un Anexo de la conformidad"

    line_id = fields.Many2one(
        comodel_name="fund.expense.batch.line", required=True, ondelete="cascade"
    )
    sheet_id = fields.Many2one(related="line_id.sheet_id", string="Anexo")
    observation = fields.Text(string="Observación", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.line_id._fund_batch_observe(self.observation)
        return {"type": "ir.actions.act_window_close"}
