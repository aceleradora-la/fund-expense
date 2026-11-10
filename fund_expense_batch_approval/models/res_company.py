# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    fund_expense_batch_frequency = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("weekly", "Semanal"),
            ("monthly", "Mensual"),
        ],
        string="Conformidad de rendiciones",
        default="manual",
        required=True,
        help="Manual: Administración arma cada conformidad y elige los Anexos. "
        "Semanal o mensual: al terminar cada período se arma sola con todos los "
        "Anexos aprobados pendientes y se envía al Gerente.",
    )
    fund_expense_batch_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable de las conformidades",
        domain=[("share", "=", False)],
        help="Responsable de las conformidades automáticas: recibe las "
        "observaciones del Gerente.",
    )
    fund_expense_batch_last_period_end = fields.Date(
        string="Última conformidad automática hasta",
        readonly=True,
        copy=False,
    )

    def _fund_expense_batch_last_period(self, today):
        """Último período completo antes de `today`: semana (lunes a domingo) o mes."""
        self.ensure_one()
        if self.fund_expense_batch_frequency == "weekly":
            end = today - timedelta(days=today.weekday() + 1)
            return end - timedelta(days=6), end
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end

    def _fund_expense_batch_create(self, date_from, date_to):
        """Armar la conformidad del período y enviarla al Gerente."""
        self.ensure_one()
        Batch = self.env["fund.expense.batch"].with_company(self)
        batch = Batch.create(
            {
                "company_id": self.id,
                "date_from": date_from,
                "date_to": date_to,
                "user_id": self.fund_expense_batch_user_id.id,
            }
        )
        batch.action_add_pending()
        if not batch.line_ids:
            batch.unlink()
            return Batch
        batch.request_validation()
        return batch

    def _cron_fund_expense_batch(self):
        today = fields.Date.context_today(self)
        companies = self.search(
            [("fund_expense_batch_frequency", "in", ("weekly", "monthly"))]
        )
        for company in companies:
            date_from, date_to = company._fund_expense_batch_last_period(today)
            last = company.fund_expense_batch_last_period_end
            if last and last >= date_to:
                continue
            try:
                with self.env.cr.savepoint():
                    company._fund_expense_batch_create(date_from, date_to)
                    company.fund_expense_batch_last_period_end = date_to
            except Exception:
                _logger.exception(
                    "Conformidad de rendiciones: no se pudo armar la de %s",
                    company.name,
                )
