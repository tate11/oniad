# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools
import json

import logging
_logger = logging.getLogger(__name__)

import boto3
from botocore.exceptions import ClientError

class OniadAddress(models.Model):
    _name = 'oniad.address'
    _description = 'Oniad Address'
    
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Contacto'
    )
    name = fields.Char(
        string='Nombre'
    )
    cp = fields.Char(
        string='Codigo postal'
    )
    cif = fields.Char(
        string='Cif'
    )
    iva = fields.Float(
        string='Iva'
    )
    city = fields.Char(
        string='Ciudad'
    )
    phone = fields.Char(
        string='Telefono'
    )
    address = fields.Char(
        string='Direccion'
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Pais'
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='Provincia'
    )
    a_number = fields.Char(
        string='A number'
    )
    res_partner_bank_id = fields.Many2one(
        comodel_name='res.partner.bank',
        string='Cuenta bancaria'
    )
    
    @api.one
    def check_res_partner(self):
        _logger.info('check_res_partner')
        partner_vals = {
            'name': self.name,
            'customer': True,
            'is_company': True,
            'country_id': self.country_id.id,
            'city': self.city,
            'street': self.address,
            'zip': self.cp,
            'state_id': self.state_id.id,
            'vat': str(self.country_id.code.upper())+str(self.cif)             
        }
        #phone
        if self.phone!=False:
            first_char_phone = self.phone[:1]
            mobile_first_chars = [6,7]
            if first_char_phone in mobile_first_chars:
                partner_vals['mobile'] = self.phone
            else:
                partner_vals['phone'] = self.phone                
        #operations
        if self.partner_id.id==0:
            #check_if_need_create of previously exists
            vat_need_check = str(self.country_id.code)+str(self.cif)            
            res_partner_ids = self.env['res.partner'].search([('is_company', '=', True),('vat', '=', vat_need_check)])
            if len(res_partner_ids)>0:
                self.partner_id = res_partner_ids[0].id
            else:                                            
                #create
                res_partner_obj = self.env['res.partner'].sudo().create(partner_vals)
                if res_partner_obj.id>0:
                    self.partner_id = res_partner_obj.id
        else:
            self.partner_id.update(partner_vals)
        #res_partner_bank_id
        if self.a_number!=False and self.res_partner_bank_id.id==0:
            partner_bank_vals = {
                'acc_number': self.a_number,
                'partner_id': self.partner_id.id,
            }
            res_partner_bank_obj = self.env['res.partner.bank'].sudo().create(partner_bank_vals)
            if res_partner_bank_obj.id>0:
                self.res_partner_bank_id = res_partner_bank_obj.id
                                            
    @api.model
    def create(self, values):
        return_item = super(OniadAddress, self).create(values)
        #operations
        return_item.check_res_partner()
        #return
        return return_item
    
    @api.one
    def write(self, vals):                        
        return_write = super(OniadAddress, self).write(vals)
        #operations
        self.check_res_partner()
        #return    
        return return_write
        
    @api.multi    
    def cron_sqs_oniad_address(self, cr=None, uid=False, context=None):
        _logger.info('cron_sqs_oniad_address')
        
        sqs_oniad_address_url = tools.config.get('sqs_oniad_address_url')
        AWS_ACCESS_KEY_ID = tools.config.get('aws_access_key_id')        
        AWS_SECRET_ACCESS_KEY = tools.config.get('aws_secret_key_id')
        AWS_SMS_REGION_NAME = tools.config.get('aws_region_name')                        
        #boto3
        sqs = boto3.client(
            'sqs',
            region_name=AWS_SMS_REGION_NAME, 
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key= AWS_SECRET_ACCESS_KEY
        )        
        # Receive message from SQS queue
        total_messages = 10
        while total_messages>0:
            response = sqs.receive_message(
                QueueUrl=sqs_oniad_address_url,
                AttributeNames=['All'],
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All']
            )
            if 'Messages' in response:
                total_messages = len(response['Messages'])
            else:
                total_messages = 0
            #continue
            if 'Messages' in response:
                for message in response['Messages']:
                    #message_body           
                    message_body = json.loads(message['Body'])
                    #fix message
                    if 'Message' in message_body:
                        message_body = json.loads(message_body['Message'])
                    #result_message
                    result_message = {
                        'statusCode': 200,
                        'return_body': 'OK',
                        'message': message_body
                    }
                    #fields_need_check
                    fields_need_check = ['id']
                    for field_need_check in fields_need_check:
                        if field_need_check not in message_body:
                            result_message['statusCode'] = 500
                            result_message['return_body'] = 'No existe el campo '+str(field_need_check)
                    #operations
                    if result_message['statusCode']==200:
                        previously_found = False
                        id_item = int(message_body['id'])
                        oniad_address_ids = self.env['oniad.address'].search([('id', '=', id_item)])
                        if len(oniad_address_ids)>0:
                            previously_found = True
                        #params
                        data_oniad_address = {
                            'name': str(message_body['name'].encode('utf-8'))
                        }
                        #fields_need_check
                        fields_need_check = ['cp', 'cif', 'iva', 'city', 'phone', 'address', 'a_number']
                        for field_need_check in fields_need_check:
                            if field_need_check in message_body:
                                if message_body[field_need_check]!='':
                                    if message_body[field_need_check]!=None:
                                        if field_need_check in ['city', 'address']:
                                            data_oniad_address[field_need_check] = str(message_body[field_need_check].encode('utf-8'))
                                        else:
                                            data_oniad_address[field_need_check] = str(message_body[field_need_check])
                        #country_id
                        if 'country' in message_body:
                            if message_body['country']!='':
                                res_country_ids = self.env['res.country'].search([('code', '=', str(message_body['country']))])
                                if len(res_country_ids)>0:
                                    res_country_id = res_country_ids[0]
                                    data_oniad_address['country_id'] = res_country_id.id
                        #state
                        if 'state' in message_body:
                            if message_body['state']!='':
                                oniad_country_state_ids = self.env['oniad.country.state'].search([('iso_code', '=', str(message_body['state']))])
                                if len(oniad_country_state_ids)>0:
                                    oniad_country_state_id = oniad_country_state_ids[0]
                                    data_oniad_address['state_id'] = oniad_country_state_id.id                        
                        #add_id
                        if previously_found==False:
                            data_oniad_address['id'] = int(message_body['id'])                                            
                        #final_operations
                        result_message['data'] = data_oniad_address
                        _logger.info(result_message)
                        #create-write
                        if previously_found==False:                            
                            oniad_address_obj = self.env['oniad.address'].sudo().create(data_oniad_address)
                        else:
                            oniad_address_id = oniad_address_ids[0]
                            #write
                            oniad_address_id.write(data_oniad_address)                                                    
                    #remove_message                
                    if result_message['statusCode']==200:                
                        response_delete_message = sqs.delete_message(
                            QueueUrl=sqs_oniad_address_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )                  