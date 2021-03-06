# -*- coding: utf-8 -*-
########################################################################################################################
#  Copyright (c) 2015 - Marcos Organizador de Negocios SRL. (<https://marcos.do/>) #  Write by Eneldo Serrata (eneldo@marcos.do)
#  See LICENSE file for full copyright and licensing details.
#
# Odoo Proprietary License v1.0
#
# This software and associated files (the "Software") may only be used
# (nobody can redistribute (or sell) your module once they have bought it, unless you gave them your consent)
# if you have purchased a valid license
# from the authors, typically via Odoo Apps, or if you have received a written
# agreement from the authors of the Software (see the COPYRIGHT file).
#
# You may develop Odoo modules that use the Software as a library (typically
# by depending on it, importing it and using its resources), but without copying
# any source code or material from the Software. You may distribute those
# modules under the license of your choice, provided that this license is
# compatible with the terms of the Odoo Proprietary License (For example:
# LGPL, MIT, or proprietary licenses similar to this one).
#
# It is forbidden to publish, distribute, sublicense, or sell copies of the Software
# or modified copies of the Software.
#
# The above copyright notice and this permission notice must be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
########################################################################################################################

from openerp import models, api, exceptions, fields
import number_to_word


class account_register_payments(models.TransientModel):
    _inherit = "account.register.payments"

    @api.onchange('amount')
    def _onchange_amount(self):
        self.check_amount_in_words = number_to_word.to_word(self.amount)


class account_payment(models.Model):
    _inherit = "account.payment"

    check_name = fields.Many2one("res.partner", string="A nombre de")

    @api.one
    @api.onchange("check_number")
    def onchange_check_number(self):
        if self.payment_method_code == "check_printing":
            check_duplicate = self.search([('journal_id', '=', self.journal_id.id), ('check_number', '=', self.check_number),('payment_method_code', '=', "check_printing")])
            if len(check_duplicate) > 1:
                raise exceptions.ValidationError(u"El número del cheque debe de ser único.")

    @api.multi
    def post(self):
        self.onchange_check_number()
        return super(account_payment, self).post()

    @api.multi
    def do_print_checks(self):
        check_layout = self[0].journal_id.check_layout
        if check_layout:
            return self.env['report'].get_action(self, "l10n_do_check_printing.check_print_report")
        return super(account_payment, self).do_print_checks()

    @api.onchange('amount')
    def _onchange_amount(self):
        self.check_amount_in_words = self.amont_in_word

    @api.multi
    def print_checks(self):
        res = super(account_payment, self).print_checks()
        if not self[0].journal_id.check_manual_sequencing:
            if self.check_number > 0:
                res["context"].update({"default_next_check_number": self.check_number})
        return res
