# -*- coding: utf-8 -*-
from openerp import api, models, fields

class ResPartnerAsociationGeo(models.Model):
    _name = 'res.partner.asociation.geo'

    name = fields.Char(
        string="Nombre"
    )     