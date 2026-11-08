"""Synthetic strategy fixtures; no real approval or business result implied."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('strategy_contract', Path(__file__).resolve().parents[1] / 'dify/nodes/validate_strategy.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StrategyContractTests(unittest.TestCase):
    def setUp(self):
        self.bundle = {'evidence': {'evidence_id': 'fixture', 'facts': {'fact': {'value': 1}}, 'human_review_status': 'pending'},
                       'diagnosis': {'evidence_id': 'fixture', 'findings': [{'finding_id': 'D1', 'fact_ids': ['fact']}]}}
        self.value = {'evidence_id': 'fixture', 'strategies': [{
            'strategy_id': 'S1', 'finding_id': 'D1', 'fact_ids': ['fact'], 'action': '先人工核查，再按确认的问题制定措施',
            'owner_function': '商品品控', 'target_metric': '核查完成记录数占需核查记录数',
            'validation_design': '留存检查记录并复核，不直接推断因果', 'validation_days': 14,
            'guardrail': '避免遗漏或重复记录', 'target_direction': 'clarify',
            'limitations': ['合成测试夹具，不是真实策略'], 'effect_status': 'hypothesis_only'}]}

    def test_valid_is_pending(self):
        self.assertEqual(module.validate_strategy(self.value, self.bundle)['human_review_status'], 'pending')

    def test_invalid_fact_rejected(self):
        self.value['strategies'][0]['fact_ids'] = ['invented']
        with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)

    def test_numeric_effect_rejected(self):
        self.value['strategies'][0]['action'] = '提升50%'
        with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)

    def test_effect_cannot_be_proven(self):
        self.value['strategies'][0]['effect_status'] = 'proven'
        with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)

    def test_planned_days_integer_range(self):
        for days in [True, 0, 100, '14']:
            self.value['strategies'][0]['validation_days'] = days
            with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)

    def test_missing_guardrail_rejected(self):
        del self.value['strategies'][0]['guardrail']
        with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)

    def test_duplicate_finding_rejected(self):
        extra = copy.deepcopy(self.value['strategies'][0])
        extra['strategy_id'] = 'S2'
        self.value['strategies'].append(extra)
        with self.assertRaises(ValueError): module.validate_strategy(self.value, self.bundle)
