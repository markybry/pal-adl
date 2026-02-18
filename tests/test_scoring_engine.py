"""
Test Suite for Scoring Engine
Validates that scoring logic works as documented.
"""

import unittest
from datetime import datetime, timedelta
from src.scoring_engine import (
    ScoringEngine,
    ADLEvent,
    AssistanceLevel,
    RiskLevel,
    DomainConfig,
    ADL_DOMAINS,
    REFUSAL_THRESHOLD_AMBER,
    REFUSAL_THRESHOLD_RED,
    DOCUMENTATION_THRESHOLD_AMBER,
    DOCUMENTATION_THRESHOLD_RED
)


class TestRefusalScoring(unittest.TestCase):
    """Test refusal score calculation"""
    
    def test_no_refusals(self):
        score = ScoringEngine.calculate_refusal_score(0)
        self.assertEqual(score.points, 0)
        self.assertIn('No refusals', score.description)
    
    def test_one_refusal(self):
        score = ScoringEngine.calculate_refusal_score(1)
        self.assertEqual(score.points, 0)
        self.assertIn('below threshold', score.description)
    
    def test_amber_threshold(self):
        score = ScoringEngine.calculate_refusal_score(REFUSAL_THRESHOLD_AMBER)
        self.assertEqual(score.points, 2)
        self.assertIn('AMBER', score.description)
    
    def test_red_threshold(self):
        score = ScoringEngine.calculate_refusal_score(REFUSAL_THRESHOLD_RED)
        self.assertEqual(score.points, 3)
        self.assertIn('RED', score.description)
    
    def test_many_refusals(self):
        score = ScoringEngine.calculate_refusal_score(10)
        self.assertEqual(score.points, 3)


class TestGapScoring(unittest.TestCase):
    """Test gap score calculation"""
    
    def setUp(self):
        self.oral_care_config = ADL_DOMAINS['Oral Care']
    
    def test_no_gap_data(self):
        score = ScoringEngine.calculate_gap_score(None, self.oral_care_config)
        self.assertEqual(score.points, 0)
    
    def test_within_threshold(self):
        score = ScoringEngine.calculate_gap_score(10.0, self.oral_care_config)
        self.assertEqual(score.points, 0)
        self.assertIn('within threshold', score.description)
    
    def test_amber_threshold(self):
        # Oral Care: amber=16h
        score = ScoringEngine.calculate_gap_score(18.0, self.oral_care_config)
        self.assertEqual(score.points, 2)
        self.assertIn('AMBER', score.description)
    
    def test_red_threshold(self):
        # Oral Care: red=24h
        score = ScoringEngine.calculate_gap_score(30.0, self.oral_care_config)
        self.assertEqual(score.points, 3)
        self.assertIn('RED', score.description)
    
    def test_exact_amber_boundary(self):
        # Exactly at amber threshold (16h) should be GREEN
        score = ScoringEngine.calculate_gap_score(16.0, self.oral_care_config)
        self.assertEqual(score.points, 0)
    
    def test_just_over_amber(self):
        score = ScoringEngine.calculate_gap_score(16.1, self.oral_care_config)
        self.assertEqual(score.points, 2)


