# -*- coding: utf-8 -*-
from openerp import api, models, fields

class ResPartnerInversorType(models.Model):
    _name = 'res.partner.inversor.type'

    name = fields.Char(
        string="Nombre"
    )     