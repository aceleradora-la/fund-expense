# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class FundExpenseBatchLine(models.Model):
    _name = "fund.expense.batch.line"
    _description = "Anexo en una conformidad"
    _order = "department_id, approval_date, id"
    _rec_name = "sheet_id"

    batch_id = fields.Many2one(
        comodel_name="fund.expense.batch",
        string="Conformidad",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    sheet_id = fields.Many2one(
        comodel_name="hr.expense.sheet",
        string="Anexo",
        required=True,
        ondelete="restrict",
        index=True,
    )
    employee_id = fields.Many2one(
        related="sheet_id.employee_id", string="Empleado", store=True
    )
    department_id = fields.Many2one(
        related="sheet_id.department_id", string="Área", store=True
    )
    approval_date = fields.Datetime(
        related="sheet_id.approval_date", string="Aprobado el", store=True
    )
    payment_mode = fields.Selection(related="sheet_id.payment_mode")
    fund_source = fields.Selection(related="sheet_id.fund_source", string="Fondos")
    sheet_state = fields.Selection(related="sheet_id.state", string="Estado del Anexo")
    currency_id = fields.Many2one(related="batch_id.currency_id")
    total_amount = fields.Monetary(
        related="sheet_id.total_amount", string="Importe", store=True
    )
    observed = fields.Boolean(string="Observado", readonly=True, copy=False)
    observation = fields.Text(string="Observación", readonly=True, copy=False)
    observed_by_id = fields.Many2one(
        comodel_name="res.users", string="Observado por", readonly=True, copy=False
    )
    observed_date = fields.Datetime(
        string="Fecha de observación", readonly=True, copy=False
    )

    _sql_constraints = [
        (
            "sheet_unique",
            "UNIQUE (sheet_id)",
            "Cada Anexo puede estar en una sola conformidad.",
        ),
    ]

    # Armado: solo con la conformidad en borrador y sin pedir la aprobación

    def _fund_batch_check_editable(self, batches):
        locked = batches.filtered(lambda batch: not batch._fund_batch_is_editable())
        if locked:
            raise UserError(
                self.env._(
                    "La conformidad %s ya se envió a aprobar: no se pueden sumar ni "
                    "quitar Anexos.",
                    ", ".join(locked.mapped("name")),
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self._fund_batch_check_editable(lines.batch_id)
        not_approved = lines.sheet_id.filtered(
            lambda sheet: sheet.approval_state != "approve"
        )
        if not_approved:
            raise UserError(
                self.env._(
                    "Solo entran Anexos aprobados. No lo están: %s",
                    ", ".join(not_approved.mapped("name")),
                )
            )
        return lines

    def write(self, vals):
        if {"batch_id", "sheet_id"} & set(vals):
            self._fund_batch_check_editable(self.batch_id)
        res = super().write(vals)
        if "batch_id" in vals:
            self._fund_batch_check_editable(self.batch_id)
        return res

    def unlink(self):
        if not self.env.context.get("fund_batch_release"):
            self._fund_batch_check_editable(self.batch_id)
        return super().unlink()

    def action_open_sheet(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.expense.sheet",
            "res_id": self.sheet_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

    # Observaciones del Gerente

    def _fund_batch_check_can_observe(self):
        for line in self:
            batch = line.batch_id
            if batch.state != "draft" or not batch.can_review:
                raise UserError(
                    self.env._(
                        "Solo quien tiene que dar la conformidad %s puede observar "
                        "sus Anexos, mientras está pendiente.",
                        batch.name,
                    )
                )

    def action_observe(self):
        self.ensure_one()
        self._fund_batch_check_can_observe()
        return {
            "name": self.env._("Observar Anexo"),
            "type": "ir.actions.act_window",
            "res_model": "fund.expense.batch.observe",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_line_id": self.id,
                "default_observation": self.observation,
            },
        }

    def _fund_batch_observe(self, observation):
        """Marcar el Anexo como observado y avisarle a Administración.

        En sudo: el Gerente solo lee los Anexos. El aviso es una actividad en
        el Anexo para el responsable de la conformidad.
        """
        self._fund_batch_check_can_observe()
        for line in self.sudo():
            line.write(
                {
                    "observed": True,
                    "observation": observation,
                    "observed_by_id": self.env.user.id,
                    "observed_date": fields.Datetime.now(),
                }
            )
            sheet = line.sheet_id
            # Markup escapa el nombre y el texto de la observación.
            sheet.message_post(
                body=Markup("%s<br/>%s")
                % (
                    self.env._(
                        "Observado en la conformidad %(batch)s por %(user)s:",
                        batch=line.batch_id.name,
                        user=self.env.user.name,
                    ),
                    Markup("<br/>").join(observation.splitlines()),
                ),
                subtype_xmlid="mail.mt_note",
            )
            responsible = line.batch_id.user_id
            if responsible:
                sheet.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=responsible.id,
                    summary=self.env._("Observación de %s", line.batch_id.name),
                    note=observation,
                )

    def action_clear_observation(self):
        self._fund_batch_check_can_observe()
        for line in self.sudo().filtered("observed"):
            line.write(
                {
                    "observed": False,
                    "observation": False,
                    "observed_by_id": False,
                    "observed_date": False,
                }
            )
            line.sheet_id.message_post(
                body=self.env._(
                    "%(user)s quitó la observación de la conformidad %(batch)s.",
                    user=self.env.user.name,
                    batch=line.batch_id.name,
                ),
                subtype_xmlid="mail.mt_note",
            )
        return True