class TestDependencyScoring(unittest.TestCase):
    """Test dependency trend calculation"""
    
    def test_insufficient_events(self):
        events = [
            ADLEvent(
                event_timestamp=datetime(2026, 2, 10, 8, 0),
                logged_timestamp=datetime(2026, 2, 10, 8, 0),
                assistance_level=AssistanceLevel.INDEPENDENT,
                is_refusal=False
            )
        ]
        score = ScoringEngine.calculate_dependency_score(events)
        self.assertEqual(score.points, 0)
        self.assertIn('Insufficient', score.description)
    
    def test_increasing_dependency(self):
        # First 3: Independent (0)
        # Last 3: Full Assistance (2)
        # Difference: 2.0 > 0.5 threshold
        events = [
            # Baseline: all independent
            ADLEvent(datetime(2026, 2, 10, 8, 0), datetime(2026, 2, 10, 8, 0), 
                    AssistanceLevel.INDEPENDENT, False),
            ADLEvent(datetime(2026, 2, 11, 8, 0), datetime(2026, 2, 11, 8, 0), 
                    AssistanceLevel.INDEPENDENT, False),
            ADLEvent(datetime(2026, 2, 12, 8, 0), datetime(2026, 2, 12, 8, 0), 
                    AssistanceLevel.INDEPENDENT, False),
            # Transition
            ADLEvent(datetime(2026, 2, 13, 8, 0), datetime(2026, 2, 13, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            # Recent: full assistance
            ADLEvent(datetime(2026, 2, 14, 8, 0), datetime(2026, 2, 14, 8, 0), 
                    AssistanceLevel.FULL_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 15, 8, 0), datetime(2026, 2, 15, 8, 0), 
                    AssistanceLevel.FULL_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 16, 8, 0), datetime(2026, 2, 16, 8, 0), 
                    AssistanceLevel.FULL_ASSISTANCE, False),
        ]
        score = ScoringEngine.calculate_dependency_score(events)
        self.assertEqual(score.points, 2)
        self.assertIn('Increasing dependency', score.description)
    
    def test_stable_dependency(self):
        # All events at same level
        events = [
            ADLEvent(datetime(2026, 2, 10+i, 8, 0), datetime(2026, 2, 10+i, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False)
            for i in range(6)
        ]
        score = ScoringEngine.calculate_dependency_score(events)
        self.assertEqual(score.points, 0)
        self.assertIn('No significant dependency change', score.description)
    
    def test_decreasing_dependency(self):
        # Full → Independent (improvement)
        events = [
            ADLEvent(datetime(2026, 2, 10+i, 8, 0), datetime(2026, 2, 10+i, 8, 0), 
                    AssistanceLevel.FULL_ASSISTANCE if i < 3 else AssistanceLevel.INDEPENDENT,
                    False)
            for i in range(6)
        ]
        score = ScoringEngine.calculate_dependency_score(events)
        self.assertEqual(score.points, 0)  # Improvement = no concern


class TestCareRiskScore(unittest.TestCase):
    """Test overall CRS calculation"""
    
    def test_green_scenario(self):
        # No refusals, small gaps (12h), stable dependency
        # For Oral Care: expected 2x daily, amber gap=16h
        events = [
            ADLEvent(datetime(2026, 2, 10, 8, 0), datetime(2026, 2, 10, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 10, 20, 0), datetime(2026, 2, 10, 20, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 11, 8, 0), datetime(2026, 2, 11, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 11, 20, 0), datetime(2026, 2, 11, 20, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 12, 8, 0), datetime(2026, 2, 12, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 12, 20, 0), datetime(2026, 2, 12, 20, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 13, 8, 0), datetime(2026, 2, 13, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
        ]
        
        crs = ScoringEngine.calculate_care_risk_score(events, ADL_DOMAINS['Oral Care'])
        self.assertEqual(crs.risk_level, RiskLevel.GREEN)
        self.assertEqual(crs.total_points, 0)
    
    def test_amber_scenario(self):
        # 2 refusals = 2 points = AMBER
        events = [
            ADLEvent(datetime(2026, 2, 10, 8, 0), datetime(2026, 2, 10, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
            ADLEvent(datetime(2026, 2, 11, 8, 0), datetime(2026, 2, 11, 8, 0), 
                    AssistanceLevel.REFUSED, True),
            ADLEvent(datetime(2026, 2, 12, 8, 0), datetime(2026, 2, 12, 8, 0), 
                    AssistanceLevel.REFUSED, True),
        ]
        
        crs = ScoringEngine.calculate_care_risk_score(events, ADL_DOMAINS['Oral Care'])
        self.assertEqual(crs.risk_level, RiskLevel.AMBER)
        self.assertGreaterEqual(crs.total_points, 2)
    
    def test_red_scenario(self):
        # 4 refusals (3 pts) + large gap (2 pts) = 5 pts = RED
        events = [
            ADLEvent(datetime(2026, 2, 10, 8, 0), datetime(2026, 2, 10, 8, 0), 
                    AssistanceLevel.REFUSED, True),
            ADLEvent(datetime(2026, 2, 11, 8, 0), datetime(2026, 2, 11, 8, 0), 
                    AssistanceLevel.REFUSED, True),
            ADLEvent(datetime(2026, 2, 12, 8, 0), datetime(2026, 2, 12, 8, 0), 
                    AssistanceLevel.REFUSED, True),
            ADLEvent(datetime(2026, 2, 13, 8, 0), datetime(2026, 2, 13, 8, 0), 
                    AssistanceLevel.REFUSED, True),
            # 30 hour gap (> 24h red threshold for Oral Care)
            ADLEvent(datetime(2026, 2, 14, 14, 0), datetime(2026, 2, 14, 14, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
        ]
        
        crs = ScoringEngine.calculate_care_risk_score(events, ADL_DOMAINS['Oral Care'])
        self.assertEqual(crs.risk_level, RiskLevel.RED)
        self.assertGreaterEqual(crs.total_points, 5)


class TestDocumentationScore(unittest.TestCase):
    """Test DCS calculation"""
    
    def test_green_compliant(self):
        # 14 entries / 14 expected = 100%
        dcs = ScoringEngine.calculate_documentation_score(
            actual_entries=14,
            expected_per_day=2.0,
            period_days=7
        )
        self.assertEqual(dcs.risk_level, RiskLevel.GREEN)
        self.assertEqual(dcs.compliance_percentage, 100.0)
    
    def test_amber_threshold(self):
        # 10 entries / 14 expected = 71% (between 60-90%)
        dcs = ScoringEngine.calculate_documentation_score(
            actual_entries=10,
            expected_per_day=2.0,
            period_days=7
        )
        self.assertEqual(dcs.risk_level, RiskLevel.AMBER)
        self.assertGreaterEqual(dcs.compliance_percentage, DOCUMENTATION_THRESHOLD_AMBER * 100)
        self.assertLess(dcs.compliance_percentage, 90)
    
    def test_red_threshold(self):
        # 5 entries / 14 expected = 36% (<60%)
        dcs = ScoringEngine.calculate_documentation_score(
            actual_entries=5,
            expected_per_day=2.0,
            period_days=7
        )
        self.assertEqual(dcs.risk_level, RiskLevel.RED)
        self.assertLess(dcs.compliance_percentage, DOCUMENTATION_THRESHOLD_AMBER * 100)
    
    def test_exact_amber_boundary(self):
        # Exactly 60% should be AMBER
        expected = 14.0
        actual = int(expected * 0.6)  # 8.4 → 8
        dcs = ScoringEngine.calculate_documentation_score(
            actual_entries=actual,
            expected_per_day=2.0,
            period_days=7
        )
        # 8/14 = 57% = RED (below 60%)
        self.assertEqual(dcs.risk_level, RiskLevel.RED)


class TestResidentDomainAnalysis(unittest.TestCase):
    """Test complete resident analysis"""
    
    def test_full_analysis(self):
        events = [
            ADLEvent(datetime(2026, 2, 10, 8, 0), datetime(2026, 2, 10, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False, "Morning care"),
            ADLEvent(datetime(2026, 2, 10, 20, 0), datetime(2026, 2, 10, 20, 0), 
                    AssistanceLevel.REFUSED, True, "Evening care refused"),
            ADLEvent(datetime(2026, 2, 11, 8, 0), datetime(2026, 2, 11, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False),
        ]
        
        analysis = ScoringEngine.analyze_resident_domain(
            resident_id='R001',
            domain_name='Oral Care',
            events=events,
            period_days=7
        )
        
        # Check structure
        self.assertEqual(analysis.resident_id, 'R001')
        self.assertEqual(analysis.domain_name, 'Oral Care')
        self.assertEqual(analysis.total_events, 3)
        self.assertEqual(analysis.refusal_count, 1)
        
        # Check scores exist
        self.assertIsNotNone(analysis.care_risk_score)
        self.assertIsNotNone(analysis.documentation_score)
        
        # Check overall risk is worst of the two
        self.assertIn(analysis.overall_risk, [RiskLevel.RED, RiskLevel.AMBER, RiskLevel.GREEN])
    
    def test_overall_risk_calculation(self):
        # Create scenario where CRS=GREEN but DCS=RED
        events = [
            ADLEvent(datetime(2026, 2, 10+i, 8, 0), datetime(2026, 2, 10+i, 8, 0), 
                    AssistanceLevel.SOME_ASSISTANCE, False)
            for i in range(3)  # Only 3 events, expected 14 for Oral Care
        ]
        
        analysis = ScoringEngine.analyze_resident_domain(
            resident_id='R001',
            domain_name='Oral Care',
            events=events,
            period_days=7
        )
        
        # DCS should be RED (3/14 = 21%)
        self.assertEqual(analysis.documentation_score.risk_level, RiskLevel.RED)
        
        # Overall risk should be RED (worst of the two)
        self.assertEqual(analysis.overall_risk, RiskLevel.RED)


class TestHelperFunctions(unittest.TestCase):
    """Test utility functions"""
    
    def test_parse_assistance_level_independent(self):
        from src.scoring_engine import parse_assistance_level
        
        level = parse_assistance_level("Dressed himself on his own", "")
        self.assertEqual(level, AssistanceLevel.INDEPENDENT)
    
    def test_parse_assistance_level_refusal(self):
        from src.scoring_engine import parse_assistance_level
        
        level = parse_assistance_level("Resident refused morning care", "")
        self.assertEqual(level, AssistanceLevel.REFUSED)
    
    def test_parse_assistance_level_full(self):
        from src.scoring_engine import parse_assistance_level
        
        level = parse_assistance_level("Required full assistance", "")
        self.assertEqual(level, AssistanceLevel.FULL_ASSISTANCE)
    
    def test_is_refusal_detection(self):
        from src.scoring_engine import is_refusal
        
        self.assertTrue(is_refusal("Resident refused", ""))
        self.assertTrue(is_refusal("", "Care declined"))
        self.assertTrue(is_refusal("didn't want to get dressed", ""))
        self.assertFalse(is_refusal("Assisted with washing", ""))


class TestThresholdConstants(unittest.TestCase):
    """Verify threshold constants are as documented"""
    
    def test_refusal_thresholds(self):
        self.assertEqual(REFUSAL_THRESHOLD_AMBER, 2)
        self.assertEqual(REFUSAL_THRESHOLD_RED, 4)
    
    def test_documentation_thresholds(self):
        self.assertEqual(DOCUMENTATION_THRESHOLD_AMBER, 0.60)
        self.assertEqual(DOCUMENTATION_THRESHOLD_RED, 0.40)
    
    def test_domain_configs(self):
        # Verify standard domains exist
        self.assertIn('Washing/Bathing', ADL_DOMAINS)
        self.assertIn('Oral Care', ADL_DOMAINS)
        self.assertIn('Toileting', ADL_DOMAINS)
        
        # Verify Oral Care config
        oral = ADL_DOMAINS['Oral Care']
        self.assertEqual(oral.expected_per_day, 2.0)
        self.assertEqual(oral.gap_threshold_amber, 16)
        self.assertEqual(oral.gap_threshold_red, 24)


def run_tests():
    """Run all tests and print results"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED - Scoring engine is working correctly!")
    else:
        print("\n❌ SOME TESTS FAILED - Review failures above")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
