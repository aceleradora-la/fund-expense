# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

AFM_GROUP = "fund_expense_report.group_fund_expense_afm"


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    department_manager_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable del área",
        compute="_compute_department_manager_user_id",
        store=True,
        index=True,
        help="Usuario del responsable del departamento del empleado: aprueba el "
        "nivel 1. Queda vacío si quien pide es el propio responsable (en ese caso "
        "firma solo Gerencia de Administración y Finanzas).",
    )
    fund_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Fondo de pago",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        check_company=True,
        tracking=True,
        help="Diario desde el que paga Administración: banco (fondo fijo, por "
        "transferencia) o efectivo (caja chica). Se propone al registrar el pago.",
    )
    fund_source = fields.Selection(
        selection=[
            ("fondo_fijo", "Fondo fijo"),
            ("caja_chica", "Caja chica"),
        ],
        string="Fondos",
        compute="_compute_fund_source",
        store=True,
    )

    @api.depends("employee_id.department_id.manager_id.user_id")
    def _compute_department_manager_user_id(self):
        for sheet in self:
            employee = sheet.employee_id
            manager = employee.department_id.manager_id
            if manager and manager != employee:
                sheet.department_manager_user_id = manager.user_id
            else:
                sheet.department_manager_user_id = False

    @api.depends("fund_journal_id.type")
    def _compute_fund_source(self):
        sources = {"bank": "fondo_fijo", "cash": "caja_chica"}
        for sheet in self:
            sheet.fund_source = sources.get(sheet.fund_journal_id.type, False)

    def write(self, vals):
        if (
            "fund_journal_id" in vals
            and not self.env.su
            and not self.env.user.has_group(AFM_GROUP)
        ):
            raise AccessError(
                self.env._(
                    "Solo Gerencia de Administración y Finanzas puede elegir el "
                    "fondo de pago."
                )
            )
        return super().write(vals)

    @api.model
    def _get_validation_exceptions(self, extra_domain=None, add_base_exceptions=True):
        # Administración elige el fondo durante la aprobación o después, sin
        # reiniciar la validación.
        res = super()._get_validation_exceptions(
            extra_domain=extra_domain, add_base_exceptions=add_base_exceptions
        )
        if add_base_exceptions:
            res = list(set(res) | {"fund_journal_id", "fund_source"})
        return res

    # Envío: comprobantes y pedido de aprobación

    def _do_submit(self):
        self._fund_expense_check_receipts()
        res = super()._do_submit()
        # Al enviar se piden las aprobaciones, sin el paso manual de
        # "Solicitar validación".
        self.filtered("need_validation").request_validation()
        return res

    def _fund_expense_check_receipts(self):
        missing = self.expense_line_ids.filtered(
            lambda line: not line.advance and not line.vendor_id.vat
        )
        if missing:
            raise UserError(
                self.env._(
                    "Cada comprobante tiene que tener proveedor con CUIT. Falta en: %s",
                    ", ".join(missing.mapped("name")),
                )
            )

    # Aprobación: al validarse el último nivel se aprueba la hoja

    def _validate_tier(self, tiers=False):
        res = super()._validate_tier(tiers=tiers)
        self._fund_expense_approve_if_validated()
        return res

    def _fund_expense_approve_if_validated(self):
        """Aprobar la hoja (y crear sus asientos) cuando ya firmaron todos.

        En sudo: quien aprueba el último nivel (p. ej. el responsable del área)
        no necesita ser aprobador de Gastos. Se mantienen los controles del
        núcleo y del anticipo (_check_can_approve) y de la analítica.
        """
        to_approve = self.filtered(
            lambda sheet: sheet.approval_state == "submit" and sheet.validated
        )
        if not to_approve:
            return
        to_approve = to_approve.sudo()
        to_approve._check_can_approve()
        to_approve._validate_analytic_distribution()
        to_approve._do_approve()

    # Pago: se propone el fondo elegido por Administración

    def action_register_payment(self):
        action = super().action_register_payment()
        journal = self.fund_journal_id
        if len(journal) == 1 and isinstance(action, dict):
            action["context"] = dict(
                action.get("context") or {}, default_journal_id=journal.id
            )
        return action

    # Anexo I

    def _fund_expense_signature(self, kind):
        """Revisión aprobada que firma el Anexo I como `kind` (area / afm)."""
        self.ensure_one()
        return self.review_ids.filtered(
            lambda review: review.definition_id.fund_expense_signature == kind
            and review.status == "approved"
        ).sorted("reviewed_date")[-1:]
