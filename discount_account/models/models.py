from odoo import models, fields, api, _
from odoo.tools.misc import format_date,formatLang
from odoo.tools import float_is_zero
from dateutil.relativedelta import relativedelta


class CustomPartner(models.Model):
    _inherit = 'res.partner'

    def _default_value(self):
        return self.env['ir.config_parameter'].sudo().get_param('discount_account.discount_payment_account_id') or False

    discount_payment_account_id = fields.Many2one('account.account', compute='get_partner',
                                                  string='Discount Received Account')
    new_field = fields.Char(string="Test", required=False, )

    # Compute field to get default advance account from setting
    def get_partner(self):
        self.discount_payment_account_id = int(
            self.env['ir.config_parameter'].sudo().get_param('discount_account.discount_payment_account_id')) or False


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _recompute_payment_terms_lines(self):
        ''' Compute the dynamic payment term lines of the journal entry.'''
        self.ensure_one()
        in_draft_mode = self != self._origin
        today = fields.Date.context_today(self)
        self = self.with_context(force_company=self.journal_id.company_id.id)

        def _get_payment_terms_computation_date(self):
            ''' Get the date from invoice that will be used to compute the payment terms.
            :param self:    The current account.move record.
            :return:        A datetime.date object.
            '''
            if self.invoice_payment_term_id:
                return self.invoice_date or today
            else:
                return self.invoice_date_due or self.invoice_date or today

        def _get_payment_terms_account(self, payment_terms_lines):
            ''' Get the account from invoice that will be set as receivable / payable account.
            :param self:                    The current account.move record.
            :param payment_terms_lines:     The current payment terms lines.
            :return:                        An account.account record.
            '''
            if payment_terms_lines:
                # Retrieve account from previous payment terms lines in order to allow the user to set a custom one.
                return payment_terms_lines[0].account_id
            elif self.partner_id:
                # Retrieve account from partner.
                if self.is_sale_document(include_receipts=True):
                    return self.partner_id.property_account_receivable_id
                else:
                    return self.partner_id.property_account_payable_id
            else:
                # Search new account.
                domain = [
                    ('company_id', '=', self.company_id.id),
                    ('internal_type', '=',
                     'receivable' if self.type in ('out_invoice', 'out_refund', 'out_receipt') else 'payable'),
                ]
                return self.env['account.account'].search(domain, limit=1)

        def _compute_payment_terms(self, date, total_balance, total_amount_currency):
            ''' Compute the payment terms.
            :param self:                    The current account.move record.
            :param date:                    The date computed by '_get_payment_terms_computation_date'.
            :param total_balance:           The invoice's total in company's currency.
            :param total_amount_currency:   The invoice's total in invoice's currency.
            :return:                        A list <to_pay_company_currency, to_pay_invoice_currency, due_date>.
            '''
            if self.invoice_payment_term_id:
                to_compute = self.invoice_payment_term_id.compute(total_balance, date_ref=date,
                                                                  currency=self.currency_id)
                if self.currency_id != self.company_id.currency_id:
                    # Multi-currencies.
                    to_compute_currency = self.invoice_payment_term_id.compute(total_amount_currency, date_ref=date,
                                                                               currency=self.currency_id)
                    return [(b[0], b[1], ac[1]) for b, ac in zip(to_compute, to_compute_currency)]
                else:
                    # Single-currency.
                    return [(b[0], b[1], 0.0) for b in to_compute]
            else:
                return [(fields.Date.to_string(date), total_balance, total_amount_currency)]

        def _compute_diff_payment_terms_lines(self, existing_terms_lines, total_balance, account, to_compute):
            ''' Process the result of the '_compute_payment_terms' method and creates/updates corresponding invoice lines.
            :param self:                    The current account.move record.
            :param existing_terms_lines:    The current payment terms lines.
            :param account:                 The account.account record returned by '_get_payment_terms_account'.
            :param to_compute:              The list returned by '_compute_payment_terms'.
            '''
            # As we try to update existing lines, sort them by due date.
            existing_terms_lines = existing_terms_lines.sorted(lambda line: line.date_maturity or today)
            existing_terms_lines_index = 0

            # Recompute amls: update existing line or create new one for each payment term.
            new_terms_lines = self.env['account.move.line']
            for date_maturity, balance, amount_currency in to_compute:
                if self.journal_id.company_id.currency_id.is_zero(balance) and len(to_compute) > 1:
                    continue

                if existing_terms_lines_index < len(existing_terms_lines):
                    candidate = existing_terms_lines[existing_terms_lines_index]
                    account_id = None
                    if self.partner_id.discount_payment_account_id and self.invoice_payment_term_id and \
                            self.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[0]:
                        discount_amount = (self.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[
                                               0].value_amount / 100) * total_balance
                        if discount_amount:
                            if int(balance) == int(discount_amount) and candidate.account_id.id != self.partner_id.discount_payment_account_id.id:
                                    account_id = self.partner_id.discount_payment_account_id

                    elif self.partner_id.discount_payment_account_id and self.invoice_payment_term_id and \
                            self.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[0]:
                        discount_amount = (self.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[
                                               0].value_amount / 100) * total_balance
                        if int(balance) == int(discount_amount) and candidate.account_id.id != self.partner_id.discount_payment_account_id.id:
                            if int(balance) == int(discount_amount):
                                account_id = self.partner_id.discount_payment_account_id
                    # Update existing line.

                    candidate = existing_terms_lines[existing_terms_lines_index]
                    existing_terms_lines_index += 1
                    candidate.update({
                        'date_maturity': date_maturity,
                        'amount_currency': -amount_currency,
                        'debit': balance < 0.0 and -balance or 0.0,
                        'credit': balance > 0.0 and balance or 0.0,
                        'account_id':account_id.id if account_id else candidate.account_id.id
                    })
                else:
                    # Create new line.
                    account_id = None
                    if self.partner_id.discount_payment_account_id and self.invoice_payment_term_id and \
                            self.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[0]:
                        discount_amount = (self.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[
                                               0].value_amount / 100) * total_balance
                        if discount_amount:
                            if int(balance) == int(discount_amount):
                                    account_id = self.partner_id.discount_payment_account_id

                    elif self.partner_id.discount_payment_account_id and self.invoice_payment_term_id and \
                            self.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[0]:
                        discount_amount = (self.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[
                                               0].value_amount / 100) * total_balance
                        if discount_amount:
                            if int(balance) == int(discount_amount):
                                account_id = self.partner_id.discount_payment_account_id

                    create_method = in_draft_mode and self.env['account.move.line'].new or self.env[
                        'account.move.line'].create
                    candidate = create_method({
                        'name': self.invoice_payment_ref or '',
                        'debit': balance < 0.0 and -balance or 0.0,
                        'credit': balance > 0.0 and balance or 0.0,
                        'quantity': 1.0,
                        'amount_currency': -amount_currency,
                        'date_maturity': date_maturity,
                        'move_id': self.id,
                        'currency_id': self.currency_id.id if self.currency_id != self.company_id.currency_id else False,
                        'account_id': account_id.id if account_id else account.id,
                        'partner_id': self.commercial_partner_id.id,
                        'exclude_from_invoice_tab': True,
                    })
                new_terms_lines += candidate
                if in_draft_mode:
                    candidate._onchange_amount_currency()
                    candidate._onchange_balance()
            return new_terms_lines

        existing_terms_lines = self.line_ids.filtered(
            lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))
        others_lines = self.line_ids.filtered(
            lambda line: line.account_id.user_type_id.type not in ('receivable', 'payable'))
        company_currency_id = self.company_id.currency_id
        if self.type =='in_refund':
            total_balance = sum(others_lines.mapped(
                lambda l: company_currency_id.round(l.balance) if company_currency_id.round(l.balance) < 0 else 0))
        else:
            total_balance = sum(others_lines.mapped(
                lambda l: company_currency_id.round(l.balance) if company_currency_id.round(l.balance) > 0 else 0))
        total_amount_currency = sum(others_lines.mapped('amount_currency'))

        # customization
        discount_line = others_lines.filtered(lambda line: line.account_id.user_type_id.type in (
            'receivable', 'payable',
            'other') if line.account_id == self.partner_id.discount_payment_account_id else None)

        if discount_line:
            existing_terms_lines += discount_line
        if not others_lines:
            self.line_ids -= existing_terms_lines
            return

        computation_date = _get_payment_terms_computation_date(self)
        account = _get_payment_terms_account(self, existing_terms_lines)
        to_compute = _compute_payment_terms(self, computation_date, total_balance, total_amount_currency)
        new_terms_lines = _compute_diff_payment_terms_lines(self, existing_terms_lines, total_balance, account,
                                                            to_compute)

        # Remove old terms lines that are no longer needed.
        existing_terms_lines -= discount_line
        self.line_ids -= existing_terms_lines - new_terms_lines

        if new_terms_lines:
            self.invoice_payment_ref = new_terms_lines[-1].name or ''
            self.invoice_date_due = new_terms_lines[-1].date_maturity


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    invoice_date = fields.Date(string='Invoice/Bill Date', readonly=True, index=True,
                               related='invoice_ids.invoice_date')
    invoice_number = fields.Char(string='Invoice/Bill Number', readonly=True, index=True, related='invoice_ids.name')
    invoice_amount = fields.Monetary(string='Original Amount', readonly=True, related='invoice_ids.amount_total')
    invoice_balance = fields.Monetary(string='Balance', readonly=True, related='invoice_ids.amount_residual')
    invoice_discount = fields.Monetary(string='Discount Amount', readonly=True)

    @api.onchange('invoice_amount')
    def _compute_discount(self):
        if self.invoice_ids and self.invoice_ids.invoice_payment_term_id and \
                    self.invoice_ids.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[0]:
                self.invoice_discount = (self.invoice_ids.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[
                                       0].value_amount / 100) * self.invoice_amount
        elif self.invoice_ids and self.invoice_ids.invoice_payment_term_id and \
                    self.invoice_ids.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[0]:
                self.invoice_discount = (self.invoice_ids.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[
                                       0].value_amount / 100) * self.invoice_amount
        else:
            self.invoice_discount=0.0

    @api.model
    def _check_make_stub_line(self, invoice):
        """ Return the dict used to display an invoice/refund in the stub
        """
        # Find the account.partial.reconcile which are common to the invoice and the payment
        if invoice.type in ['in_invoice', 'out_refund']:
            invoice_sign = 1
            invoice_payment_reconcile = invoice.line_ids.mapped('matched_debit_ids').filtered(lambda r: r.debit_move_id in self.move_line_ids)
        else:
            invoice_sign = -1
            invoice_payment_reconcile = invoice.line_ids.mapped('matched_credit_ids').filtered(lambda r: r.credit_move_id in self.move_line_ids)

        if self.currency_id != self.journal_id.company_id.currency_id:
            amount_paid = abs(sum(invoice_payment_reconcile.mapped('amount_currency')))
        else:
            amount_paid = abs(sum(invoice_payment_reconcile.mapped('amount')))

        amount_residual = invoice_sign * invoice.amount_residual
        amount_discount = (invoice_sign * invoice.amount_total)-amount_paid

        return {
            'due_date': format_date(self.env, invoice.invoice_date_due),
            'number': invoice.ref and invoice.name + ' - ' + invoice.ref or invoice.name,
            'amount_total': formatLang(self.env, invoice_sign * invoice.amount_total, currency_obj=invoice.currency_id),
            'amount_residual': formatLang(self.env, amount_residual, currency_obj=invoice.currency_id) if amount_residual * 10**4 != 0 else '-',
            'amount_discount': formatLang(self.env, amount_discount, currency_obj=invoice.currency_id),
            'amount_paid': formatLang(self.env, invoice_sign * amount_paid, currency_obj=invoice.currency_id),
            'currency': invoice.currency_id,
        }


