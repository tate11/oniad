# -*- coding: utf-8 -*-
from openerp import api, models, fields

class ResPartnerCommunicatorType(models.Model):
    _name = 'res.partner.communicator.type'

    name = fields.Char(
        string="Nombre"
    )
    influencer = fields.Boolean(
        string="Influencer"
    )     