# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import unittest
from datetime import date, datetime, timedelta

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestFundExpenseBatch(TransactionCase):
    """Conformidad del Gerente sobre Anexos ya aprobados.

    Los Anexos se aprueban sin niveles (se desactivan las definiciones de las
    hojas): lo que se prueba es la conformidad, no la aprobación del Anexo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.company = cls.env.company
        Journal = cls.env["account.journal"]
        expense_account = cls.env["account.account"].search(
            [
                *cls.env["account.account"]._check_company_domain(company),
                ("account_type", "=", "expense"),
            ],
            limit=1,
        )
        if not expense_account:
            raise unittest.SkipTest("La compañía no tiene cuenta de gastos")
        journal_vals = {
            "name": "Rendiciones de gastos (test conformidad)",
            "code": "TRGC",
            "type": "purchase",
            "company_id": company.id,
        }
        if "l10n_latam_use_documents" in Journal._fields:
            journal_vals["l10n_latam_use_documents"] = False
        cls.expense_journal = Journal.create(journal_vals)
        cls.product = cls.env["product.product"].create(
            {
                "name": "Gasto de prueba (conformidad)",
                "can_be_expensed": True,
                "standard_price": 0.0,
                "property_account_expense_id": expense_account.id,
                "supplier_taxes_id": [Command.clear()],
            }
        )
        user_vals = {
            "company_id": company.id,
            "company_ids": [Command.set(company.ids)],
        }
        cls.employee_user = new_test_user(
            cls.env, login="fund_batch_employee", groups="base.group_user", **user_vals
        )
        cls.afm_user = new_test_user(
            cls.env,
            login="fund_batch_afm",
            name="Administración",
            groups="base.group_user,fund_expense_report.group_fund_expense_afm",
            **user_vals,
        )
        cls.director_user = new_test_user(
            cls.env,
            login="fund_batch_director",
            name="Gerente",
            groups="base.group_user,"
            "fund_expense_batch_approval.group_fund_expense_batch_approver",
            **user_vals,
        )
        cls.department = cls.env["hr.department"].create(
            {"name": "Área de prueba (conformidad)", "company_id": company.id}
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Empleado que rinde (conformidad)",
                "user_id": cls.employee_user.id,
                "work_contact_id": cls.employee_user.partner_id.id,
                "department_id": cls.department.id,
                "company_id": company.id,
            }
        )
        vendor_vals = {
            "name": "Proveedor con CUIT (conformidad)",
            "country_id": cls.env.ref("base.ar").id,
            "vat": "30712345671",
        }
        cuit_type = cls.env.ref("l10n_ar.it_cuit", raise_if_not_found=False)
        if cuit_type:
            vendor_vals["l10n_latam_identification_type_id"] = cuit_type.id
        cls.vendor = cls.env["res.partner"].create(vendor_vals)

        # Los Anexos se aprueban directo; la conformidad usa solo la
        # definición del módulo.
        TierDefinition = cls.env["tier.definition"]
        TierDefinition.search([("model", "=", "hr.expense.sheet")]).active = False
        TierDefinition.search(
            [
                ("model", "=", "fund.expense.batch"),
                (
                    "id",
                    "!=",
                    cls.env.ref(
                        "fund_expense_batch_approval.tier_definition_fund_expense_batch"
                    ).id,
                ),
            ]
        ).active = False

    def _sheet(self, approve=True):
        # Importes distintos: con el mismo empleado, fecha e importe el núcleo
        # los toma como duplicados y pide confirmar en lugar de aprobar.
        self.amount = getattr(self, "amount", 500.0) + 1
        sheet = self.env["hr.expense.sheet"].create(
            {
                "name": "Anexo de prueba",
                "employee_id": self.employee.id,
                "company_id": self.company.id,
                "employee_journal_id": self.expense_journal.id,
                "expense_line_ids": [
                    Command.create(
                        {
                            "name": "Comprobante",
                            "employee_id": self.employee.id,
                            "product_id": self.product.id,
                            "total_amount_currency": self.amount,
                            "tax_ids": [Command.clear()],
                            "date": fields.Date.today(),
                            "company_id": self.company.id,
                            "currency_id": self.company.currency_id.id,
                            "vendor_id": self.vendor.id,
                            "payment_mode": "own_account",
                        }
                    )
                ],
            }
        )
        sheet.with_user(self.employee_user).action_submit_sheet()
        if approve:
            sheet.with_user(self.afm_user).action_approve_expense_sheets()
            self.assertEqual(sheet.approval_state, "approve")
        return sheet

    def _batch(self, sheets=None, **vals):
        batch = (
            self.env["fund.expense.batch"]
            .with_user(self.afm_user)
            .create(dict({"date_to": fields.Date.today()}, **vals))
        )
        if sheets:
            self.env["fund.expense.batch.line"].with_user(self.afm_user).create(
                [{"batch_id": batch.id, "sheet_id": sheet.id} for sheet in sheets]
            )
        return batch

    def _sent_batch(self, sheets):
        batch = self._batch(sheets)
        batch.with_user(self.afm_user).request_validation()
        self.assertTrue(batch.review_ids)
        return batch

    def _observe(self, line, user, text="El comprobante no corresponde"):
        action = line.with_user(user).action_observe()
        wizard = (
            self.env[action["res_model"]]
            .with_user(user)
            .with_context(action["context"])
            .create({"observation": text})
        )
        wizard.action_confirm()

    # Armado

    def test_name_from_sequence(self):
        batch = self._batch()
        self.assertTrue(batch.name.startswith("CR/"))

    def test_add_pending(self):
        approved = self._sheet()
        submitted = self._sheet(approve=False)
        later = self._sheet()
        later.sudo().approval_date = datetime.now() + timedelta(days=5)
        other = self._sheet()
        self._batch([other])

        batch = self._batch()
        batch.with_user(self.afm_user).action_add_pending()
        sheets = batch.line_ids.sheet_id
        self.assertIn(approved, sheets)
        self.assertNotIn(submitted, sheets)
        self.assertNotIn(later, sheets)
        self.assertNotIn(other, sheets)
        self.assertEqual(approved.fund_batch_id, batch)
        self.assertEqual(approved.fund_conformity, "pending")
        line = batch.line_ids.filtered(lambda line: line.sheet_id == approved)
        self.assertEqual(line.department_id, self.department)
        self.assertEqual(line.total_amount, approved.total_amount)
        # El día de aprobación tal como lo guarda el núcleo, sin correrlo por
        # la zona horaria.
        self.assertEqual(line.approval_day, approved.approval_date.date())
        approved.sudo().approval_date = datetime(2026, 11, 11)
        self.assertEqual(line.approval_day, date(2026, 11, 11))

    def test_only_approved_sheets(self):
        with self.assertRaises(UserError):
            self._batch([self._sheet(approve=False)])

    def test_sheet_in_one_batch_only(self):
        sheet = self._sheet()
        batch = self._batch([sheet])
        # En otra conformidad.
        with self.assertRaises(UserError):
            self._batch([sheet])
        # Dos veces en la misma.
        with self.assertRaises(UserError):
            self._batch_line_create(batch, sheet)
        other = self._sheet()
        with self.assertRaises(UserError):
            self._batch([other, other])
        # Y el índice único por si se saltea el control.
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "INSERT INTO fund_expense_batch_line (batch_id, sheet_id) "
                    "VALUES (%s, %s)",
                    (batch.id, sheet.id),
                )

    def test_selector_skips_selected_sheets(self):
        sheet = self._sheet()
        batch = self._batch([sheet])
        self.assertEqual(batch.selected_sheet_ids, sheet)
        arch = self.env["fund.expense.batch"].get_view(view_type="form")["arch"]
        arch = arch.decode() if isinstance(arch, bytes) else arch
        self.assertIn("parent.selected_sheet_ids", arch)

    def test_create_from_sheet_list(self):
        first = self._sheet()
        second = self._sheet()
        first.sudo().approval_date = datetime(2026, 11, 2)
        second.sudo().approval_date = datetime(2026, 11, 5)
        action = (first | second).with_user(self.afm_user).action_fund_batch_create()
        batch = self.env["fund.expense.batch"].browse(action["res_id"])
        self.assertEqual(batch.line_ids.sheet_id, first | second)
        self.assertEqual((batch.date_from, batch.date_to), (date(2026, 11, 2), date(2026, 11, 5)))
        self.assertEqual(batch.state, "draft")
        self.assertFalse(batch.review_ids)
        # Ya están en una conformidad.
        with self.assertRaises(UserError):
            first.with_user(self.afm_user).action_fund_batch_create()

    def test_create_from_sheet_list_checks(self):
        with self.assertRaises(UserError):
            self._sheet(approve=False).with_user(self.afm_user).action_fund_batch_create()
        with self.assertRaises(AccessError):
            self._sheet().with_user(self.employee_user).action_fund_batch_create()
        binding = self.env.ref("fund_expense_batch_approval.action_server_fund_batch_create")
        self.assertEqual(binding.binding_model_id.model, "hr.expense.sheet")

    def test_empty_batch_cannot_be_sent(self):
        with self.assertRaises(UserError):
            self._batch().with_user(self.afm_user).request_validation()

    def test_lines_locked_once_sent(self):
        batch = self._sent_batch([self._sheet()])
        with self.assertRaises(UserError):
            self.env["fund.expense.batch.line"].with_user(self.afm_user).create(
                {"batch_id": batch.id, "sheet_id": self._sheet().id}
            )
        with self.assertRaises(UserError):
            batch.line_ids.with_user(self.afm_user).unlink()
        with self.assertRaises(UserError):
            batch.with_user(self.afm_user).action_add_pending()

    # Conformidad

    def test_director_gives_conformity(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        self.assertTrue(batch.with_user(self.director_user).can_review)
        self.assertFalse(batch.with_user(self.afm_user).can_review)
        batch.with_user(self.director_user).validate_tier()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(batch.approved_by_id, self.director_user)
        self.assertTrue(batch.approved_date)
        self.assertEqual(sheet.fund_conformity, "conformed")
        self.assertIn(batch.name, sheet.message_ids[:1].body)

    def test_director_reads_batch_sheets(self):
        sheet = self._sheet()
        outside = self._sheet()
        batch = self._sent_batch([sheet])
        batch.with_user(self.director_user).check_access("read")
        sheet.with_user(self.director_user).check_access("read")
        sheet.expense_line_ids.with_user(self.director_user).check_access("read")
        with self.assertRaises(AccessError):
            outside.with_user(self.director_user).check_access("read")
        with self.assertRaises(AccessError):
            sheet.with_user(self.director_user).check_access("write")

    def test_observation(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        line = batch.line_ids
        self._observe(line, self.director_user)
        self.assertTrue(line.observed)
        self.assertEqual(line.observed_by_id, self.director_user)
        self.assertEqual(sheet.fund_conformity, "observed")
        self.assertEqual(sheet.fund_batch_observation, "El comprobante no corresponde")
        activity = sheet.activity_ids.filtered(
            lambda act: act.user_id == self.afm_user
        )
        self.assertEqual(len(activity), 1)
        self.assertIn(batch.name, activity.summary)
        # La conformidad se da igual: el Anexo sigue observado.
        batch.with_user(self.director_user).validate_tier()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(batch.observed_count, 1)
        self.assertEqual(sheet.fund_conformity, "observed")

    def test_observation_escapes_text(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        self._observe(batch.line_ids, self.director_user, text="<b>ojo</b>")
        note = sheet.message_ids.filtered(lambda m: "ojo" in (m.body or ""))[:1]
        self.assertIn("&lt;b&gt;ojo&lt;/b&gt;", note.body)

    def test_clear_observation(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        self._observe(batch.line_ids, self.director_user)
        activity = batch.line_ids.observation_activity_id
        self.assertTrue(activity)
        batch.line_ids.with_user(self.director_user).action_clear_observation()
        self.assertFalse(batch.line_ids.observed)
        self.assertEqual(sheet.fund_conformity, "pending")
        # La actividad de Administración se cancela.
        self.assertFalse(activity.exists())
        self.assertFalse(
            sheet.activity_ids.filtered(lambda act: act.user_id == self.afm_user)
        )

    def test_observe_twice_updates_activity(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        self._observe(batch.line_ids, self.director_user, text="Primera")
        self._observe(batch.line_ids, self.director_user, text="Segunda")
        activities = sheet.activity_ids.filtered(
            lambda act: act.user_id == self.afm_user
        )
        self.assertEqual(len(activities), 1)
        self.assertIn("Segunda", str(activities.note))
        self.assertEqual(batch.line_ids.observation, "Segunda")

    def test_only_reviewer_observes(self):
        batch = self._sent_batch([self._sheet()])
        with self.assertRaises(UserError):
            batch.line_ids.with_user(self.afm_user).action_observe()
        batch.with_user(self.director_user).validate_tier()
        # Ya dada la conformidad, no se observa más.
        with self.assertRaises(UserError):
            batch.line_ids.with_user(self.director_user).action_observe()

    def test_reject_asks_reason_and_restart(self):
        batch = self._sent_batch([self._sheet()])
        action = batch.with_user(self.director_user).reject_tier()
        self.assertEqual(action["res_model"], "comment.wizard")
        self.env["comment.wizard"].with_user(self.director_user).with_context(
            action["context"]
        ).create({"comment": "Falta un Anexo"}).add_comment()
        self.assertEqual(batch.validation_status, "rejected")
        self.assertEqual(batch.state, "draft")
        batch.with_user(self.afm_user).restart_validation()
        self.assertFalse(batch.review_ids)
        # Vuelve a estar en armado.
        self._batch_line_create(batch, self._sheet())
        self.assertEqual(len(batch.line_ids), 2)

    def _batch_line_create(self, batch, sheet):
        return self.env["fund.expense.batch.line"].with_user(self.afm_user).create(
            {"batch_id": batch.id, "sheet_id": sheet.id}
        )

    def test_approved_batch_cannot_be_deleted(self):
        batch = self._sent_batch([self._sheet()])
        batch.with_user(self.director_user).validate_tier()
        with self.assertRaises(UserError):
            batch.with_user(self.afm_user).unlink()

    # El Anexo después de entrar en una conformidad

    def test_reset_sheet_leaves_draft_batch(self):
        sheet = self._sheet()
        batch = self._batch([sheet])
        sheet.with_user(self.afm_user).action_reset_expense_sheets()
        self.assertFalse(batch.line_ids)
        self.assertFalse(sheet.fund_conformity)

    def test_reset_sheet_blocked_once_sent(self):
        sheet = self._sheet()
        self._sent_batch([sheet])
        with self.assertRaises(UserError):
            sheet.with_user(self.afm_user).action_reset_expense_sheets()
        self.assertEqual(sheet.approval_state, "approve")

    def test_refuse_sheet_blocked_once_sent(self):
        sheet = self._sheet()
        self._sent_batch([sheet])
        with self.assertRaises(UserError):
            sheet.with_user(self.afm_user)._do_refuse("No corresponde")

    # Armado automático

    def test_last_period(self):
        company = self.company
        company.fund_expense_batch_frequency = "weekly"
        self.assertEqual(
            company._fund_expense_batch_last_period(date(2026, 11, 10)),
            (date(2026, 11, 2), date(2026, 11, 8)),
        )
        self.assertEqual(
            company._fund_expense_batch_last_period(date(2026, 11, 9)),
            (date(2026, 11, 2), date(2026, 11, 8)),
        )
        company.fund_expense_batch_frequency = "monthly"
        self.assertEqual(
            company._fund_expense_batch_last_period(date(2026, 11, 10)),
            (date(2026, 10, 1), date(2026, 10, 31)),
        )
        self.assertEqual(
            company._fund_expense_batch_last_period(date(2026, 3, 1)),
            (date(2026, 2, 1), date(2026, 2, 28)),
        )

    def test_cron_manual_does_nothing(self):
        self.company.fund_expense_batch_frequency = "manual"
        self._sheet()
        Batch = self.env["fund.expense.batch"]
        before = Batch.search_count([])
        self.env["res.company"]._cron_fund_expense_batch()
        self.assertEqual(Batch.search_count([]), before)

    def test_cron_weekly(self):
        company = self.company
        company.write(
            {
                "fund_expense_batch_frequency": "weekly",
                "fund_expense_batch_user_id": self.afm_user.id,
                "fund_expense_batch_last_period_end": False,
            }
        )
        today = fields.Date.context_today(company)
        date_from, date_to = company._fund_expense_batch_last_period(today)
        last_week = self._sheet()
        last_week.sudo().approval_date = datetime.combine(
            date_to, datetime.min.time()
        )
        this_week = self._sheet()

        self.env["res.company"]._cron_fund_expense_batch()
        batch = last_week.fund_batch_id
        self.assertTrue(batch)
        self.assertEqual((batch.date_from, batch.date_to), (date_from, date_to))
        self.assertEqual(batch.user_id, self.afm_user)
        self.assertFalse(this_week.fund_batch_id)
        # Enviada al Gerente.
        self.assertTrue(batch.review_ids)
        self.assertTrue(batch.with_user(self.director_user).can_review)
        self.assertEqual(company.fund_expense_batch_last_period_end, date_to)

        # Una por período.
        Batch = self.env["fund.expense.batch"]
        before = Batch.search_count([])
        self.env["res.company"]._cron_fund_expense_batch()
        self.assertEqual(Batch.search_count([]), before)

    def test_views(self):
        def arch(model):
            # base_tier_validation devuelve el arch en bytes.
            res = self.env[model].get_view(view_type="form")["arch"]
            return res.decode() if isinstance(res, bytes) else res

        batch = arch("fund.expense.batch")
        # Botones y aprobaciones que agrega base_tier_validation.
        self.assertIn("request_validation", batch)
        self.assertIn("validate_tier", batch)
        self.assertIn("action_add_pending", batch)
        self.assertIn("fund_expense_batch_frequency", arch("res.config.settings"))
        self.assertIn("fund_conformity", arch("hr.expense.sheet"))

    def test_report(self):
        sheet = self._sheet()
        batch = self._sent_batch([sheet])
        self._observe(batch.line_ids, self.director_user)
        batch.with_user(self.director_user).validate_tier()
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "fund_expense_batch_approval.report_fund_expense_batch", batch.ids
        )
        html = html.decode()
        self.assertIn(batch.name, html)
        self.assertIn(sheet.name, html)
        self.assertIn("El comprobante no corresponde", html)
        self.assertIn(self.department.name, html)
        # Documentos: el asiento del reintegro del Anexo.
        move = sheet.account_move_ids
        self.assertTrue(move)
        documents = batch.line_ids.document_names
        # En borrador: se distingue por proveedor (el empleado) e importe.
        self.assertIn("en borrador", documents)
        self.assertIn(move.partner_id.name, documents)
        self.assertIn("501", documents)
        self.assertIn("Documentos", html)

    def test_documents_include_payments(self):
        sheet = self._sheet()
        sheet.action_sheet_move_post()
        payment_action = sheet.account_move_ids.action_register_payment()
        try:
            with self.env.cr.savepoint():
                self.env["account.payment.register"].with_context(
                    **payment_action["context"]
                ).create({})._create_payments()
        except Exception as error:  # noqa: BLE001
            # Con localizaciones que piden datos extra para pagar (retenciones,
            # talonarios) el asistente estándar no alcanza.
            self.skipTest(f"No se pudo registrar el pago en esta base: {error}")
        self.assertIn(sheet.payment_state, ("paid", "in_payment"))
        line = self._batch([sheet]).line_ids
        payment = sheet.account_move_ids.reconciled_payment_ids
        self.assertTrue(payment)
        self.assertIn(f"Pago {payment.name}", line.document_names)
        # Confirmado: la factura aparece con su número.
        self.assertIn(sheet.account_move_ids.name, line.document_names)
