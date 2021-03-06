# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SurveyUserinput(models.Model):
    _inherit = 'survey.user_input'

    oniad_campaign_id = fields.Many2one(
        comodel_name='oniad.campaign',
        string='Oniad Campaign'
    )
    oniad_user_id = fields.Many2one(
        comodel_name='oniad.user',
        string='Oniad User'
    )
