# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models, tools, _
from dateutil.relativedelta import relativedelta
from datetime import datetime
import dateutil.parser
import json
import logging
import boto3
_logger = logging.getLogger(__name__)


class OniadTransaction(models.Model):
    _name = 'oniad.transaction'
    _description = 'Oniad Transaction'

    account_payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Payment'
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Sale order'
    )
    account_invoice_id = fields.Many2one(
        comodel_name='account.invoice',
        string='Invoice'
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency'
    )
    amount = fields.Monetary(
        string='Amount'
    )
    tax = fields.Monetary(
        string='Tax'
    )
    total = fields.Monetary(
        string='Total'
    )
    date = fields.Date(
        string='Date'
    )
    oniad_user_id = fields.Many2one(
        comodel_name='oniad.user',
        string='Oniad User'
    )
    oniad_address_id = fields.Many2one(
        comodel_name='oniad.address',
        string='Oniad Address'
    )
    type = fields.Selection(
        selection=[
            ('TYPE_CREDIT', 'Credit'),
            ('TYPE_COMMISSION', 'Commission'),
            ('TYPE_SERVICE', 'Service')
        ],
        string='Type'
    )
    state = fields.Selection(
        selection=[
            ('STATUS_PENDING', 'Pending'),
            ('STATUS_COMPLETED', 'Completed'),
            ('STATUS_CANCELLED', 'Cancelled')
        ],
        string='State'
    )
    actor = fields.Selection(
        selection=[
            ('ACTOR_ONIAD', 'Oniad'),
            ('ACTOR_USER', 'User'),
            ('ACTOR_AGENCY', 'Agency'),
            ('ACTOR_ACCOUNT', 'Account')
        ],
        string='Actor'
    )
    medium = fields.Selection(
        selection=[
            ('MEDIUM_STRIPE', 'Stripe'),
            ('MEDIUM_BRAINTREE', 'Braintree'),
            ('MEDIUM_INTERNAL', 'Internal'),
            ('MEDIUM_OFFLINE', 'Offline')
        ],
        string='Medium'
    )
    subject = fields.Selection(
        selection=[
            ('SUBJECT_CHARGE', 'Pago ONiAD'),
            ('SUBJECT_VOUCHER', 'Cupón aplicado'),
            ('SUBJECT_BANNERS', 'Diseño de creatividades'),
            ('SUBJECT_COMPENSATION', 'Compensación comercial'),
            ('SUBJECT_GIFT', 'Promoción'),
            ('SUBJECT_REFUND', 'Reembolso'),
            ('SUBJECT_CONVERT_COMMISSION_TO_CREDIT', 'Comisión Afiliado a crédito'),
            (
                'SUBJECT_CONVERT_AGENCYCOMMISSION_TO_CREDIT',
                'Comisión Partner a crédito'
            ),
            ('SUBJECT_SETTLEMENT', 'Liquidación'),
            ('SUBJECT_TRANSFER', 'Transferencia'),
            ('SUBJECT_COMMISSION_RECOMMENDED', 'Programa de recomendados'),
            ('SUBJECT_COMMISSION_AGENCY', 'Programa de Partners'),
            ('SUBJECT_COMMISSION', 'Programa de Afiliados')
        ],
        string='Subject'
    )

    @api.multi
    def check_account_payment(self):
        self.ensure_one()
        # define
        stranger_ids_need_skip = [1743, 52076, 52270, 52271, 52281]
        # need_create_account_payment
        need_create_account_payment = False
        if self.id > 94:  # Fix eliminar los de 2017
            if self.id not in stranger_ids_need_skip:
                if self.type != 'TYPE_COMMISSION':
                    if self.subject in \
                            ['SUBJECT_CHARGE', 'SUBJECT_REFUND', 'SUBJECT_BANNERS']:
                        if self.medium == 'MEDIUM_STRIPE':
                            if self.create_date.strftime("%Y-%m-%d") > '2020-01-01':
                                need_create_account_payment = True
        # need_create_account_invoice | need_create_sale_order
        need_create_account_invoice = False
        need_create_sale_order = False
        # Operations check if sale_order or account_invoice need create
        if self.id > 94:  # Fix eliminar los de 2017
            if self.id not in stranger_ids_need_skip:
                if self.type != 'TYPE_COMMISSION':
                    if self.subject in ['SUBJECT_CHARGE', 'SUBJECT_REFUND']:
                        if self.medium == 'MEDIUM_OFFLINE':
                            if self.create_date.strftime("%Y-%m-%d") > '2020-02-12':
                                if self.oniad_address_id.partner_id.credit_limit > 0:
                                    need_create_account_invoice = True
                                else:
                                    need_create_sale_order = True
        # operations need_create_account_payment
        if need_create_account_payment:
            if self.account_payment_id.id == 0:
                # account.payment
                vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'payment_method_id': 1,
                    'state': 'draft',
                    'currency_id': self.currency_id.id,
                    'partner_id': self.oniad_address_id.partner_id.id,
                    'oniad_user_id': self.oniad_user_id.id,
                    'journal_id': int(
                        self.env[
                            'ir.config_parameter'
                        ].sudo().get_param('oniad_stripe_journal_id')
                    ),
                    'amount': self.total,
                    'payment_date': self.date,
                    'oniad_purchase_price': 0,
                    'communication': dict(
                        self.fields_get(allfields=['subject'])['subject']['selection']
                    )[self.subject],
                    'oniad_transaction_id': self.id,
                }
                # oniad_product_id
                if self.type == 'TYPE_CREDIT':
                    vals['oniad_product_id'] = int(
                        self.env[
                            'ir.config_parameter'
                        ].sudo().get_param('oniad_credit_product_id')
                    )
                elif self.type == 'TYPE_SERVICE':
                    vals['oniad_product_id'] = int(
                        self.env[
                            'ir.config_parameter'
                        ].sudo().get_param('oniad_service_product_id')
                    )
                # oniad_purchase_price
                if self.type == 'TYPE_CREDIT':
                    vals['oniad_purchase_price'] = self.total*0.5
                # communication
                subjects_with_date = ['SUBJECT_CHARGE', 'SUBJECT_REFUND']
                if self.subject in subjects_with_date:
                    date_explode = self.date.strftime("%Y-%m-%d").split('-')
                    vals['communication'] = '%s  %s/%s/%s' % (
                        vals['communication'],
                        date_explode[2],
                        date_explode[1],
                        date_explode[0]
                    )
                # SUBJECT_REFUND
                if self.subject == 'SUBJECT_REFUND':
                    vals['payment_type'] = 'outbound'
                    vals['oniad_purchase_price'] = 0
                    # fix negative amounts
                    if self.total < 0:
                        vals['amount'] = self.total*-1
                # create
                payment_obj = self.env['account.payment'].sudo().create(vals)
                if payment_obj.id > 0:
                    self.account_payment_id = payment_obj.id
                    if self.account_payment_id.state == 'draft':
                        self.account_payment_id.post()
            else:
                if self.account_payment_id.state == 'draft':
                    self.account_payment_id.post()
        # operations need_create_account_invoice
        if need_create_account_invoice:
            if self.sale_order_id.id == 0 and self.account_invoice_id.id == 0:
                # define
                oniad_account_invoice_journal_id = int(
                    self.env[
                        'ir.config_parameter'
                    ].sudo().get_param('oniad_account_invoice_journal_id')
                )
                oniad_product_id = int(
                    self.env[
                        'ir.config_parameter'
                    ].sudo().get_param('oniad_credit_product_id')
                )
                product = self.env['product.product'].search(
                    [
                        ('id', '=', oniad_product_id)
                    ]
                )
                communication = dict(
                    self.fields_get(allfields=['subject'])
                    ['subject']['selection']
                )[self.subject]
                allow_create = True
                # creamos una factura con la linea de esta transaccion
                oap = self.oniad_address_id.partner_id
                vals = {
                    'partner_id': oap.id,
                    'partner_shipping_id': oap.id,
                    'account_id': oap.property_account_receivable_id.id,
                    'journal_id': oniad_account_invoice_journal_id,
                    'state': 'draft',
                    'comment': ' ',
                    'currency_id': self.currency_id.id,
                }
                # payment_mode_id
                if oap.customer_payment_mode_id:
                    vals['payment_mode_id'] = oap.customer_payment_mode_id.id
                    # check_mandate_required
                    if oap.customer_payment_mode_id.payment_method_id.mandate_required:
                        # search
                        if self.oniad_address_id.res_partner_bank_id:
                            oa_rpb = self.oniad_address_id.res_partner_bank_id
                            if oa_rpb.mandate_id:
                                for mandate_id in oa_rpb.mandate_ids:
                                    if 'mandate_id' not in vals:
                                        if mandate_id.state == 'valid':
                                            vals['mandate_id'] = mandate_id.id
                                            vals['partner_bank_id'] = \
                                                mandate_id.partner_bank_id.id
                        # check_continue
                        if 'mandate_id' not in vals:
                            allow_create = False
                            _logger.info(
                                _('No bank mandates, invoice cannot be created')
                            )
                # payment_term_id
                if oap.property_payment_term_id:
                    vals['payment_term_id'] = oap.property_payment_term_id.id
                # fiscal_position_id
                if oap.property_account_position_id:
                    vals['fiscal_position_id'] = oap.property_account_position_id.id
                # user_id
                if self.oniad_user_id.partner_id:
                    ou_partner = self.oniad_user_id.partner_id
                    if ou_partner.user_id:
                        vals['user_id'] = ou_partner.user_id.id
                        #  team_id
                        if ou_partner.user_id.sale_team_id:
                            vals['team_id'] = ou_partner.user_id.sale_team_id.id
                # create
                if allow_create:
                    invoice_obj = self.env['account.invoice'].sudo().create(vals)
                    # lines
                    vals = {
                        'invoice_id': invoice_obj.id,
                        'oniad_transaction_id': self.id,
                        'name': communication,
                        'quantity': 1,
                        'price_unit': self.amount,
                        'account_id': product.property_account_income_id.id,
                        'purchase_price': self.total*0.5,
                        'currency_id': self.currency_id.id,
                        'product_id': oniad_product_id
                    }
                    self.env['account.invoice.line'].sudo().create(vals)
                    # compute_taxes
                    invoice_obj.compute_taxes()
                    # valid
                    invoice_obj.action_invoice_open()
                    # save account_invoice_id
                    self.account_invoice_id = invoice_obj.id
        # need_create_sale_order
        if need_create_sale_order:
            # check_if_need_create
            if self.sale_order_id.id == 0:
                # define
                oniad_product_id = int(
                    self.env[
                        'ir.config_parameter'
                    ].sudo().get_param('oniad_credit_product_id')
                )
                product = self.env['product.product'].search(
                    [
                        ('id', '=', oniad_product_id)
                    ]
                )
                communication = dict(
                    self.fields_get(allfields=['subject'])
                    ['subject']['selection']
                )[self.subject]
                # vals
                oup = self.oniad_user_id.partner_id
                oap = self.oniad_address_id.partner_id
                vals = {
                    'partner_id': oup.id,
                    'partner_shipping_id': oup.id,
                    'partner_invoice_id': oap.id,
                    'state': 'sent',
                    'note': '',
                    'currency_id': self.currency_id.id,
                }
                # payment_mode_id
                if oap.customer_payment_mode_id:
                    vals['payment_mode_id'] = \
                        oap.customer_payment_mode_id.id
                # payment_term_id
                if oap.property_payment_term_id:
                    vals['payment_term_id'] = \
                        oap.property_payment_term_id.id
                # fiscal_position_id
                if oap.property_account_position_id:
                    vals['fiscal_position_id'] = \
                        oap.property_account_position_id.id
                # user_id
                if oup:
                    if oup.user_id:
                        vals['user_id'] = oup.user_id.id
                        # team_id
                        if oup.user_id.sale_team_id:
                            vals['team_id'] = oup.user_id.sale_team_id.id
                # create
                if 'user_id' in vals:
                    order_obj = self.env['sale.order'].sudo(
                        vals['user_id']
                    ).create(vals)
                else:
                    order_obj = self.env['sale.order'].sudo().create(vals)
                # lines
                vals = {
                    'order_id': order_obj.id,
                    'oniad_transaction_id': self.id,
                    'name': communication,
                    'product_qty': 1,
                    'price_unit': self.amount,
                    'price_subtotal': self.total,
                    'purchase_price': self.total*0.5,
                    'currency_id': self.currency_id.id,
                    'product_id': oniad_product_id
                }
                self.env['sale.order.line'].sudo(
                    order_obj.create_uid
                ).create(vals)
                # valid
                order_obj.state = 'sent'
                # save sale_order_id
                self.sale_order_id = order_obj.id

    @api.model
    def create(self, values):
        return_item = super(OniadTransaction, self).create(values)
        # operations
        return_item.check_account_payment()
        # return
        return return_item

    @api.multi
    def write(self, vals):
        return_write = super(OniadTransaction, self).write(vals)
        # operations
        self.check_account_payment()
        # return
        return return_write

    @api.model
    def cron_sqs_oniad_transaction(self):
        _logger.info('cron_sqs_oniad_transaction')
        sqs_url = tools.config.get('sqs_oniad_transaction_url')
        AWS_ACCESS_KEY_ID = tools.config.get('aws_access_key_id')
        AWS_SECRET_ACCESS_KEY = tools.config.get('aws_secret_key_id')
        AWS_SMS_REGION_NAME = tools.config.get('aws_region_name')
        # boto3
        sqs = boto3.client(
            'sqs',
            region_name=AWS_SMS_REGION_NAME,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        # Receive message from SQS queue
        total_messages = 10
        while total_messages > 0:
            response = sqs.receive_message(
                QueueUrl=sqs_url,
                AttributeNames=['All'],
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All']
            )
            if 'Messages' in response:
                total_messages = len(response['Messages'])
            else:
                total_messages = 0
            # continue
            if 'Messages' in response:
                for message in response['Messages']:
                    # message_body
                    message_body = json.loads(message['Body'])
                    # fix message
                    if 'Message' in message_body:
                        message_body = json.loads(message_body['Message'])
                    # result_message
                    result_message = {
                        'statusCode': 200,
                        'return_body': 'OK',
                        'message': message_body
                    }
                    # fields_need_check
                    fields_need_check = ['id']
                    for fnc in fields_need_check:
                        if fnc not in message_body:
                            result_message['statusCode'] = 500
                            result_message['return_body'] = \
                                _('The field does not exist %s') % fnc
                    # operations
                    if result_message['statusCode'] == 200:
                        previously_found = False
                        id_item = int(message_body['id'])
                        transaction_ids = self.env['oniad.transaction'].search(
                            [
                                ('id', '=', id_item)
                            ]
                        )
                        if transaction_ids:
                            previously_found = True
                        # params
                        vals = {
                            'currency_id': 1,
                            'amount': str(message_body['amount']),
                            'tax': str(message_body['tax']),
                            'total': str(message_body['total']),
                            'oniad_user_id': int(message_body['actor_destination_id']),
                            'oniad_address_id': int(message_body['address_id']),
                            'type': str(message_body['type']),
                            'state': str(message_body['status']),
                            'actor': str(message_body['actor_origin']),
                            'medium': str(message_body['medium_type']),
                            'subject': str(message_body['subject']),
                        }
                        # completed_at
                        completed_at = dateutil.parser.parse(
                            str(message_body['completed_at'])
                        )
                        completed_at = completed_at.replace() - completed_at.utcoffset()
                        vals['date'] = completed_at.strftime("%Y-%m-%d %H:%M:%S")
                        vals['create_date'] = completed_at.strftime("%Y-%m-%d %H:%M:%S")
                        # fix prevent error oniad_user_id
                        if vals['oniad_user_id'] == '0':
                            del vals['oniad_user_id']
                            # result
                            result_message['statusCode'] = 500
                            result_message['return_body'] = \
                                _('The oniad_user_id field cannot be 0')
                        # add_id
                        if not previously_found:
                            vals['id'] = int(message_body['id'])
                        # search oniad_user_id (prevent errors)
                        if 'oniad_user_id' in vals:
                            if vals['oniad_user_id'] > 0:
                                user_ids = self.env['oniad.user'].search(
                                    [
                                        ('id', '=', int(vals['oniad_user_id']))
                                    ]
                                )
                                if len(user_ids) == 0:
                                    result_message['statusCode'] = 500
                                    result_message['return_body'] = \
                                        _('The oniad_user_id=%s does not exist') \
                                        % vals['oniad_user_id']
                        # search oniad_address_id (prevent errors)
                        if 'oniad_address_id' in vals:
                            if vals['oniad_address_id'] == 0:
                                result_message['statusCode'] = 500
                                result_message['return_body'] = \
                                    _('The oniad_address_id field cannot be 0')
                            else:
                                address_ids = self.env['oniad.address'].search(
                                    [
                                        ('id', '=', int(vals['oniad_address_id']))
                                    ]
                                )
                                if len(address_ids) == 0:
                                    result_message['statusCode'] = 500
                                    result_message['return_body'] = \
                                        _('The oniad_address_id=%s does not exist') \
                                        % vals['oniad_address_id']
                        # final_operations
                        result_message['data'] = vals
                        _logger.info(result_message)
                        # create-write
                        if result_message['statusCode'] == 200:
                            if previously_found:
                                transaction_ids[0].write(vals)
                            else:
                                self.env['oniad.transaction'].sudo().create(vals)
                    # remove_message
                    if result_message['statusCode'] == 200:
                        sqs.delete_message(
                            QueueUrl=sqs_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )

    @api.model
    def cron_action_account_invoices_generate(self):
        _logger.info('cron_action_account_invoices_generate')
        # define
        oniad_stripe_journal_id = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'oniad_stripe_journal_id'
            )
        )
        oniad_account_invoice_journal_id = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'oniad_account_invoice_journal_id'
            )
        )
        oniad_account_invoice_product = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'oniad_account_invoice_product'
            )
        )
        product = self.env['product.product'].search(
            [
                ('id', '=', oniad_account_invoice_product)
            ]
        )
        # dates
        current_date = datetime.today()
        start_date = current_date + relativedelta(months=-1, day=1)
        end_date = datetime(
            start_date.year,
            start_date.month,
            1
        ) + relativedelta(months=1, days=-1)
        date_invoice = end_date
        if end_date.day == 31 and end_date.month == 12:
            date_invoice = date_invoice + relativedelta(days=-1)
        # account_invoice_line
        line_ids = self.env['account.invoice.line'].search(
            [
                ('oniad_transaction_id', '!=', False)]
        )

        if line_ids:
            line_ids_mapped = line_ids.mapped('oniad_transaction_id')
            # oniad_transaction_ids
            transaction_ids = self.env['oniad.transaction'].search(
                [
                    ('id', '>', 94),
                    ('id', 'not in', (1743, 52076, 52270, 52271, 52281)),
                    ('type', 'in', ('TYPE_CREDIT', 'TYPE_SERVICE')),
                    ('state', '=', 'STATUS_COMPLETED'),
                    ('actor', '=', 'ACTOR_ONIAD'),
                    ('medium', '=', 'MEDIUM_STRIPE'),
                    (
                        'subject',
                        'in',
                        (
                            'SUBJECT_CHARGE',
                            'SUBJECT_BANNERS',
                            'SUBJECT_REFUND'
                        )
                    ),
                    ('account_payment_id', '!=', False),
                    ('account_payment_id.journal_id', '=', oniad_stripe_journal_id),
                    ('account_payment_id.state', 'in', ('posted', 'sent')),
                    ('account_payment_id.payment_type', 'in', ('inbound', 'outbound')),
                    (
                        'account_payment_id.payment_date',
                        '<=',
                        end_date.strftime("%Y-%m-%d")
                    ),
                    ('date', '>=', '2020-01-01'),
                    ('id', 'not in', line_ids_mapped.ids)
                ]
            )
            if transaction_ids:
                partner_payments = {}
                for transaction_id in transaction_ids:
                    t_ap = transaction_id.account_payment_id
                    payment_with_invoice = False
                    if t_ap.has_invoices:
                        payment_with_invoice = True

                    if not payment_with_invoice:
                        if t_ap.partner_id.id not in partner_payments:
                            partner_payments[t_ap.partner_id.id] = []
                        # append
                        partner_payments[t_ap.partner_id.id].append(
                            transaction_id.account_payment_id
                        )
                # operations
                _logger.info(_('Invoices to create: %s') % len(partner_payments))
                if len(partner_payments) > 0:
                    count = 0
                    # for
                    for partner_id, partner_payments_item in partner_payments.items():
                        count += 1
                        # types
                        partner_payments_by_type = {'inbound': [], 'outbound': []}
                        payment_types_item_amount = {'inbound': 0, 'outbound': 0}
                        # calculate_total and by_type
                        for partner_payment_item in partner_payments_item:
                            # amount
                            payment_types_item_amount[
                                str(partner_payment_item.payment_type)
                            ] += partner_payment_item.amount
                            # add_items
                            partner_payments_by_type[
                                str(partner_payment_item.payment_type)
                            ].append(partner_payment_item)
                        # operations
                        # inbound
                        if payment_types_item_amount['inbound'] > 0:
                            # partner_payment_by_type_item_0
                            pp_type_item_0 = partner_payments_by_type['inbound'][0]
                            # partner
                            partner = pp_type_item_0.partner_id
                            # percent
                            percent = (float(count)/float(len(partner_payments)))*100
                            percent = "{0:.2f}".format(percent)
                            # account.invoice
                            vals = {
                                'partner_id': partner.id,
                                'partner_shipping_id': partner.id,
                                'account_id': partner.property_account_receivable_id.id,
                                'journal_id': oniad_account_invoice_journal_id,
                                'date': date_invoice.strftime("%Y-%m-%d"),
                                'date_invoice': date_invoice.strftime("%Y-%m-%d"),
                                'date_due': date_invoice.strftime("%Y-%m-%d"),
                                'state': 'draft',
                                'comment': ' ',
                                'currency_id': pp_type_item_0.currency_id.id
                            }
                            # user_id (el del partner_payment_by_type_item_0 >
                            # oniad_user_id > partner_id > user_id)
                            pp_item_0_ot = pp_type_item_0.oniad_transaction_id
                            if pp_item_0_ot:
                                if pp_item_0_ot.oniad_user_id:
                                    pp_item_0_ot_ou = pp_item_0_ot.oniad_user_id
                                    if pp_item_0_ot_ou.partner_id:
                                        pp_item_0_ot_ou_p = pp_item_0_ot_ou.partner_id
                                        if pp_item_0_ot_ou_p.user_id:
                                            vals['user_id'] = \
                                                pp_item_0_ot_ou_p.user_id.id
                            # continue
                            _logger.info(
                                _('Prepare to generate partner_id %s and '
                                  'partner_shipping_id %s')
                                % (
                                    vals['partner_id'],
                                    partner.id
                                )
                            )
                            invoice_obj = self.env['account.invoice'].sudo().create(
                                vals
                            )
                            _logger.info(
                                _('Invoice %s created successfully')
                                % invoice_obj.id
                            )
                            # account.invoice.lines (creamos las lineas segun
                            # los pagos partner_payments_by_type['inbound'])
                            for payment_id in partner_payments_by_type['inbound']:
                                # account_invoice_line_vals
                                line_vals = {
                                    'invoice_id': invoice_obj.id,
                                    'oniad_transaction_id':
                                        payment_id.oniad_transaction_id.id,
                                    'product_id': product.id,
                                    'name': payment_id.communication,
                                    'quantity': 1,
                                    'price_unit': payment_id.amount,
                                    'account_id': product.property_account_income_id.id,
                                    'purchase_price': payment_id.oniad_purchase_price,
                                    'currency_id': payment_id.currency_id.id
                                }
                                # oniad_product_id
                                if payment_id.oniad_product_id:
                                    line_vals['product_id'] = \
                                        payment_id.oniad_product_id.id
                                # create
                                line_obj = self.env[
                                    'account.invoice.line'
                                ].sudo().create(
                                    line_vals
                                )
                                # name
                                line_obj.name = payment_id.communication
                            # Fix check totals
                            payment_id.compute_taxes()
                            # operations
                            if invoice_obj.partner_id.vat \
                                    and invoice_obj.partner_id.vat != "":
                                invoice_obj.action_invoice_open()
                                _logger.info(
                                    _('Invoice %s successfully validated')
                                    % invoice_obj.id
                                )
                                invoice_obj.action_auto_create_message_slack()
                            # logger_percent
                            _logger.info('%s%s (%s/%s)' % (
                                percent,
                                '%',
                                count,
                                len(partner_payments)
                            ))
                        # outbound
                        if payment_types_item_amount['outbound'] > 0:
                            # partner_payment_by_type_item_0
                            pp_type_item_0 = partner_payments_by_type['outbound'][0]
                            # search out_invoice
                            invoice_ids_out_invoice = self.env[
                                'account.invoice'
                            ].search(
                                [
                                    ('type', '=', 'out_invoice'),
                                    ('partner_id', '=', pp_type_item_0.partner_id.id),
                                    (
                                        'amount_total',
                                        '>=',
                                        payment_types_item_amount['outbound']
                                    )
                                ],
                                order="date_invoice desc"
                            )
                            if invoice_ids_out_invoice:
                                invoice_id_out_invoice = invoice_ids_out_invoice[0]
                                _logger.info(
                                    _('We create negative related to %s')
                                    % invoice_id_out_invoice.id
                                )
                                invoice_out_partner = invoice_id_out_invoice.partner_id
                                invoice_out_partner_par = \
                                    invoice_out_partner.property_account_receivable
                                # percent
                                percent = (float(count) / float(len(partner_payments)))
                                percent = percent*100
                                percent = "{0:.2f}".format(percent)
                                # account_invoice_vals
                                vals = {
                                    'partner_id': invoice_out_partner.id,
                                    'partner_shipping_id': invoice_out_partner.id,
                                    'account_id': invoice_out_partner_par.id,
                                    'journal_id': invoice_id_out_invoice.journal_id.id,
                                    'date': date_invoice.strftime("%Y-%m-%d"),
                                    'date_invoice': date_invoice.strftime("%Y-%m-%d"),
                                    'date_due': date_invoice.strftime("%Y-%m-%d"),
                                    'state': 'draft',
                                    'type': 'out_refund',
                                    'origin': invoice_id_out_invoice.number,
                                    'name': 'Devolucion',
                                    'comment': ' ',
                                    'currency_id': invoice_id_out_invoice.currency_id.id
                                }
                                # user_id
                                if invoice_id_out_invoice.user_id.id:
                                    vals['user_id'] = invoice_id_out_invoice.user_id.id
                                # continue
                                _logger.info(
                                    _(
                                        'Prepare to generate partner_id %s and '
                                        'partner_shipping_id %s'
                                    )
                                    % (
                                        vals['partner_id'],
                                        vals['partner_id']
                                    )
                                )
                                invoice_obj = self.env[
                                    'account.invoice'
                                ].sudo().create(vals)
                                _logger.info(
                                    _('Invoice %s created successfully')
                                    % invoice_obj.id
                                )
                                # account.invoice.lines (creamos las lineas segun
                                # los pagos partner_payments_by_type['outbound'])
                                for payment_id in partner_payments_by_type['outbound']:
                                    # account_invoice_line_vals
                                    line_vals = {
                                        'invoice_id': invoice_obj.id,
                                        'oniad_transaction_id':
                                            payment_id.oniad_transaction_id.id,
                                        'product_id': product.id,
                                        'name': payment_id.communication,
                                        'quantity': 1,
                                        'price_unit': payment_id.amount,
                                        'account_id':
                                            product.property_account_income_id.id,
                                        'currency_id': payment_id.currency_id.id
                                    }
                                    # Fix price_unit (prevent negative)
                                    if line_vals['price_unit'] < 0:
                                        line_vals['price_unit'] = \
                                            line_vals['price_unit'] * -1
                                    # oniad_product_id
                                    if payment_id.oniad_product_id:
                                        line_vals['product_id'] = \
                                            payment_id.oniad_product_id.id
                                    # create
                                    line_obj = self.env[
                                        'account.invoice.line'
                                    ].sudo().create(line_vals)
                                    # name
                                    line_obj.name = payment_id.communication
                                # Fix check totals
                                invoice_obj.compute_taxes()
                                # operations
                                if invoice_obj.partner_id.vat \
                                        and invoice_obj.partner_id.vat != "":
                                    invoice_obj.action_invoice_open()
                                    _logger.info(
                                        _('Invoice %s successfully validated')
                                        % invoice_obj.id
                                    )
                                    invoice_obj.action_auto_create_message_slack()
                                # logger_percent
                                _logger.info('%s%s (%s/%s)' % (
                                    percent,
                                    '%',
                                    count,
                                    len(partner_payments)
                                ))
                            else:
                                _logger.info(
                                    _('NO positive invoice of higher amount found '
                                      '- SHOULD BE FULLY IMPOSSIBLE')
                                )