class ReportAccountAgedPartner(models.AbstractModel):
    _inherit = "account.aged.partner"

    @api.model
    def _get_columns_name(self, options):

        columns = [
            {},

            {'name': _("Due Date"), 'class': 'date', 'style': 'white-space:nowrap;'},
            {'name': _("Bill Total"), 'class': '', 'style': 'text-align:center; white-space:nowrap;'},
            {'name': _("BILL Discount"), 'class': '', 'style': 'text-align:center; white-space:nowrap;'},
            {'name': _("Net"), 'class': 'date', 'style': 'white-space:nowrap;'},
            {'name': _("As of: %s") % format_date(self.env, options['date']['date_to']), 'class': 'number sortable', 'style': 'white-space:nowrap;'},

            {'name': _("1 - 30"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
            {'name': _("31 - 60"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
            {'name': _("61 - 90"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
            {'name': _("91 - 120"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
            {'name': _("Older"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
            # {'name': _("Actual Amount"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},

            {'name': _("Total"), 'class': 'number sortable', 'style': 'white-space:nowrap;'},
        ]
        return columns

    @api.model
    def _get_lines(self, options, line_id=None):
        "overwrite exist features"
        sign = -1.0 if self.env.context.get('aged_balance') else 1.0
        lines = []
        account_types = [self.env.context.get('account_type')]
        context = {'include_nullified_amount': True}
        if line_id and 'partner_' in line_id:
            # we only want to fetch data about this partner because we are expanding a line
            partner_id_str = line_id.split('_')[1]
            if partner_id_str.isnumeric():
                partner_id = self.env['res.partner'].browse(int(partner_id_str))
            else:
                partner_id = False
            context.update(partner_ids=partner_id)
        results, total, amls = self.env['report.account.report_agedpartnerbalance'].with_context(
            **context)._get_partner_move_lines(account_types, self._context['date_to'], 'posted', 30)
        total_discount = 0.0
        total_bill = 0.0
        total_net = 0.0

        for values in results:
            # customization to get discount in aged payable report
            vals = {
                'id': 'partner_%s' % (values['partner_id'],),
                'name': values['name'],
                'level': 2,
                'columns': [{'name': ''}] * 4 + [{'name': self.format_value(sign * v), 'no_format': sign * v}
                                                 for v in [values['direction'],values['4'],
                                                           values['3'], values['2'],
                                                           values['1'], values['0'], values['total']]],
                'trust': values['trust'],
                'unfoldable': True,
                'unfolded': 'partner_%s' % (values['partner_id'],) in options.get('unfolded_lines'),
                'partner_id': values['partner_id'],
            }

            lines.append(vals)
            if 'partner_%s' % (values['partner_id'],) in options.get('unfolded_lines'):
                for line in amls[values['partner_id']]:
                    aml = line['line']
                    if aml.move_id.is_purchase_document():
                        caret_type = 'account.invoice.in'
                    elif aml.move_id.is_sale_document():
                        caret_type = 'account.invoice.out'
                    elif aml.payment_id:
                        caret_type = 'account.payment'
                    else:
                        caret_type = 'account.move'

                    line_date = aml.date_maturity or aml.date

                    if not self._context.get('no_format'):
                        line_date = format_date(self.env, line_date)

                    # calculate discount amount
                    discount_amount = 0.0
                    if aml.move_id.invoice_payment_term_id:
                        if aml.partner_id.discount_payment_account_id and aml.move_id.invoice_payment_term_id and \
                                aml.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[0]:
                            discount_amount = (aml.move_id.invoice_payment_term_id.line_ids.search(
                                [('value', '=', 'percent')])[
                                                   0].value_amount / 100) * aml.move_id.amount_total

                        elif aml.partner_id.discount_payment_account_id and aml.move_id.invoice_payment_term_id and \
                                aml.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[0]:
                            discount_amount = (
                                aml.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[
                                    0].value_amount)

                    # discount_value = {'name': discount_amount if discount_amount > 0 else 0.0,
                    #                   'no_format': discount_amount if discount_amount > 0 else 0.0}
                    total_discount = total_discount + discount_amount
                    total_bill = total_bill + aml.move_id.amount_total
                    total_net = total_net + line['amount']
                    vals = {
                        'id': aml.id,
                        'name': aml.move_id.name,
                        'class': 'date',
                        'caret_options': caret_type,
                        'level': 4,
                        'parent_id': 'partner_%s' % (values['partner_id'],),
                        'columns': [{'name': v} for v in
                                    [format_date(self.env, aml.date_maturity or aml.date), aml.move_id.amount_total, discount_amount,line['amount']]] +
                                   [{'name': self.format_value(sign * v, blank_if_zero=True), 'no_format': sign * v} for
                                    v in [line['period'] == 6 - i and line['amount'] or 0 for i in range(7)]],#'''aml.journal_id.code,
                                     # aml.account_id.display_name,''',
                        'action_context': {
                            'default_type': aml.move_id.type,
                            'default_journal_id': aml.move_id.journal_id.id,
                        },
                        'title_hover': self._format_aml_name(aml.name, aml.ref, aml.move_id.name),
                    }


                    # vals['columns'].insert(5,discount_value)
                    lines.append(vals)




        if total and not line_id:
            total_line = {
                'id': 0,
                'name': _('Total'),
                'class': 'total',
                'level': 2,
                'columns': [{'name': ''}] * 4 + [{'name': self.format_value(sign * v), 'no_format': sign * v} for v in
                                                 [total[6], total[4], total[3], total[2], total[1], total[0],
                                                  total[5]]],
            }
            # total_discount_val = {'name': total_discount ,
            #                   'no_format': total_discount if total_discount>0 else 0.0}
            # total_line['columns'].insert(2,total_discount_val)
            # total_bill_value = {'name': total_bill ,
            #                   'no_format': total_bill if total_bill>0 else 0.0}
            # total_line['columns'].insert(1,total_bill_value)
            # net_value = {'name': total_bill-total_discount ,
            #                   'no_format': total_bill-total_discount if total_bill-total_discount>0 else 0.0}
            # total_line['columns'].insert(3,net_value)
            lines.append(total_line)
        return lines


class ReportAgedPartnerBalance(models.AbstractModel):

    _name = 'report.account.report_agedpartnerbalance'
    _description = 'Aged Partner Balance Report'

    @api.model
    def _get_partner_move_lines(self, account_type, date_from, target_move, period_length):
        ctx = self._context
        periods = {}
        date_from = fields.Date.from_string(date_from)
        start = date_from
        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length)
            period_name = str((5 - (i + 1)) * period_length + 1) + '-' + str((5 - i) * period_length)
            period_stop = (start - relativedelta(days=1)).strftime('%Y-%m-%d')
            if i == 0:
                period_name = '+' + str(4 * period_length)
            periods[str(i)] = {
                'name': period_name,
                'stop': period_stop,
                'start': (i != 0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop

        res = []
        total = []
        partner_clause = ''
        cr = self.env.cr
        user_company = self.env.company
        user_currency = user_company.currency_id
        company_ids = self._context.get('company_ids') or [user_company.id]
        move_state = ['draft', 'posted']
        if target_move == 'posted':
            move_state = ['posted']
        arg_list = (tuple(move_state), tuple(account_type), date_from, date_from,)
        if 'partner_ids' in ctx:
            if ctx['partner_ids']:
                partner_clause = 'AND (l.partner_id IN %s)'
                arg_list += (tuple(ctx['partner_ids'].ids),)
            else:
                partner_clause = 'AND l.partner_id IS NULL'
        if ctx.get('partner_categories'):
            partner_clause += 'AND (l.partner_id IN %s)'
            partner_ids = self.env['res.partner'].search([('category_id', 'in', ctx['partner_categories'].ids)]).ids
            arg_list += (tuple(partner_ids or [0]),)
        arg_list += (date_from, tuple(company_ids))

        query = '''
              SELECT DISTINCT l.partner_id, res_partner.name AS name, UPPER(res_partner.name) AS UPNAME, CASE WHEN prop.value_text IS NULL THEN 'normal' ELSE prop.value_text END AS trust
              FROM account_move_line AS l
                LEFT JOIN res_partner ON l.partner_id = res_partner.id
                LEFT JOIN ir_property prop ON (prop.res_id = 'res.partner,'||res_partner.id AND prop.name='trust' AND prop.company_id=%s),
                account_account, account_move am
              WHERE (l.account_id = account_account.id)
                  AND (l.move_id = am.id)
                  AND (am.state IN %s)
                  AND (account_account.internal_type IN %s)
                  AND (
                          l.reconciled IS NOT TRUE
                          OR l.id IN(
                              SELECT credit_move_id FROM account_partial_reconcile where max_date > %s
                              UNION ALL
                              SELECT debit_move_id FROM account_partial_reconcile where max_date > %s
                          )
                      )
                      ''' + partner_clause + '''
                  AND (l.date <= %s)
                  AND l.company_id IN %s
              ORDER BY UPPER(res_partner.name)'''
        arg_list = (self.env.company.id,) + arg_list
        cr.execute(query, arg_list)

        partners = cr.dictfetchall()
        # put a total of 0
        for i in range(7):
            total.append(0)

        # Build a string like (1,2,3) for easy use in SQL query
        partner_ids = [partner['partner_id'] for partner in partners]
        lines = dict((partner['partner_id'], []) for partner in partners)
        if not partner_ids:
            return [], [], {}

        # Use one query per period and store results in history (a list variable)
        # Each history will contain: history[1] = {'<partner_id>': <partner_debit-credit>}
        history = []
        for i in range(5):
            args_list = (tuple(move_state), tuple(account_type), tuple(partner_ids),)
            dates_query = '(COALESCE(l.date_maturity,l.date)'

            if periods[str(i)]['start'] and periods[str(i)]['stop']:
                dates_query += ' BETWEEN %s AND %s)'
                args_list += (periods[str(i)]['start'], periods[str(i)]['stop'])
            elif periods[str(i)]['start']:
                dates_query += ' >= %s)'
                args_list += (periods[str(i)]['start'],)
            else:
                dates_query += ' <= %s)'
                args_list += (periods[str(i)]['stop'],)
            args_list += (date_from, tuple(company_ids))

            query = '''SELECT l.id
                      FROM account_move_line AS l, account_account, account_move am
                      WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                          AND (am.state IN %s)
                          AND (account_account.internal_type IN %s)
                          AND ((l.partner_id IN %s) OR (l.partner_id IS NULL))
                          AND ''' + dates_query + '''
                      AND (l.date <= %s)
                      AND l.company_id IN %s
                      ORDER BY COALESCE(l.date_maturity, l.date)'''
            cr.execute(query, args_list)
            partners_amount = {}
            aml_ids = cr.fetchall()
            aml_ids = aml_ids and [x[0] for x in aml_ids] or []
            for line in self.env['account.move.line'].browse(aml_ids).with_context(prefetch_fields=False):
                partner_id = line.partner_id.id or False
                if partner_id not in partners_amount:
                    partners_amount[partner_id] = 0.0
                line_amount = line.company_id.currency_id._convert(line.balance, user_currency, user_company, date_from)
                if user_currency.is_zero(line_amount):
                    continue
                for partial_line in line.matched_debit_ids:
                    if partial_line.max_date <= date_from:
                        line_amount += partial_line.company_id.currency_id._convert(partial_line.amount, user_currency,
                                                                                    user_company, date_from)
                for partial_line in line.matched_credit_ids:
                    if partial_line.max_date <= date_from:
                        line_amount -= partial_line.company_id.currency_id._convert(partial_line.amount, user_currency,
                                                                                    user_company, date_from)

                if not self.env.company.currency_id.is_zero(line_amount):
                    partners_amount[partner_id] += line_amount
                    lines.setdefault(partner_id, [])
                    lines[partner_id].append({
                        'line': line,
                        'amount': line_amount,
                        'period': i + 1,
                    })
            history.append(partners_amount)

        # This dictionary will store the not due amount of all partners
        undue_amounts = {}
        disc_amount = {}
        total_amount = {}
        net_amount = {}
        query = '''SELECT l.id
                  FROM account_move_line AS l, account_account, account_move am
                  WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                      AND (am.state IN %s)
                      AND (account_account.internal_type IN %s)
                      AND (COALESCE(l.date_maturity,l.date) >= %s)\
                      AND ((l.partner_id IN %s) OR (l.partner_id IS NULL))
                  AND (l.date <= %s)
                  AND l.company_id IN %s
                  ORDER BY COALESCE(l.date_maturity, l.date)'''
        cr.execute(query, (
        tuple(move_state), tuple(account_type), date_from, tuple(partner_ids), date_from, tuple(company_ids)))
        aml_ids = cr.fetchall()
        aml_ids = aml_ids and [x[0] for x in aml_ids] or []
        for line in self.env['account.move.line'].browse(aml_ids):
            partner_id = line.partner_id.id or False
            if partner_id not in undue_amounts:
                undue_amounts[partner_id] = 0.0
            if partner_id not in disc_amount:
                disc_amount[partner_id] = 0.0
            line_amount = line.company_id.currency_id._convert(line.balance, user_currency, user_company, date_from)
            if user_currency.is_zero(line_amount):
                continue
            for partial_line in line.matched_debit_ids:
                if partial_line.max_date <= date_from:
                    line_amount += partial_line.company_id.currency_id._convert(partial_line.amount, user_currency,
                                                                                user_company, date_from)
            for partial_line in line.matched_credit_ids:
                if partial_line.max_date <= date_from:
                    line_amount -= partial_line.company_id.currency_id._convert(partial_line.amount, user_currency,
                                                                                user_company, date_from)
            if not self.env.company.currency_id.is_zero(line_amount):
                undue_amounts[partner_id] += line_amount
                lines.setdefault(partner_id, [])
                lines[partner_id].append({
                    'line': line,
                    'amount': line_amount,
                    'period': 6,
                })

            #     customization to get discount on aged payable account.
            discount_amount = 0.0
            if line.move_id.invoice_payment_state!='paid' and line.move_id.invoice_payment_term_id:
                if line.partner_id.discount_payment_account_id and line.move_id.invoice_payment_term_id and \
                        line.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'percent')])[0]:
                    discount_amount = (line.move_id.invoice_payment_term_id.line_ids.search(
                        [('value', '=', 'percent')])[
                                           0].value_amount / 100) * line.move_id.amount_total

                elif line.partner_id.discount_payment_account_id and line.move_id.invoice_payment_term_id and \
                        line.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[0]:
                    discount_amount = (line.move_id.invoice_payment_term_id.line_ids.search([('value', '=', 'fixed')])[
                                           0].value_amount)
            disc_amount[partner_id] += discount_amount
            total_amount[partner_id]=line.move_id.amount_total


        for partner in partners:
            if partner['partner_id'] is None:
                partner['partner_id'] = False
            at_least_one_amount = False
            values = {}
            undue_amt = 0.0
            disc_amt = 0.0
            total_amt = 0.0
            if partner['partner_id'] in undue_amounts:  # Making sure this partner actually was found by the query
                undue_amt = undue_amounts[partner['partner_id']]

            if partner['partner_id'] in disc_amount:
                disc_amt = disc_amount[partner['partner_id']]
            if partner['partner_id'] in total_amount:
                total_amt = total_amount[partner['partner_id']]

            total[6] = total[6] + undue_amt
            values['direction'] = undue_amt
            values['discount'] = disc_amt
            values['total_bill'] = total_amt
            if total_amt>0:
                values['net']=total_amt - disc_amt
            else:
                values['net'] = total_amt + disc_amt


            if not float_is_zero(values['direction'], precision_rounding=self.env.company.currency_id.rounding):
                at_least_one_amount = True

            for i in range(5):
                during = False
                if partner['partner_id'] in history[i]:
                    during = [history[i][partner['partner_id']]]
                # Adding counter
                total[(i)] = total[(i)] + (during and during[0] or 0)
                values[str(i)] = during and during[0] or 0.0
                if not float_is_zero(values[str(i)], precision_rounding=self.env.company.currency_id.rounding):
                    at_least_one_amount = True
            values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
            # Add for total
            total[(i + 1)] += values['total']
            values['partner_id'] = partner['partner_id']
            if partner['partner_id']:
                name = partner['name'] or ''
                values['name'] = len(name) >= 45 and name[0:40] + '...' or name
                values['trust'] = partner['trust']
            else:
                values['name'] = _('Unknown Partner')
                values['trust'] = False

            if at_least_one_amount or (self._context.get('include_nullified_amount') and lines[partner['partner_id']]):
                res.append(values)
        return res, total, lines