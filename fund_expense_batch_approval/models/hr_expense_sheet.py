# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError


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

    def action_fund_batch_create(self):
        """Crear una conformidad con los Anexos elegidos en la lista.

        El período va de la primera a la última fecha de aprobación. La
        conformidad queda en borrador para revisarla antes de enviarla.
        """
        if not self.env.user.has_group("hr_expense.group_hr_expense_manager"):
            raise AccessError(
                self.env._("Solo Administración puede armar conformidades.")
            )
        if not self:
            raise UserError(self.env._("Elegí al menos un Anexo."))
        not_approved = self.filtered(lambda sheet: sheet.approval_state != "approve")
        if not_approved:
            raise UserError(
                self.env._(
                    "Solo entran Anexos aprobados. No lo están: %s",
                    ", ".join(not_approved.mapped("name")),
                )
            )
        taken = self.filtered("fund_batch_line_ids")
        if taken:
            raise UserError(
                self.env._(
                    "Estos Anexos ya están en una conformidad:\n%s",
                    "\n".join(
                        f"- {sheet.name}: {sheet.fund_batch_id.name}" for sheet in taken
                    ),
                )
            )
        if len(self.company_id) > 1:
            raise UserError(
                self.env._("Los Anexos de una conformidad tienen que ser de una compañía.")
            )
        dates = [fields.Date.to_date(sheet.approval_date) for sheet in self]
        batch = (
            self.env["fund.expense.batch"]
            .with_company(self.company_id)
            .create(
                {
                    "company_id": self.company_id.id,
                    "date_from": min(dates),
                    "date_to": max(dates),
                    "line_ids": [
                        Command.create({"sheet_id": sheet.id})
                        for sheet in self.sorted("approval_date")
                    ],
                }
            )
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "fund.expense.batch",
            "res_id": batch.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

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
