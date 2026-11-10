# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fund_expense_batch_frequency = fields.Selection(
        related="company_id.fund_expense_batch_frequency", readonly=False
    )
    fund_expense_batch_user_id = fields.Many2one(
        related="company_id.fund_expense_batch_user_id", readonly=False
    )
    fund_expense_batch_last_period_end = fields.Date(
        related="company_id.fund_expense_batch_last_period_end"
    )
