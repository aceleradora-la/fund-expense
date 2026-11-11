# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import clean_context

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
        domain="[('type', 'in', ('bank', 'cash', 'credit')), "
        "('company_id', '=', company_id)]",
        check_company=True,
        tracking=True,
        help="Diario desde el que paga Administración: banco (fondo fijo, por "
        "transferencia), efectivo (caja chica) o tarjeta de crédito. Se propone al "
        "registrar el pago.",
    )
    fund_source = fields.Selection(
        selection=[
            ("fondo_fijo", "Fondo fijo"),
            ("caja_chica", "Caja chica"),
            ("tarjeta", "Tarjeta de crédito"),
        ],
        string="Fondos",
        compute="_compute_fund_source",
        store=True,
    )
    fund_bill_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="fund_expense_sheet_id",
        string="Facturas de proveedor",
        copy=False,
        help="Facturas precargadas al aprobar una hoja pagada por la empresa.",
    )
    fund_bill_count = fields.Integer(
        string="Facturas",
        compute="_compute_fund_bill_count",
        compute_sudo=True,
    )

    @api.depends(
        "employee_id.department_id.manager_id.user_id",
        "employee_id.department_id.manager_id.user_id.groups_id",
    )
    def _compute_department_manager_user_id(self):
        for sheet in self:
            sheet.department_manager_user_id = (
                False
                if sheet._fund_expense_area_skip_reason()
                else sheet.employee_id.department_id.manager_id.user_id
            )

    def _fund_expense_area_skip_reason(self):
        """Por qué no firma el responsable del área (nivel 1), o False.

        - Pide el propio responsable: firma solo Gerencia AyF.
        - El responsable es de Gerencia AyF: firma una sola vez, por AyF.
        - El área no tiene responsable con usuario.
        """
        self.ensure_one()
        employee = self.employee_id
        manager = employee.department_id.manager_id
        if not manager or manager == employee:
            return "own"
        if not manager.user_id:
            return "no_user"
        if manager.user_id.has_group(AFM_GROUP):
            return "afm"
        return False

    def _fund_expense_area_note(self):
        """Leyenda de la firma 2 del Anexo I cuando ese nivel no aplica."""
        self.ensure_one()
        reason = self._fund_expense_area_skip_reason()
        return {
            "own": self.env._("No aplica: solicita el responsable del área"),
            "afm": self.env._(
                "No aplica: el responsable del área firma por Gerencia de Adm. y Fin."
            ),
            "no_user": self.env._("No aplica: el área no tiene responsable con usuario"),
        }.get(reason, False)

    @api.depends("fund_journal_id.type")
    def _compute_fund_source(self):
        sources = {"bank": "fondo_fijo", "cash": "caja_chica", "credit": "tarjeta"}
        for sheet in self:
            sheet.fund_source = sources.get(sheet.fund_journal_id.type, False)

    @api.depends("fund_bill_ids")
    def _compute_fund_bill_count(self):
        for sheet in self:
            sheet.fund_bill_count = len(sheet.fund_bill_ids)

    @api.depends(
        "fund_bill_ids.state",
        "fund_bill_ids.payment_state",
        "fund_bill_ids.amount_residual",
    )
    def _compute_from_account_move_ids(self):
        res = super()._compute_from_account_move_ids()
        for sheet in self:
            bills = sheet._fund_expense_active_bills()
            if not bills:
                continue
            sheet.amount_residual = sum(
                bills.filtered(lambda bill: bill.state == "posted").mapped(
                    "amount_residual"
                )
            )
            states = set(bills.mapped("payment_state"))
            if len(states) == 1:
                sheet.payment_state = states.pop()
            elif states & {"partial", "paid", "in_payment"}:
                sheet.payment_state = "partial"
            else:
                sheet.payment_state = "not_paid"
        return res

    @api.depends("fund_bill_ids.state")
    def _compute_state(self):
        # La hoja pagada por la empresa no tiene asientos propios: avanza con
        # las facturas del proveedor.
        res = super()._compute_state()
        for sheet in self.filtered(lambda s: s.approval_state == "approve"):
            bills = sheet._fund_expense_active_bills()
            if not bills:
                continue
            if sheet.payment_state in ("paid", "in_payment"):
                sheet.state = "done"
            elif any(bill.state == "posted" for bill in bills):
                sheet.state = "post"
        return res

    def _fund_expense_active_bills(self):
        return self.fund_bill_ids.filtered(lambda bill: bill.state != "cancel")

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
        # reiniciar la validación. department_id lo escribe el núcleo al
        # recalcular el Manager (_compute_from_employee_id), también con la
        # hoja en aprobación: si estuviera bloqueado fallaría ese cálculo.
        res = super()._get_validation_exceptions(
            extra_domain=extra_domain, add_base_exceptions=add_base_exceptions
        )
        if add_base_exceptions:
            res = list(set(res) | {"department_id", "fund_journal_id", "fund_source"})
        return res

    # Envío: comprobantes y pedido de aprobación

    def _do_submit(self):
        self._fund_expense_check_receipts()
        res = super()._do_submit()
        # Al enviar se piden las aprobaciones, sin el paso manual de
        # "Solicitar validación".
        self.filtered("need_validation").request_validation()
        # need_validation no declara dependencias en base_tier_validation: sin
        # esto queda en caché como True y, al aprobar la hoja en la misma
        # transacción, OCA vuelve a pedir las aprobaciones (duplicadas).
        self.invalidate_recordset(["need_validation"])
        return res

    def activity_update(self):
        # Quien firma ya tiene su aprobación por niveles: la actividad del
        # núcleo le llegaría a otra persona (el Manager de la hoja).
        in_tiers = self.filtered(
            lambda sheet: sheet.state == "submit"
            and (sheet.need_validation or sheet.review_ids)
        )
        return super(HrExpenseSheet, self - in_tiers).activity_update()

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
        # Mismo motivo que en _do_submit: que el control de OCA al escribir
        # approval_state recalcule need_validation.
        to_approve.invalidate_recordset(["need_validation"])
        to_approve._check_can_approve()
        to_approve._validate_analytic_distribution()
        to_approve._do_approve()

    # Rechazo: un nivel que rechaza deja la hoja rechazada, con las firmas

    def reject_tier(self):
        # Siempre con motivo, sin exigir comentario también al aprobar: es lo
        # que lee el empleado para corregir la hoja.
        self.ensure_one()
        sequences = self._get_sequences_to_approve(self.env.user)
        reviews = self.review_ids.filtered(lambda x: x.sequence in sequences)
        action = self._add_comment("reject", reviews)
        action["name"] = self.env._("Motivo del rechazo")
        return action

    def _rejected_tier(self, tiers=False):
        res = super()._rejected_tier(tiers=tiers)
        self._fund_expense_refuse_if_rejected()
        return res

    def _fund_expense_refuse_if_rejected(self):
        """Rechazar la hoja cuando un nivel la rechaza.

        En sudo, como al aprobar: quien rechaza no necesita ser aprobador de
        Gastos.
        """
        for sheet in self.sudo().filtered(lambda s: s.approval_state == "submit"):
            rejected = sheet.review_ids.filtered(lambda r: r.status == "rejected")
            if rejected:
                sheet._do_refuse(rejected[-1].comment or "")

    def _do_refuse(self, reason):
        self._fund_expense_remove_bills()
        res = super()._do_refuse(reason)
        self.sudo().review_ids.filtered(
            lambda review: review.status in ("waiting", "pending")
        ).status = "cancel"
        return res

    def _allow_to_remove_reviews(self, values):
        # Por defecto OCA borra las revisiones al cancelar: la hoja rechazada
        # conserva quién firmó y quién rechazó. Se borran al pasarla a borrador.
        if values.get(self._state_field) == self._cancel_state:
            return False
        return super()._allow_to_remove_reviews(values)

    # Pago por la empresa: al aprobar se precarga la factura del proveedor

    def _do_create_moves(self):
        # El núcleo crearía un pago por renglón, sin factura. La deuda es con el
        # proveedor: Administración completa la factura, la confirma (Libro IVA)
        # y la paga por el circuito habitual.
        company_sheets = self.filtered(
            lambda sheet: sheet.payment_mode == "company_account"
        )
        moves = super(HrExpenseSheet, self - company_sheets)._do_create_moves()
        company_sheets._fund_expense_create_bills()
        return moves

    def action_sheet_move_post(self):
        # Sin esto el núcleo vería la hoja sin asientos y volvería a generarlos.
        company_sheets = self.filtered(
            lambda sheet: sheet.payment_mode == "company_account"
        )
        return super(HrExpenseSheet, self - company_sheets).action_sheet_move_post()

    def _fund_expense_create_bills(self):
        """Precargar un borrador de factura por proveedor.

        En sudo, como los asientos del núcleo: quien aprueba puede no tener
        permisos contables. No usa expense_sheet_id: con ese campo el núcleo
        trata el asiento como gasto y no como factura normal.
        """
        Move = (
            self.env["account.move"]
            .sudo()
            .with_context(clean_context(self.env.context))
        )
        for sheet in self.filtered(lambda s: not s.fund_bill_ids):
            bills = Move.with_company(sheet.company_id).create(
                sheet._fund_expense_prepare_bills_vals()
            )
            for bill in bills:
                bill._message_set_main_attachment_id(
                    bill.attachment_ids, force=True, filter_xml=False
                )

    def _fund_expense_prepare_bills_vals(self):
        self.ensure_one()
        journal = self._fund_expense_bill_journal()
        groups = defaultdict(lambda: self.env["hr.expense"])
        for expense in self.expense_line_ids:
            groups[expense.vendor_id, expense.currency_id] |= expense
        vals_list = []
        for (vendor, currency), expenses in groups.items():
            vals = {
                "move_type": "in_invoice",
                "partner_id": vendor.id,
                "currency_id": currency.id,
                "company_id": self.company_id.id,
                "invoice_origin": self.name,
                "fund_expense_sheet_id": self.id,
                "invoice_line_ids": [
                    Command.create(expense._fund_expense_prepare_bill_line_vals())
                    for expense in expenses
                ],
                "attachment_ids": [
                    Command.create(
                        attachment.copy_data(
                            {
                                "res_model": "account.move",
                                "res_id": False,
                                "raw": attachment.raw,
                            }
                        )[0]
                    )
                    for attachment in expenses.attachment_ids
                ],
            }
            if journal:
                vals["journal_id"] = journal.id
            vals_list.append(vals)
        return vals_list

    def _fund_expense_bill_journal(self):
        """Diario de compras para la factura: no el de reintegros a empleados.

        Con la localización argentina se prefiere uno con documentos, para que
        la factura entre al Libro IVA.
        """
        self.ensure_one()
        Journal = self.env["account.journal"].sudo()
        journals = Journal.search(
            [
                *Journal._check_company_domain(self.company_id),
                ("type", "=", "purchase"),
                ("id", "!=", self.employee_journal_id.id),
            ]
        )
        if "l10n_latam_use_documents" in Journal._fields:
            journals = journals.filtered("l10n_latam_use_documents") or journals
        return journals[:1]

    def _fund_expense_remove_bills(self):
        """Al rechazar o volver a borrador no quedan facturas sueltas."""
        bills = self.sudo().fund_bill_ids
        locked = bills.filtered(
            lambda bill: bill.state == "posted"
            or bill.fund_expense_payment_ids.filtered(
                lambda payment: payment.state not in ("draft", "canceled", "rejected")
            )
        )
        if locked:
            raise UserError(
                self.env._(
                    "Primero hay que anular la factura o el pago de: %s",
                    ", ".join(locked.mapped("display_name")),
                )
            )
        drafts = bills.filtered(lambda bill: bill.state == "draft")
        (bills - drafts).fund_expense_sheet_id = False
        drafts.unlink()

    def action_reset_expense_sheets(self):
        self._fund_expense_remove_bills()
        return super().action_reset_expense_sheets()

    def action_open_fund_bills(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "account.action_move_in_invoice_type"
        )
        action["domain"] = [("id", "in", self.fund_bill_ids.ids)]
        action["context"] = {"default_move_type": "in_invoice"}
        if len(self.fund_bill_ids) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.fund_bill_ids.id
        return action

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
