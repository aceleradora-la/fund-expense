# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    fund_batch_line_ids = fields.One2many(
        comodel_name="fund.expense.batch.line",
        inverse_name="sheet_id",
        string="Conformidades",
        readonly=True,
        copy=False,
    )
    fund_batch_id = fields.Many2one(
        comodel_name="fund.expense.batch",
        string="Conformidad",
        compute="_compute_fund_conformity",
        store=True,
        compute_sudo=True,
    )
    fund_conformity = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("conformed", "Conforme"),
            ("observed", "Observado"),
        ],
        string="Conformidad del Gerente",
        compute="_compute_fund_conformity",
        store=True,
        compute_sudo=True,
    )
    fund_batch_observation = fields.Text(
        string="Observación del Gerente",
        compute="_compute_fund_batch_observation",
        compute_sudo=True,
    )

    @api.depends("fund_batch_line_ids.observation")
    def _compute_fund_batch_observation(self):
        for sheet in self:
            sheet.fund_batch_observation = sheet.fund_batch_line_ids[:1].observation

    @api.depends("fund_batch_line_ids.batch_id.state", "fund_batch_line_ids.observed")
    def _compute_fund_conformity(self):
        for sheet in self:
            line = sheet.fund_batch_line_ids[:1]
            sheet.fund_batch_id = line.batch_id
            if not line:
                sheet.fund_conformity = False
            elif line.observed:
                sheet.fund_conformity = "observed"
            elif line.batch_id.state == "approved":
                sheet.fund_conformity = "conformed"
            else:
                sheet.fund_conformity = "pending"

    def _fund_batch_release(self):
        """Antes de volver a borrador o rechazar un Anexo aprobado.

        Si está en una conformidad todavía en armado, sale de ella. Si la
        conformidad ya se envió o ya se dio, no se puede: el Gerente estaría
        firmando algo que cambió.
        """
        lines = self.sudo().fund_batch_line_ids
        locked = lines.filtered(lambda line: not line.batch_id._fund_batch_is_editable())
        if locked:
            raise UserError(
                self.env._(
                    "El Anexo %(sheet)s está en la conformidad %(batch)s, que ya se "
                    "envió al Gerente: no se puede volver atrás.",
                    sheet=locked[0].sheet_id.name,
                    batch=locked[0].batch_id.name,
                )
            )
        lines.with_context(fund_batch_release=True).unlink()

    def _do_reset_approval(self):
        self._fund_batch_release()
        return super()._do_reset_approval()

    def _do_refuse(self, reason):
        self._fund_batch_release()
        return super()._do_refuse(reason)
