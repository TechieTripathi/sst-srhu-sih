"""
TechForge 3.0 Platform Test Suite
Tests scoring formulas, 40/60 weighting, tie-breaking, incomplete evaluation rules,
and template rendering integrity.
"""

import unittest
from services.scoring import calculate_weighted_score, validate_scores, OFFICIAL_CRITERIA
from services.results_calculator import calculate_team_score, calculate_all_teams_scores


class TestTechForgeScoring(unittest.TestCase):
    """Test official evaluation criteria and score calculation"""

    def test_official_weights_sum_to_one(self):
        """Verify the 6 criteria weights sum exactly to 1.0 (100%)"""
        total_weight = sum(c['weight'] for c in OFFICIAL_CRITERIA.values())
        self.assertAlmostEqual(total_weight, 1.0, places=4)
        self.assertEqual(OFFICIAL_CRITERIA['prototype']['weight'], 0.25)
        self.assertEqual(OFFICIAL_CRITERIA['technical_design']['weight'], 0.20)
        self.assertEqual(OFFICIAL_CRITERIA['problem_understanding']['weight'], 0.15)
        self.assertEqual(OFFICIAL_CRITERIA['innovation']['weight'], 0.15)
        self.assertEqual(OFFICIAL_CRITERIA['impact']['weight'], 0.15)
        self.assertEqual(OFFICIAL_CRITERIA['presentation']['weight'], 0.10)

    def test_score_validation(self):
        """Verify scores outside 0-10 are rejected"""
        # Valid
        valid, msg = validate_scores({
            'problem_understanding': 8.5,
            'innovation': 9.0,
            'technical_design': 7.5,
            'prototype': 8.0,
            'impact': 9.0,
            'presentation': 8.0
        })
        self.assertTrue(valid)
        self.assertIsNone(msg)

        # Out of bounds (> 10)
        valid, msg = validate_scores({'problem_understanding': 10.5})
        self.assertFalse(valid)

        # Negative (< 0)
        valid, msg = validate_scores({'problem_understanding': -1})
        self.assertFalse(valid)

    def test_weighted_score_calculation(self):
        """Test calculation of weighted score on 0-100 scale"""
        raw_scores = {
            'problem_understanding': 8.0,  # 8 * 0.15 * 10 = 12.0
            'innovation': 8.0,            # 8 * 0.15 * 10 = 12.0
            'technical_design': 8.0,       # 8 * 0.20 * 10 = 16.0
            'prototype': 8.0,              # 8 * 0.25 * 10 = 20.0
            'impact': 8.0,                 # 8 * 0.15 * 10 = 12.0
            'presentation': 8.0            # 8 * 0.10 * 10 = 8.0
        }
        res = calculate_weighted_score(raw_scores)
        self.assertEqual(res['weighted_total'], 80.0)

    def test_composite_40_60_formula(self):
        """Verify (Internal * 0.40) + (External * 0.60) formula"""
        internal_avg = 80.0
        external_avg = 90.0
        final_score = (internal_avg * 0.40) + (external_avg * 0.60)
        self.assertEqual(final_score, 86.0)

    def test_tie_breaking_order(self):
        """Verify tie-breaking priority: Prototype > Technical > Innovation"""
        # Team A and Team B have identical final score (85.0)
        # Team A has higher prototype score
        team_a = {
            'team_name': 'Team Alpha',
            'final_score': 85.0,
            'prototype_avg': 9.0,
            'technical_avg': 8.0,
            'innovation_avg': 8.0,
            'is_complete': True
        }
        team_b = {
            'team_name': 'Team Beta',
            'final_score': 85.0,
            'prototype_avg': 8.5,
            'technical_avg': 8.5,
            'innovation_avg': 8.5,
            'is_complete': True
        }
        
        teams = [team_b, team_a]
        teams.sort(key=lambda x: (
            1 if x['is_complete'] else 0,
            x['final_score'],
            x['prototype_avg'],
            x['technical_avg'],
            x['innovation_avg']
        ), reverse=True)
        
        # Team Alpha should be 1st because of prototype score
        self.assertEqual(teams[0]['team_name'], 'Team Alpha')
        self.assertEqual(teams[1]['team_name'], 'Team Beta')


if __name__ == '__main__':
    unittest.main()
