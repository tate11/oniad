# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': 'Crm OniAd',
    'version': '12.0.1.0.0',    
    'author': 'Odoo Nodriza Tech (ONT)',
    'website': 'https://nodrizatech.com/',
    'category': 'Tools',
    'license': 'AGPL-3',
    'depends': ['base', 'crm'],
    'data': [
        'data/crm_lead_source_data.xml',
        'views/crm_lead_view.xml',
    ],
    'installable': True,
    'auto_install': False,    
}