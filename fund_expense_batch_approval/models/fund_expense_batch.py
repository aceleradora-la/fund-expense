# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from collections import defaultdict
from datetime import datetime, time

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_amount


class FundExpenseBatch(models.Model):
    """Conformidad del Gerente sobre los Anexos I ya aprobados.

    Es posterior: los Anexos ya tienen sus dos firmas y pueden estar pagados.
    El Gerente aprueba el lote entero y, si algo no le cierra, observa ese
    Anexo con un motivo; la observación le llega a Administración como
    actividad en el Anexo. El lote no bloquea ni deshace nada.
    """

    _name = "fund.expense.batch"
    _description = "Conformidad de rendiciones"
    _inherit = ["mail.thread", "mail.activity.mixin", "tier.validation"]
    _order = "date_to desc, id desc"

    _tier_validation_manual_config = False
    _state_from = ["draft"]
    _state_to = ["approved"]
    _cancel_state = "cancel"

    name = fields.Char(
        string="Número", default="/", readonly=True, copy=False, required=True
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="Desde",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        tracking=True,
    )
    date_to = fields.Date(
        string="Hasta",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="Entran los Anexos aprobados hasta esta fecha que todavía no estén en "
        "otra conformidad, aunque sean de antes del período.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable",
        default=lambda self: self.env.user,
        tracking=True,
        help="Recibe como actividad en el Anexo las observaciones del Gerente.",
    )
    line_ids = fields.One2many(
        comodel_name="fund.expense.batch.line",
        inverse_name="batch_id",
        string="Anexos",
        copy=False,
    )
    state = fields.Selection(
        selection=[("draft", "Borrador"), ("approved", "Conforme")],
        string="Estado",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        comodel_name="res.users", string="Conformidad de", readonly=True, copy=False
    )
    approved_date = fields.Datetime(
        string="Fecha de conformidad", readonly=True, copy=False
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    sheet_count = fields.Integer(string="Cantidad de Anexos", compute="_compute_totals")
    observed_count = fields.Integer(string="Observados", compute="_compute_totals")
    amount_total = fields.Monetary(string="Total", compute="_compute_totals")
    summary_html = fields.Html(
        string="Totales", compute="_compute_summary_html", sanitize=False
    )

    _sql_constraints = [
        (
            "date_check",
            "CHECK (date_from <= date_to)",
            "La fecha Desde no puede ser posterior a la fecha Hasta.",
        ),
    ]

    @api.depends("line_ids.total_amount", "line_ids.observed")
    def _compute_totals(self):
        for batch in self:
            batch.sheet_count = len(batch.line_ids)
            batch.observed_count = len(batch.line_ids.filtered("observed"))
            batch.amount_total = sum(batch.line_ids.mapped("total_amount"))

    @api.depends(
        "line_ids.total_amount", "line_ids.department_id", "line_ids.fund_source"
    )
    def _compute_summary_html(self):
        for batch in self:
            batch.summary_html = batch._fund_batch_summary_html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                company = self.env["res.company"].browse(
                    vals.get("company_id") or self.env.company.id
                )
                vals["name"] = self.env["ir.sequence"].sudo().with_company(
                    company
                ).next_by_code("fund.expense.batch") or "/"
        return super().create(vals_list)

    def unlink(self):
        if self.filtered(lambda batch: batch.state != "draft"):
            raise UserError(
                self.env._("No se puede borrar una conformidad ya dada.")
            )
        return super().unlink()

    # Armado

    def _fund_batch_is_editable(self):
        """Se pueden sumar o quitar Anexos solo antes de pedir la aprobación."""
        self.ensure_one()
        return self.state == "draft" and not self.review_ids

    @api.model
    def _fund_batch_pending_domain(self, company, date_to):
        return [
            ("company_id", "=", company.id),
            ("approval_state", "=", "approve"),
            ("approval_date", "<=", datetime.combine(date_to, time.max)),
            ("fund_batch_line_ids", "=", False),
        ]

    def action_add_pending(self):
        """Sumar todos los Anexos aprobados que todavía no tienen conformidad."""
        for batch in self:
            if not batch._fund_batch_is_editable():
                raise UserError(
                    self.env._(
                        "La conformidad %s ya se envió a aprobar: para cambiar los "
                        "Anexos hay que reiniciar la validación.",
                        batch.name,
                    )
                )
            sheets = (
                self.env["hr.expense.sheet"]
                .sudo()
                .search(
                    self._fund_batch_pending_domain(batch.company_id, batch.date_to),
                    order="approval_date, id",
                )
            )
            self.env["fund.expense.batch.line"].create(
                [{"batch_id": batch.id, "sheet_id": sheet.id} for sheet in sheets]
            )
        return True

    def action_open_sheets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hr_expense.action_hr_expense_sheet_all"
        )
        action.update(
            {
                "domain": [("id", "in", self.line_ids.sheet_id.ids)],
                "context": {"group_by": ["department_id"], "create": False},
                "name": self.env._("Anexos de %s", self.name),
            }
        )
        return action

    # Aprobación

    def request_validation(self):
        empty = self.filtered(lambda batch: not batch.line_ids)
        if empty:
            raise UserError(
                self.env._(
                    "La conformidad %s no tiene Anexos: no hay nada para aprobar.",
                    ", ".join(empty.mapped("name")),
                )
            )
        return super().request_validation()

    def _validate_tier(self, tiers=False):
        res = super()._validate_tier(tiers=tiers)
        self._fund_batch_approve_if_validated()
        return res

    def _fund_batch_approve_if_validated(self):
        """Dar la conformidad cuando firmó el último nivel.

        En sudo: el Gerente solo puede leer los Anexos de la conformidad. Cada
        Anexo deja constancia en su historial, como nota interna.
        """
        to_approve = self.filtered(
            lambda batch: batch.state == "draft"
            and batch.validation_status == "validated"
        )
        for batch in to_approve:
            batch.sudo().write(
                {
                    "state": "approved",
                    "approved_by_id": self.env.user.id,
                    "approved_date": fields.Datetime.now(),
                }
            )
            values = {"batch": batch.name, "user": self.env.user.name}
            for line in batch.line_ids.sudo():
                # Markup % escapa los valores.
                if line.observed:
                    body = (
                        Markup(
                            self.env._(
                                "Conformidad %(batch)s: <b>observado</b> por %(user)s."
                            )
                        )
                        % values
                    )
                else:
                    body = self.env._(
                        "Conformidad %(batch)s: conforme, por %(user)s.", **values
                    )
                line.sheet_id.message_post(body=body, subtype_xmlid="mail.mt_note")

    def reject_tier(self):
        # Siempre con motivo: es lo que lee Administración para corregir el lote.
        self.ensure_one()
        sequences = self._get_sequences_to_approve(self.env.user)
        reviews = self.review_ids.filtered(lambda x: x.sequence in sequences)
        action = self._add_comment("reject", reviews)
        action["name"] = self.env._("Motivo del rechazo")
        return action

    # Totales

    def _fund_batch_totals(self):
        """Totales por área y por fondo, para el formulario y el PDF."""
        self.ensure_one()
        source_labels = dict(
            self.env["hr.expense.sheet"]._fields["fund_source"]._description_selection(
                self.env
            )
        )
        by_area = defaultdict(float)
        by_source = defaultdict(float)
        for line in self.line_ids:
            by_area[line.department_id.name or self.env._("Sin área")] += (
                line.total_amount
            )
            by_source[
                source_labels.get(line.fund_source) or self.env._("Sin fondo asignado")
            ] += line.total_amount
        return {
            "by_area": sorted(by_area.items()),
            "by_source": sorted(by_source.items()),
        }

    def _fund_batch_summary_html(self):
        self.ensure_one()
        if not self.line_ids:
            return False
        totals = self._fund_batch_totals()

        def table(title, rows):
            body = Markup("").join(
                Markup(
                    "<tr><td>%s</td><td class='text-end'>%s</td></tr>"
                ) % (name, format_amount(self.env, amount, self.currency_id))
                for name, amount in rows
            )
            return Markup(
                "<div class='col-md-6'><table class='table table-sm'>"
                "<thead><tr><th>%s</th><th class='text-end'>Importe</th></tr></thead>"
                "<tbody>%s</tbody></table></div>"
            ) % (escape(title), body)

        return Markup("<div class='row'>%s%s</div>") % (
            table(self.env._("Por área"), totals["by_area"]),
            table(self.env._("Por fondo"), totals["by_source"]),
        )

    @api.constrains("company_id", "line_ids")
    def _check_line_company(self):
        for batch in self:
            if batch.line_ids.sheet_id.filtered(
                lambda sheet, b=batch: sheet.company_id != b.company_id
            ):
                raise ValidationError(
                    self.env._(
                        "Los Anexos de una conformidad tienen que ser de su compañía."
                    )
                )
