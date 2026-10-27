# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import unittest

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestFundExpenseReport(TransactionCase):
    """Sobre la compañía principal y su plan de cuentas.

    No usa TestExpenseCommon: crea una compañía nueva y, en bases donde
    crear contactos está restringido, su usuario no puede hacerlo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.company = cls.env.company
        Journal = cls.env["account.journal"]
        company_domain = Journal._check_company_domain(company)
        cls.bank_journal = Journal.search(
            [*company_domain, ("type", "=", "bank")], limit=1
        )
        cls.cash_journal = Journal.search(
            [*company_domain, ("type", "=", "cash")], limit=1
        )
        expense_account = cls.env["account.account"].search(
            [
                *cls.env["account.account"]._check_company_domain(company),
                ("account_type", "=", "expense"),
            ],
            limit=1,
        )
        if not (cls.bank_journal and cls.cash_journal and expense_account):
            raise unittest.SkipTest(
                "La compañía no tiene diario de banco, de efectivo o cuenta de gastos"
            )
        # Diario de gastos de empleados sin documentos fiscales (localización
        # argentina): el reintegro no es una factura; los comprobantes van en
        # cada renglón.
        journal_vals = {
            "name": "Rendiciones de gastos (test)",
            "code": "TRGT",
            "type": "purchase",
            "company_id": company.id,
        }
        if "l10n_latam_use_documents" in Journal._fields:
            journal_vals["l10n_latam_use_documents"] = False
        cls.expense_journal = Journal.create(journal_vals)
        cls.product = cls.env["product.product"].create(
            {
                "name": "Gasto de prueba (rendición)",
                "can_be_expensed": True,
                "standard_price": 0.0,
                "property_account_expense_id": expense_account.id,
                "supplier_taxes_id": [Command.clear()],
            }
        )

        cls.afm_group = cls.env.ref("fund_expense_report.group_fund_expense_afm")
        user_vals = {
            "company_id": company.id,
            "company_ids": [Command.set(company.ids)],
        }
        cls.employee_user = new_test_user(
            cls.env,
            login="fund_expense_employee",
            groups="base.group_user",
            **user_vals,
        )
        cls.manager_user = new_test_user(
            cls.env,
            login="fund_expense_area_manager",
            groups="base.group_user",
            **user_vals,
        )
        cls.afm_user = new_test_user(
            cls.env,
            login="fund_expense_afm",
            name="Gerencia AyF",
            groups="base.group_user,fund_expense_report.group_fund_expense_afm",
            **user_vals,
        )
        Employee = cls.env["hr.employee"]
        cls.expense_employee = Employee.create(
            {
                "name": "Empleado que rinde",
                "user_id": cls.employee_user.id,
                "work_contact_id": cls.employee_user.partner_id.id,
                "company_id": company.id,
            }
        )
        cls.manager_employee = Employee.create(
            {
                "name": "Responsable del área",
                "user_id": cls.manager_user.id,
                "work_contact_id": cls.manager_user.partner_id.id,
                "company_id": company.id,
            }
        )
        cls.department = cls.env["hr.department"].create(
            {
                "name": "Área de prueba",
                "manager_id": cls.manager_employee.id,
                "company_id": company.id,
            }
        )
        (cls.manager_employee | cls.expense_employee).department_id = cls.department
        vendor_vals = {
            "name": "Proveedor con CUIT",
            "country_id": cls.env.ref("base.ar").id,
            "vat": "30712345671",
        }
        # Con l10n_ar el CUIT se valida según el tipo de identificación.
        cuit_type = cls.env.ref("l10n_ar.it_cuit", raise_if_not_found=False)
        if cuit_type:
            vendor_vals["l10n_latam_identification_type_id"] = cuit_type.id
        cls.vendor = cls.env["res.partner"].create(vendor_vals)

        # Solo las definiciones del test: las de la base no tienen que influir.
        # En base_tier_validation firma primero la de mayor secuencia.
        TierDefinition = cls.env["tier.definition"]
        TierDefinition.search([("model", "=", "hr.expense.sheet")]).active = False
        sheet_model = cls.env["ir.model"]._get("hr.expense.sheet")
        TierDefinition.create(
            {
                "name": "Responsable del área",
                "model_id": sheet_model.id,
                "review_type": "field",
                "reviewer_field_id": cls.env["ir.model.fields"]
                ._get("hr.expense.sheet", "department_manager_user_id")
                .id,
                "definition_domain": "[('department_manager_user_id', '!=', False)]",
                "sequence": 20,
                "approve_sequence": True,
                "fund_expense_signature": "area",
                "company_id": company.id,
            }
        )
        TierDefinition.create(
            {
                "name": "Gerencia AyF",
                "model_id": sheet_model.id,
                "review_type": "group",
                "reviewer_group_id": cls.afm_group.id,
                "sequence": 10,
                "approve_sequence": True,
                "fund_expense_signature": "afm",
                "company_id": company.id,
            }
        )

    def _sheet(self, employee=None, vendor=True):
        employee = employee or self.expense_employee
        line = {
            "name": "Comprobante de prueba",
            "employee_id": employee.id,
            "product_id": self.product.id,
            "total_amount_currency": 1000.00,
            "tax_ids": [Command.clear()],
            "date": fields.Date.today(),
            "company_id": self.company.id,
            "currency_id": self.company.currency_id.id,
            "receipt_number": "0001-00001234",
        }
        if vendor:
            line["vendor_id"] = self.vendor.id
        return self.env["hr.expense.sheet"].create(
            {
                "name": "Rendición de prueba",
                "employee_id": employee.id,
                "company_id": self.company.id,
                "employee_journal_id": self.expense_journal.id,
                "expense_line_ids": [Command.create(line)],
            }
        )

    def _submit(self, sheet):
        sheet.with_user(sheet.employee_id.user_id).action_submit_sheet()

    def test_department_manager(self):
        self.assertEqual(self._sheet().department_manager_user_id, self.manager_user)
        # Si pide el propio responsable, no hay nivel 1.
        own = self._sheet(employee=self.manager_employee)
        self.assertFalse(own.department_manager_user_id)

    def test_submit_requires_vendor_with_cuit(self):
        sheet = self._sheet(vendor=False)
        with self.assertRaises(UserError):
            self._submit(sheet)
        self.assertNotEqual(sheet.approval_state, "submit")

    def test_submit_requests_validation(self):
        sheet = self._sheet()
        self._submit(sheet)
        self.assertEqual(sheet.approval_state, "submit")
        self.assertEqual(len(sheet.review_ids), 2)
        signatures = sheet.review_ids.mapped("definition_id.fund_expense_signature")
        self.assertEqual(sorted(signatures), ["afm", "area"])
        area = sheet.review_ids.filtered(
            lambda r: r.definition_id.fund_expense_signature == "area"
        )
        self.assertEqual(area.reviewer_ids, self.manager_user)
        # Firma primero el responsable del área.
        self.assertTrue(sheet.with_user(self.manager_user).can_review)
        self.assertFalse(sheet.with_user(self.afm_user).can_review)

    def test_requester_is_area_manager(self):
        sheet = self._sheet(employee=self.manager_employee)
        self._submit(sheet)
        self.assertEqual(
            sheet.review_ids.mapped("definition_id.fund_expense_signature"), ["afm"]
        )

    def test_full_approval_creates_moves(self):
        sheet = self._sheet()
        self._submit(sheet)
        # El responsable del área no es aprobador de Gastos: igual ve y aprueba.
        sheet.with_user(self.manager_user).validate_tier()
        self.assertEqual(sheet.approval_state, "submit")
        sheet.with_user(self.afm_user).validate_tier()
        self.assertEqual(sheet.approval_state, "approve")
        self.assertTrue(sheet.account_move_ids)
        # No se duplicaron las aprobaciones al aprobar la hoja.
        self.assertEqual(len(sheet.review_ids), 2)
        self.assertEqual(
            sheet._fund_expense_signature("area").done_by, self.manager_user
        )
        self.assertEqual(sheet._fund_expense_signature("afm").done_by, self.afm_user)

    def test_fund_journal_only_afm(self):
        sheet = self._sheet()
        self._submit(sheet)
        with self.assertRaises(AccessError):
            sheet.with_user(self.employee_user).fund_journal_id = (
                self.bank_journal
            )
        # Gerencia AyF lo elige mientras la hoja está en aprobación.
        sheet.with_user(self.afm_user).fund_journal_id = self.bank_journal
        self.assertEqual(sheet.fund_source, "fondo_fijo")
        sheet.with_user(self.afm_user).fund_journal_id = self.cash_journal
        self.assertEqual(sheet.fund_source, "caja_chica")

    def test_register_payment_proposes_fund_journal(self):
        sheet = self._sheet()
        self._submit(sheet)
        sheet.fund_journal_id = self.cash_journal
        sheet.with_user(self.manager_user).validate_tier()
        sheet.with_user(self.afm_user).validate_tier()
        sheet.action_sheet_move_post()
        action = sheet.action_register_payment()
        self.assertEqual(action["context"]["default_journal_id"], self.cash_journal.id)

    def test_anexo_report(self):
        sheet = self._sheet(employee=self.manager_employee)
        self._submit(sheet)
        sheet.with_user(self.afm_user).validate_tier()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "fund_expense_report.report_fund_expense_anexo", sheet.ids
        )[0].decode()
        self.assertIn("ANEXO I: SOLICITUD DE FONDOS", html)
        self.assertIn("0001-00001234", html)
        self.assertIn("No aplica: solicita el responsable del área", html)
        self.assertIn("Gerencia AyF", html)
